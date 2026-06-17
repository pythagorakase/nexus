use serde::Deserialize;
use serde_json::Value;
use std::{
    env, fs,
    path::{Path, PathBuf},
    process::Command,
    sync::{Arc, Mutex},
    thread,
    time::{Duration, Instant},
};
use tauri::{Manager, WebviewWindow};

const BUNDLED_CONFIG: &str = include_str!("../nexus.desktop.json");
const DEFAULT_RUNTIME_ORIGIN: &str = "http://127.0.0.1:8002";
const DEFAULT_STATUS_PATH: &str = "/runtime/status";
const DEFAULT_AUTH_HEADER: &str = "X-Nexus-Auth";
const DEFAULT_AUTH_TOKEN_ENV: &str = "NEXUS_AUTH";

#[derive(Clone, Debug, Deserialize, PartialEq, Eq)]
#[serde(default, rename_all = "camelCase")]
pub struct DesktopConfig {
    pub runtime_origin: String,
    pub status_path: String,
    pub auth_header: String,
    pub auth_token_env: String,
    pub runtime_command: Vec<String>,
    pub start_args: Vec<String>,
    pub stop_args: Vec<String>,
    pub working_directory: Option<PathBuf>,
    pub startup_timeout_seconds: u64,
    pub poll_interval_milliseconds: u64,
}

impl Default for DesktopConfig {
    fn default() -> Self {
        Self {
            runtime_origin: DEFAULT_RUNTIME_ORIGIN.to_string(),
            status_path: DEFAULT_STATUS_PATH.to_string(),
            auth_header: DEFAULT_AUTH_HEADER.to_string(),
            auth_token_env: DEFAULT_AUTH_TOKEN_ENV.to_string(),
            runtime_command: vec!["nexus".to_string()],
            start_args: vec!["--json".to_string(), "up".to_string()],
            stop_args: vec!["--json".to_string(), "down".to_string()],
            working_directory: None,
            startup_timeout_seconds: 90,
            poll_interval_milliseconds: 500,
        }
    }
}

#[derive(Clone, Debug)]
pub struct ResolvedDesktopConfig {
    pub config: DesktopConfig,
    pub source_path: Option<PathBuf>,
    pub working_directory: PathBuf,
}

#[derive(Default)]
struct RuntimeSession {
    started_by_shell: bool,
}

