fn main() {
    println!("cargo:rerun-if-changed=nexus.desktop.json");
    println!(
        "cargo:rustc-env=NEXUS_BUILD_CONFIG_DIR={}",
        std::env::var("CARGO_MANIFEST_DIR").expect("CARGO_MANIFEST_DIR is set")
    );
    tauri_build::build()
}
