"""Real source/git/CLI proofs for the shrink-only exception disposition lint."""

from __future__ import annotations

import ast
import json
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts import check_exception_dispositions as lint

CHECKER = Path(lint.__file__).resolve()
PYTHONS = ("python3.11", "python3.12", "python3.13")


def _run(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=30)


def _git(root: Path, *args: str) -> str:
    result = _run("git", *args, cwd=root)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _commit(root: Path) -> str:
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=Lint Proof",
        "-c",
        "user.email=lint@example.invalid",
        "-c",
        "core.hooksPath=/dev/null",
        "commit",
        "-qm",
        "Test fixture",
    )
    return _git(root, "rev-parse", "HEAD")


def _write(root: Path, source: str, path: str = "nexus/example.py") -> Path:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(source).lstrip("\n"), encoding="utf-8")
    return target


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Make a real bootstrap ref without either lint artifact."""
    _git(tmp_path, "init", "-q")
    _write(tmp_path, "fixture\n", "README.md")
    _write(tmp_path, "ignored/\n", ".gitignore")
    _commit(tmp_path)
    (tmp_path / "scripts").mkdir()
    shutil.copyfile(CHECKER, tmp_path / lint.CHECKER_PATH)
    _baseline(tmp_path)
    return tmp_path


def _baseline(root: Path) -> dict[str, str]:
    (root / lint.BASELINE_PATH).parent.mkdir(parents=True, exist_ok=True)
    debt = {
        h.identity: lint.SEED_REASON
        for h in lint.collect_handlers(root)
        if not h.ast_exempt and h.marker is None
    }
    (root / lint.BASELINE_PATH).write_text(
        json.dumps(
            {"schema_version": 1, "handlers": dict(sorted(debt.items()))}, indent=2
        )
        + "\n"
    )
    return debt


def _cli(
    root: Path, *args: str, python: str = sys.executable
) -> subprocess.CompletedProcess[str]:
    return _run(python, "-S", str(CHECKER), "--root", str(root), *args, cwd=root)


def _handlers(root: Path) -> list[lint.Handler]:
    return [h for h in lint.collect_handlers(root) if h.path == "nexus/example.py"]


def _catch(body: str, header: str = "except Exception as caught:") -> str:
    return (
        "try:\n    work()\n"
        + header
        + "\n"
        + textwrap.indent(textwrap.dedent(body).strip() + "\n", "    ")
    )


@pytest.mark.parametrize(
    "header",
    [
        "except ValueError:",
        "except (ValueError, TypeError):",
        "except:",
        "except BaseException:",
        "except* Exception:",
    ],
)
def test_new_unmarked_handler_fails(repo: Path, header: str) -> None:
    _write(repo, _catch("pass", header))
    (handler,) = _handlers(repo)
    expected = f"nexus/example.py:3: missing exception disposition: {handler.identity}"
    assert lint.check_tree(repo, repo / lint.BASELINE_PATH, "HEAD") == [expected]
    for python in _interpreters():
        result = _cli(repo, python=python)
        assert (result.returncode, result.stderr) == (1, expected + "\n")


@pytest.mark.parametrize(
    "kind", ["fail", "retry", "degrade-read-only", "safe-continuation"]
)
def test_valid_marker_satisfies_one_handler_only(repo: Path, kind: str) -> None:
    marked = _catch(
        "pass",
        "except Exception:  # nexus-exception-disposition: "
        f"{kind}; reason=reviewed contract; safety=visible failure",
    )
    _write(repo, marked)
    assert _cli(repo).returncode == 0
    (handler,) = _handlers(repo)
    assert handler.marker == {
        "kind": kind,
        "reason": "reviewed contract",
        "safety": "visible failure",
    }
    _write(repo, marked + _catch("pass"))
    result = _cli(repo)
    assert result.returncode == 1
    assert result.stderr.startswith(
        "nexus/example.py:7: missing exception disposition:"
    )
    assert result.stderr.count("missing exception disposition") == 1


@pytest.mark.parametrize(
    "source,invalid",
    [
        (_catch('"# nexus-exception-disposition: fail; reason=x; safety=y"'), False),
        (_catch("pass", "except Exception:  # noqa: BLE001"), False),
        (
            "# nexus-exception-disposition: fail; reason=x; safety=y\n"
            + _catch("pass"),
            False,
        ),
        (
            _catch(
                "pass",
                "except Exception:  # nexus-exception-disposition: unknown; "
                "reason=x; safety=y",
            ),
            True,
        ),
        (
            _catch(
                "pass",
                "except Exception:  # nexus-exception-disposition: fail; "
                "reason= ; safety=y",
            ),
            True,
        ),
        (
            _catch(
                "pass",
                "except Exception:  # nexus-exception-disposition: fail; "
                "reason=x; safety= ",
            ),
            True,
        ),
        (
            _catch(
                "pass",
                "except Exception:  # nexus-exception-disposition: fail; " "reason=x",
            ),
            True,
        ),
        (
            _catch(
                "pass",
                "except Exception:  # nexus-exception-disposition: fail; "
                "reason=x; safety=y; extra=z",
            ),
            True,
        ),
    ],
)
def test_marker_requires_comment_token_and_contract(
    repo: Path, source: str, invalid: bool
) -> None:
    if invalid:
        _write(repo, _catch("pass"))
        _baseline(repo)
        _commit(repo)
    _write(repo, source)
    result = _cli(repo)
    assert result.returncode == 1
    assert ("invalid exception disposition marker" in result.stderr) == invalid
    if not invalid:
        assert "missing exception disposition" in result.stderr


def test_multiline_header_marker_uses_colon_line(repo: Path) -> None:
    _write(
        repo,
        """
        try:
            work()
        except (
            ValueError,
            TypeError,
        ):  # nexus-exception-disposition: fail; reason=x; safety=y
            pass
    """,
    )
    assert _cli(repo).returncode == 0
    _write(
        repo,
        """
        try:
            work()
        except (  # nexus-exception-disposition: fail; reason=x; safety=y
            ValueError,
        ):
            pass
    """,
    )
    assert "missing exception disposition" in _cli(repo).stderr


@pytest.mark.parametrize(
    "body",
    [
        "raise",
        "raise caught",
        "raise RuntimeError('translated') from caught",
        "log(caught)\nraise",
        "if flag:\n    raise\nelse:\n    raise caught",
        "try:\n    raise\nexcept ValueError:\n    raise\nelse:\n    raise",
        "try:\n    return\nfinally:\n    raise",
        "match value:\n    case 1:\n        raise\n    case _:\n        raise",
        "raise\nyield caught",  # unreachable suspension does not prevent exemption
    ],
)
def test_always_raising_handlers_are_exempt(repo: Path, body: str) -> None:
    _write(repo, "def function():\n" + textwrap.indent(_catch(body), "    "))
    assert all(handler.ast_exempt for handler in _handlers(repo))
    assert _cli(repo).returncode == 0


@pytest.mark.parametrize(
    "body",
    [
        "if flag:\n    raise",
        "return\nraise",
        "def nested():\n    raise",
        "class Nested:\n    def nested(self):\n        raise",
        "for value in values:\n    raise",
        "while flag:\n    raise",
        "try:\n    raise\nfinally:\n    return",
        "try:\n    raise\nexcept Exception:\n    pass",
        "with suppress(Exception):\n    raise",
        "match value:\n    case 1:\n        raise",
        "match value:\n    case _ if flag:\n        raise",
        "yield caught\nraise",
        "yield from values\nraise",
        "for value in values:\n    break\nelse:\n    raise",
        "try:\n    yield caught\nfinally:\n    raise",
        "if flag:\n    return\nelse:\n    raise",
        "while flag:\n    continue",
        "def nested(value=(yield caught)):\n    pass\nraise",
        "class Nested((yield caught)):\n    pass\nraise",
        "match value:\n    case _ if (yield caught):\n        raise\n"
        "    case _:\n        raise",
    ],
)
def test_partial_and_overridden_raises_are_not_exempt(repo: Path, body: str) -> None:
    _write(repo, "def function():\n" + textwrap.indent(_catch(body), "    "))
    assert not _handlers(repo)[0].ast_exempt
    assert "missing exception disposition" in _cli(repo).stderr


@pytest.mark.parametrize(
    "definition,suspends",
    [
        ("callback = lambda value=(yield caught): value", True),
        ("callback = lambda *, value=(yield from values): value", True),
        ("callback = lambda value=(await pending()): value", True),
        ("callback = lambda value=1: value", False),
        ("callback = lambda: (yield caught)", False),
        ("def nested():\n    yield caught", False),
        ("async def nested():\n    await pending()", False),
        ("def nested(value=(yield caught)):\n    pass", True),
        ("def nested(*, value=(yield from values)):\n    pass", True),
        ("async def nested(value=(await pending())):\n    pass", True),
        ("@(yield caught)\ndef nested():\n    pass", True),
        ("@(yield caught)\nasync def nested():\n    pass", True),
        ("@(await pending())\nclass Nested:\n    pass", True),
        ("def nested(value: (yield caught)):\n    pass", True),
        ("def nested() -> (yield caught):\n    pass", True),
        ("class Nested((yield caught)):\n    pass", True),
        ("class Nested(metaclass=(yield caught)):\n    pass", True),
        ("class Nested:\n    def method(self):\n        yield caught", False),
        ("callback = lambda value=(lambda item=(yield caught): item): value", True),
    ],
)
def test_nested_scope_definition_suspension(
    repo: Path, definition: str, suspends: bool
) -> None:
    """Definition expressions execute here; nested bodies execute later."""
    prefix = "async def" if "await" in definition else "def"
    source = f"{prefix} function():\n" + textwrap.indent(
        _catch(definition + "\nraise"), "    "
    )
    compile(source, "nexus/example.py", "exec", dont_inherit=True)
    _write(repo, source)
    (handler,) = _handlers(repo)
    assert handler.ast_exempt is not suspends
    result = _cli(repo)
    assert result.returncode == int(suspends)
    assert ("missing exception disposition" in result.stderr) is suspends


@pytest.mark.parametrize(
    "inner_body,exempt",
    [
        ("pass", True),
        ('"docstring"\npass\n...\nNone\n42', True),
        ("x = 1", False),
        ("foo()", False),
        ("value", False),
        ("value.attribute", False),
        ("return value", False),
    ],
)
def test_inner_handler_reachability(repo: Path, inner_body: str, exempt: bool) -> None:
    """Only pass and constant expressions prove an inner catch unreachable."""
    body = (
        "try:\n"
        + textwrap.indent(inner_body, "    ")
        + "\nexcept Exception:\n    return\nraise"
    )
    source = "def function():\n" + textwrap.indent(_catch(body), "    ")
    compile(source, "nexus/example.py", "exec", dont_inherit=True)
    _write(repo, source)
    outer, inner = _handlers(repo)
    assert outer.ast_exempt is exempt
    assert not inner.ast_exempt  # Still inventoried separately, even if unreachable.
    result = _cli(repo)
    assert result.returncode == 1
    assert result.stderr.count("missing exception disposition") == (1 if exempt else 2)
    assert (f": {outer.identity}\n" in result.stderr) is not exempt
    assert f": {inner.identity}\n" in result.stderr


@pytest.mark.parametrize("body", ["logging.error(caught)", "cleanup()"])
def test_logging_observer_still_requires_disposition(repo: Path, body: str) -> None:
    _write(repo, _catch(body))
    assert _cli(repo).returncode == 1


@pytest.mark.parametrize("retirement", ["mark", "delete", "raise"])
def test_baseline_shrinks_after_debt_retires(repo: Path, retirement: str) -> None:
    _write(repo, _catch("pass"))
    _baseline(repo)
    _commit(repo)
    if retirement == "mark":
        source = _catch(
            "pass",
            "except Exception:  # nexus-exception-disposition: "
            "fail; reason=x; safety=y",
        )
    elif retirement == "delete":
        source = "work()\n"
    else:
        source = _catch("raise")
    _write(repo, source)
    assert "stale exception disposition baseline entry" in _cli(repo).stderr
    _baseline(repo)
    assert _cli(repo).returncode == 0


def test_baseline_growth_and_same_size_replacement_fail(repo: Path) -> None:
    legacy = _catch("pass")
    _write(repo, legacy)
    _baseline(repo)
    _commit(repo)
    _write(repo, legacy + _catch("cleanup()"))
    assert len(_baseline(repo)) == 2
    assert "baseline growth forbidden" in _cli(repo).stderr
    _write(repo, _catch("cleanup()"))
    assert len(_baseline(repo)) == 1
    assert "baseline growth forbidden" in _cli(repo).stderr


def test_retained_reason_cannot_change(repo: Path) -> None:
    _write(repo, _catch("pass"))
    _baseline(repo)
    _commit(repo)
    path = repo / lint.BASELINE_PATH
    path.write_text(path.read_text().replace(lint.SEED_REASON, "Changed reason"))
    assert "retained baseline reason changed" in _cli(repo).stderr


def test_baseline_identity_survives_line_shifts_but_not_body_changes(
    repo: Path,
) -> None:
    source = _catch("cleanup()") * 2
    _write(repo, source)
    initial = _baseline(repo)
    _commit(repo)
    assert len(initial) == 2
    first, second = _handlers(repo)
    assert first.identity.rsplit("|", 1)[0] == second.identity.rsplit("|", 1)[0]
    assert [h.identity.rsplit("|", 1)[1] for h in (first, second)] == ["1", "2"]
    _write(repo, "# comment\n\n" + source)
    assert set(initial) == {h.identity for h in _handlers(repo)}
    assert _cli(repo).returncode == 0
    _write(repo, source.replace("cleanup()", "cleanup(force=True)", 1))
    assert _cli(repo).returncode == 1
    assert "missing exception disposition" in _cli(repo).stderr
    assert "stale exception disposition baseline entry" in _cli(repo).stderr


def _interpreters() -> list[str]:
    """Require the full CI matrix, including locally uv-managed interpreters."""
    paths: list[str] = []
    uv = shutil.which("uv")
    for name in PYTHONS:
        version = name.removeprefix("python")
        path = None
        if version == "3.11":
            path = shutil.which("/Users/pythagor/nexus/.venv/bin/python")
        if path is None:
            path = shutil.which(name)
        if path is None and uv is not None:
            result = _run(uv, "python", "find", version, cwd=CHECKER.parent)
            if result.returncode == 0 and result.stdout.strip():
                path = shutil.which(result.stdout.strip())
        if path is None:
            for candidate in sorted(
                (Path.home() / ".local/share/uv/python").glob(
                    f"cpython-{version}.*/bin/{name}"
                )
            ):
                path = shutil.which(str(candidate))
                if path is not None:
                    break
        assert path is not None, (
            f"Required interpreter {name} missing; "
            f"install it with `uv python install {version}`. "
            "All three interpreters (3.11, 3.12, 3.13) are required."
        )
        paths.append(path)
    return paths


def test_identities_and_baseline_results_match_supported_python_versions(
    repo: Path,
) -> None:
    interpreters = _interpreters()
    source = _catch(
        """
        log()
        value = (None, True, 1, 1.0, b'bytes', 'text', ..., 1j)
        def nested(value=None, *args, **kwargs):
            try:
                call()
            except TypeError:
                pass
        class Nested:
            def method(self):
                return None
    """
    )
    _write(repo, source)
    _baseline(repo)
    _commit(repo)
    outcomes: list[list[tuple[int, str, str]]] = []
    for mode in ("clean", "new-debt", "stale-debt", "replacement"):
        _write(repo, source)
        _baseline(repo)
        if mode == "new-debt":
            _write(repo, source + _catch("new_debt()"))
        elif mode == "stale-debt":
            _write(repo, "work()\n")
        elif mode == "replacement":
            _write(repo, source.replace("log()", "log(level='error')"))
            _baseline(repo)
        documents = [
            _cli(repo, "--inventory", python=python) for python in interpreters
        ]
        assert all(result.returncode == 0 for result in documents)
        assert documents[0].stdout == documents[1].stdout == documents[2].stdout
        results = [_cli(repo, python=python) for python in interpreters]
        row = [(r.returncode, r.stdout, r.stderr) for r in results]
        assert row[0] == row[1] == row[2]
        assert row[0][0] == (0 if mode == "clean" else 1)
        outcomes.append(row)
    assert "missing exception disposition" in outcomes[1][0][2]
    assert "stale exception disposition baseline entry" in outcomes[2][0][2]
    assert "baseline growth forbidden" in outcomes[3][0][2]


def test_type_parameter_fields_preserve_semantics(repo: Path) -> None:
    # This syntax was added in 3.12; compare those parsers and also check that
    # nonempty type_params participate in identity, rather than being erased.
    _, python312, python313 = _interpreters()
    source = _catch("def nested[T]():\n    pass\nclass Nested[T]:\n    pass")
    _write(repo, source)
    a = _cli(repo, "--inventory", python=python312)
    b = _cli(repo, "--inventory", python=python313)
    assert a.returncode == b.returncode == 0
    assert a.stdout == b.stdout
    _write(repo, source.replace("[T]", "[T: int]"))
    changed = _cli(repo, "--inventory", python=python313)
    assert changed.returncode == 0
    assert json.loads(a.stdout)["handlers"] != json.loads(changed.stdout)["handlers"]


@pytest.mark.parametrize(
    "bad",
    [
        '{"schema_version":1,"schema_version":1,"handlers":{}}',
        '{"schema_version":2,"handlers":{}}',
        '{"schema_version":true,"handlers":{}}',
        '{"schema_version":1,"handlers":{"bad":"reason"}}',
        '{"schema_version":1,"handlers":[]}',
        '{"schema_version":1,"handlers":{},"other":1}',
    ],
)
def test_invalid_baseline_shapes_fail(repo: Path, bad: str) -> None:
    (repo / lint.BASELINE_PATH).write_text(bad)
    assert _cli(repo).returncode == 1


def test_bootstrap_and_baseline_validation_fail_closed(repo: Path) -> None:
    _write(repo, _catch("pass"))
    debt = _baseline(repo)
    assert _cli(repo).returncode == 0
    assert _cli(repo, "--baseline-base-ref", "no-such-ref").returncode == 1
    (key,) = debt
    path = repo / lint.BASELINE_PATH
    path.write_text(
        '{"schema_version":1,"handlers":{'
        + f'{json.dumps(key)}:"x",{json.dumps(key)}:"y"'
        + "}}"
    )
    assert "Duplicate baseline key" in _cli(repo).stderr
    path.write_text(json.dumps({"schema_version": 1, "handlers": {key: " "}}))
    assert "Blank baseline reason" in _cli(repo).stderr
    _baseline(repo)
    path.unlink()
    assert _cli(repo).returncode == 1
    _commit(repo)  # checker now exists at HEAD, but its baseline is absent
    _baseline(repo)
    assert "Prior baseline missing" in _cli(repo).stderr
    _write(repo, "invalid syntax !!!!\n")
    assert _cli(repo).returncode == 1
    _write(repo, _catch("pass"))
    _git(repo, "add", "nexus/example.py")
    (repo / "nexus/example.py").unlink()  # git-visible but unreadable
    assert _cli(repo).returncode == 1


def test_inventory_respects_scope_and_is_deterministic(repo: Path) -> None:
    _write(repo, _catch("pass"), "nexus/tracked.py")
    _git(repo, "add", "nexus/tracked.py")
    _write(repo, _catch("pass"), "nexus/untracked.py")
    _write(repo, _catch("pass"), "scripts/untracked.py")
    _write(
        repo,
        "raise RuntimeError('must not import')\n" + _catch("pass"),
        "scripts/no_import.py",
    )
    for path in (
        "nexus/ignored/no.py",
        "scripts/ignored/no.py",
        "tests/no.py",
        "migrations/no.py",
        "outside.py",
    ):
        _write(repo, _catch("pass"), path)
    first = _cli(repo, "--inventory")
    second = _cli(repo, "--inventory")
    assert first.returncode == second.returncode == 0
    assert first.stdout == second.stdout
    data = json.loads(first.stdout)
    assert {h["path"] for h in data["handlers"]} == {
        lint.CHECKER_PATH,
        "nexus/tracked.py",
        "nexus/untracked.py",
        "scripts/untracked.py",
        "scripts/no_import.py",
    }
    assert data["counts"]["by_root"] == {"nexus": 2, "scripts": 3}
    assert data["counts"]["missing_marker"] == 4


def test_canonical_encoding_rejects_unknown_shapes_and_preserves_types() -> None:
    with pytest.raises(ValueError, match="Unsupported AST node"):
        lint.canonical_ast(ast.AST())
    with pytest.raises(ValueError, match="Missing AST field"):
        call = ast.Call(func=ast.Name(id="work", ctx=ast.Load()), args=[], keywords=[])
        del call.func
        lint.canonical_ast(call)
    with pytest.raises(ValueError, match="Unsupported AST scalar shape"):
        lint.canonical_ast({"field": "value"})
    assert lint.canonical_ast(True) != lint.canonical_ast(1)
    assert lint.canonical_ast(1) != lint.canonical_ast(1.0)
    assert lint.canonical_ast([]) != lint.canonical_ast(None)
    assert lint.canonical_ast(b"x") != lint.canonical_ast("x")


def test_failed_git_command_is_not_an_empty_inventory(tmp_path: Path) -> None:
    result = _cli(tmp_path, "--inventory")
    assert result.returncode == 1
    assert result.stdout == ""


def test_repository_tree_matches_committed_baseline() -> None:
    root = CHECKER.parents[1]
    assert lint.check_tree(root, root / lint.BASELINE_PATH, "HEAD") == []
    assert lint.check_tree(root, root / lint.BASELINE_PATH, "origin/main") == []