pub fn run() {
    let loaded = match load_desktop_config() {
        Ok(config) => config,
        Err(error) => {
            eprintln!("failed to load NEXUS desktop config: {error}");
            return;
        }
    };
    let session = Arc::new(Mutex::new(RuntimeSession::default()));
    let startup_config = loaded.clone();
    let startup_session = session.clone();

    let app = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .setup(move |app| {
            let window = app
                .get_webview_window("main")
                .expect("main window is declared in tauri.conf.json");
            spawn_runtime_startup(window, startup_config.clone(), startup_session.clone());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building NEXUS desktop application");

    app.run(move |_app_handle, event| {
        if let tauri::RunEvent::ExitRequested { .. } = event {
            stop_owned_runtime(&loaded, &session);
        }
    });
}

fn spawn_runtime_startup(
    window: WebviewWindow,
    config: ResolvedDesktopConfig,
    session: Arc<Mutex<RuntimeSession>>,
) {
    thread::spawn(move || {
        set_loading_status(&window, "Checking runtime", &config.config.runtime_origin);
        match ensure_runtime_ready(&config, &session, &window) {
            Ok(status) => navigate_to_runtime(&window, &config.config.runtime_origin, &status),
            Err(error) => set_loading_status(&window, "Runtime unavailable", &error),
        }
    });
}

fn ensure_runtime_ready(
    config: &ResolvedDesktopConfig,
    session: &Arc<Mutex<RuntimeSession>>,
    window: &WebviewWindow,
) -> Result<Value, String> {
    if let Ok(status) = fetch_runtime_status(config) {
        if status.get("ok").and_then(Value::as_bool).unwrap_or(false) {
            set_loading_status(
                window,
                "Attached to running runtime",
                &runtime_summary(&status),
            );
            return Ok(status);
        }
    }

    set_loading_status(window, "Starting managed runtime", "Running nexus up");
    match run_runtime_command(config, &config.config.start_args) {
        Ok(output) => {
            session
                .lock()
                .expect("runtime session lock")
                .started_by_shell = true;
            if !output.trim().is_empty() {
                set_loading_status(window, "Runtime command returned", output.trim());
            }
        }
        Err(error) => {
            if let Ok(status) = fetch_runtime_status(config) {
                if status.get("ok").and_then(Value::as_bool).unwrap_or(false) {
                    set_loading_status(
                        window,
                        "Attached after startup race",
                        &runtime_summary(&status),
                    );
                    return Ok(status);
                }
            }
            return Err(error);
        }
    }

    wait_for_runtime_ready(config, window)
}

fn wait_for_runtime_ready(
    config: &ResolvedDesktopConfig,
    window: &WebviewWindow,
) -> Result<Value, String> {
    let deadline = Instant::now() + Duration::from_secs(config.config.startup_timeout_seconds);
    let mut last_error = String::from("runtime did not answer yet");
    while Instant::now() < deadline {
        match fetch_runtime_status(config) {
            Ok(status) => {
                let summary = runtime_summary(&status);
                set_loading_status(window, "Waiting for runtime readiness", &summary);
                if status.get("ok").and_then(Value::as_bool).unwrap_or(false) {
                    return Ok(status);
                }
                last_error = summary;
            }
            Err(error) => {
                last_error = error;
            }
        }
        thread::sleep(Duration::from_millis(
            config.config.poll_interval_milliseconds.max(100),
        ));
    }
    Err(format!(
        "runtime did not become ready within {}s: {}",
        config.config.startup_timeout_seconds, last_error
    ))
}

fn stop_owned_runtime(config: &ResolvedDesktopConfig, session: &Arc<Mutex<RuntimeSession>>) {
    let should_stop = {
        let mut guard = session.lock().expect("runtime session lock");
        let started = guard.started_by_shell;
        guard.started_by_shell = false;
        started
    };
    if should_stop {
        let _ = run_runtime_command(config, &config.config.stop_args);
    }
}

fn fetch_runtime_status(config: &ResolvedDesktopConfig) -> Result<Value, String> {
    let url = runtime_status_url(&config.config)?;
    let auth_value = env::var(&config.config.auth_token_env).unwrap_or_default();
    let response = reqwest::blocking::Client::new()
        .get(url.clone())
        .header(&config.config.auth_header, auth_value)
        .timeout(Duration::from_secs(3))
        .send()
        .map_err(|error| format!("{url}: {error}"))?;
    let status = response.status();
    if !status.is_success() {
        return Err(format!("{url}: HTTP {status}"));
    }
    response
        .json::<Value>()
        .map_err(|error| format!("{url}: invalid JSON: {error}"))
}

fn run_runtime_command(config: &ResolvedDesktopConfig, args: &[String]) -> Result<String, String> {
    let (program, prefix_args) = config
        .config
        .runtime_command
        .split_first()
        .ok_or_else(|| "runtimeCommand must contain at least the CLI program".to_string())?;
    let program_path = resolve_program(program);
    let output = Command::new(&program_path)
        .args(prefix_args)
        .args(args)
        .current_dir(&config.working_directory)
        .env("NEXUS_DESKTOP", "1")
        .output()
        .map_err(|error| {
            format!(
                "failed to run {} {}: {}",
                display_command(&program_path, prefix_args, args),
                config.working_directory.display(),
                error
            )
        })?;
    let stdout = String::from_utf8_lossy(&output.stdout);
    let stderr = String::from_utf8_lossy(&output.stderr);
    let combined = [stdout.trim(), stderr.trim()]
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join("\n");
    if output.status.success() {
        Ok(combined)
    } else {
        Err(format!(
            "{} exited with {}{}{}",
            display_command(&program_path, prefix_args, args),
            output.status,
            if combined.is_empty() { "" } else { ":\n" },
            combined
        ))
    }
}

fn display_command(program: &Path, prefix_args: &[String], args: &[String]) -> String {
    std::iter::once(program.display().to_string())
        .chain(prefix_args.iter().cloned())
        .chain(args.iter().cloned())
        .collect::<Vec<_>>()
        .join(" ")
}

fn runtime_status_url(config: &DesktopConfig) -> Result<String, String> {
    let origin = config.runtime_origin.trim_end_matches('/');
    let path = if config.status_path.starts_with('/') {
        config.status_path.clone()
    } else {
        format!("/{}", config.status_path)
    };
    let url = format!("{origin}{path}");
    url::Url::parse(&url).map_err(|error| format!("invalid runtime status URL {url}: {error}"))?;
    Ok(url)
}

fn navigate_to_runtime(window: &WebviewWindow, runtime_origin: &str, status: &Value) {
    let origin = serde_json::to_string(runtime_origin).expect("string serialization");
    let status_json = serde_json::to_string(status).expect("status serialization");
    let script = format!(
        "if (window.__nexusDesktopReady) {{ window.__nexusDesktopReady({origin}, {status_json}); }} window.setTimeout(() => window.location.replace({origin}), 250);"
    );
    eval_on_main_thread(window, script);
}

fn set_loading_status(window: &WebviewWindow, label: &str, detail: &str) {
    let label = serde_json::to_string(label).expect("string serialization");
    let detail = serde_json::to_string(detail).expect("string serialization");
    let script = format!(
        "if (window.__nexusDesktopStatus) {{ window.__nexusDesktopStatus({label}, {detail}); }}"
    );
    eval_on_main_thread(window, script);
}

fn eval_on_main_thread(window: &WebviewWindow, script: String) {
    let target = window.clone();
    let _ = window.run_on_main_thread(move || {
        let _ = target.eval(script);
    });
}

fn runtime_summary(status: &Value) -> String {
    let profile = status
        .get("profile")
        .and_then(Value::as_str)
        .unwrap_or("unknown");
    let slot = status
        .get("slot")
        .map(Value::to_string)
        .unwrap_or_else(|| "?".to_string());
    let database = status
        .get("database")
        .and_then(|database| database.get("ok"))
        .and_then(Value::as_bool)
        .unwrap_or(false);
    let services_ok = status
        .get("services")
        .and_then(Value::as_object)
        .map(|services| {
            services
                .iter()
                .map(|(name, service)| {
                    let ok = service.get("ok").and_then(Value::as_bool).unwrap_or(false);
                    format!("{name}:{}", if ok { "ok" } else { "down" })
                })
                .collect::<Vec<_>>()
                .join(", ")
        })
        .unwrap_or_else(|| "services:unknown".to_string());
    format!(
        "profile {profile}, slot {slot}, database {}, {services_ok}",
        if database { "ok" } else { "down" }
    )
}

pub fn load_desktop_config() -> Result<ResolvedDesktopConfig, String> {
    let (mut config, source_path) = read_config_source()?;
    if let Ok(origin) = env::var("NEXUS_DESKTOP_RUNTIME_ORIGIN") {
        if !origin.trim().is_empty() {
            config.runtime_origin = origin;
        }
    }
    let working_directory = resolve_working_directory(&config, source_path.as_deref())?;
    Ok(ResolvedDesktopConfig {
        config,
        source_path,
        working_directory,
    })
}

fn read_config_source() -> Result<(DesktopConfig, Option<PathBuf>), String> {
    if let Ok(path) = env::var("NEXUS_DESKTOP_CONFIG") {
        let path = PathBuf::from(path);
        return read_config_file(&path).map(|config| (config, Some(path)));
    }

    if let Some(repo_root) = discover_repo_root() {
        let path = repo_root.join("ui/src-tauri/nexus.desktop.json");
        if path.exists() {
            return read_config_file(&path).map(|config| (config, Some(path)));
        }
    }

    serde_json::from_str::<DesktopConfig>(BUNDLED_CONFIG)
        .map(|config| (config, None))
        .map_err(|error| format!("bundled desktop config is invalid: {error}"))
}

fn read_config_file(path: &Path) -> Result<DesktopConfig, String> {
    let text = fs::read_to_string(path)
        .map_err(|error| format!("failed to read {}: {error}", path.display()))?;
    serde_json::from_str(&text).map_err(|error| format!("{} is invalid: {error}", path.display()))
}

fn resolve_working_directory(
    config: &DesktopConfig,
    source_path: Option<&Path>,
) -> Result<PathBuf, String> {
    if let Some(path) = &config.working_directory {
        let resolved = if path.is_absolute() {
            path.clone()
        } else if let Some(source_path) = source_path {
            source_path
                .parent()
                .unwrap_or_else(|| Path::new("."))
                .join(path)
        } else if let Some(repo_root) = discover_repo_root() {
            repo_root.join(path)
        } else {
            env::current_dir()
                .map_err(|error| format!("failed to resolve current directory: {error}"))?
                .join(path)
        };
        return Ok(resolved);
    }
    discover_repo_root()
        .or_else(|| env::current_dir().ok())
        .ok_or_else(|| {
            "failed to resolve desktop runtime working directory; set workingDirectory".to_string()
        })
}

fn discover_repo_root() -> Option<PathBuf> {
    let mut seeds = Vec::new();
    if let Ok(cwd) = env::current_dir() {
        seeds.push(cwd);
    }
    if let Ok(exe) = env::current_exe() {
        seeds.push(exe);
    }
    for seed in seeds {
        let mut cursor = if seed.is_file() {
            seed.parent().map(Path::to_path_buf)
        } else {
            Some(seed)
        };
        while let Some(path) = cursor {
            if path.join("pyproject.toml").exists() && path.join("nexus.toml").exists() {
                return Some(path);
            }
            cursor = path.parent().map(Path::to_path_buf);
        }
    }
    None
}

fn resolve_program(program: &str) -> PathBuf {
    let path = PathBuf::from(program);
    if path.components().count() > 1 || path.is_absolute() {
        return path;
    }

    for candidate in path_candidates(program) {
        if candidate.is_file() {
            return candidate;
        }
    }
    PathBuf::from(program)
}

fn path_candidates(program: &str) -> Vec<PathBuf> {
    let mut candidates = Vec::new();
    if let Some(paths) = env::var_os("PATH") {
        candidates.extend(env::split_paths(&paths).map(|path| path.join(program)));
    }
    candidates.extend(common_bin_dirs().into_iter().map(|path| path.join(program)));
    candidates
}

fn common_bin_dirs() -> Vec<PathBuf> {
    let mut dirs = vec![
        PathBuf::from("/opt/homebrew/bin"),
        PathBuf::from("/usr/local/bin"),
        PathBuf::from("/usr/bin"),
        PathBuf::from("/bin"),
    ];
    if let Some(home) = dirs::home_dir() {
        dirs.push(home.join(".local/bin"));
        dirs.push(home.join(".cargo/bin"));
    }
    dirs
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn desktop_config_defaults_to_runtime_contract() {
        let config = DesktopConfig::default();
        assert_eq!(config.runtime_origin, "http://127.0.0.1:8002");
        assert_eq!(config.status_path, "/runtime/status");
        assert_eq!(config.auth_header, "X-Nexus-Auth");
        assert_eq!(config.start_args, vec!["--json", "up"]);
        assert_eq!(config.stop_args, vec!["--json", "down"]);
    }

    #[test]
    fn runtime_status_url_normalizes_slashes() {
        let config = DesktopConfig {
            runtime_origin: "http://127.0.0.1:8002/".to_string(),
            status_path: "runtime/status".to_string(),
            ..DesktopConfig::default()
        };
        assert_eq!(
            runtime_status_url(&config).unwrap(),
            "http://127.0.0.1:8002/runtime/status"
        );
    }

    #[test]
    fn runtime_summary_includes_profile_slot_and_services() {
        let status = serde_json::json!({
            "profile": "local",
            "slot": 5,
            "database": {"ok": true},
            "services": {
                "gateway": {"ok": true},
                "mock_openai": {"ok": false}
            }
        });
        let summary = runtime_summary(&status);
        assert!(summary.contains("profile local"));
        assert!(summary.contains("slot 5"));
        assert!(summary.contains("database ok"));
        assert!(summary.contains("gateway:ok"));
        assert!(summary.contains("mock_openai:down"));
    }
}
