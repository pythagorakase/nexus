"""Inventory exception handlers and ratchet unmarked swallowing-handler debt.

Offline, stdlib-only, and source-only: scanned modules are never imported.
Canonical encoding v1 is compact UTF-8 JSON (ensure_ascii=True): AST nodes are
["node", type, [[field, value], ...]], fields sorted by name from the frozen
Python 3.11-3.13 schema below. Lists are ["list", [values...]]; scalars carry
their exact type tag, integers use decimal strings, floats use float.hex(),
complex values use two hex floats, bytes use hex, and Ellipsis has its own tag.
Empty lists and None are included. Source attributes are excluded. Only missing
type_params and type-parameter default_value are normalized, to [] and None.
Unknown nodes, fields, missing fields, and scalar shapes fail closed. Comments
and positions never enter a hash; semantic fields (including nested bodies) do.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import io
import json
import re
import subprocess
import sys
import tokenize
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = "scripts/exception_disposition_baseline.json"
CHECKER_PATH = "scripts/check_exception_dispositions.py"
SEED_REASON = (
    "Legacy swallowing handler inventoried by 806-S4; "
    "unapproved fallback defaults to fail/delete."
)
MARKER_PREFIX = "nexus-exception-disposition:"
MARKER = re.compile(
    r"# nexus-exception-disposition: "
    r"(fail|retry|degrade-read-only|safe-continuation); "
    r"reason=([^;]+); safety=([^;]+)\Z"
)
IDENTITY = re.compile(
    r"(nexus|scripts)/[^|]+\.py\|" r"(<module>|[^|]+)\|[0-9a-f]{64}\|[1-9][0-9]*\Z"
)

# Frozen schema, not the running interpreter's ast.dump or field defaults.
NODE_FIELDS: dict[str, str] = {
    "Add": "",
    "And": "",
    "AnnAssign": "annotation,simple,target,value",
    "Assert": "msg,test",
    "Assign": "targets,type_comment,value",
    "AsyncFor": "body,iter,orelse,target,type_comment",
    "AsyncFunctionDef": (
        "args,body,decorator_list,name,returns,type_comment,type_params"
    ),
    "AsyncWith": "body,items,type_comment",
    "Attribute": "attr,ctx,value",
    "AugAssign": "op,target,value",
    "AugLoad": "",
    "AugStore": "",
    "Await": "value",
    "BinOp": "left,op,right",
    "BitAnd": "",
    "BitOr": "",
    "BitXor": "",
    "BoolOp": "op,values",
    "Break": "",
    "Call": "args,func,keywords",
    "ClassDef": "bases,body,decorator_list,keywords,name,type_params",
    "Compare": "comparators,left,ops",
    "Constant": "kind,value",
    "Continue": "",
    "Del": "",
    "Delete": "targets",
    "Dict": "keys,values",
    "DictComp": "generators,key,value",
    "Div": "",
    "Eq": "",
    "ExceptHandler": "body,name,type",
    "Expr": "value",
    "Expression": "body",
    "FloorDiv": "",
    "For": "body,iter,orelse,target,type_comment",
    "FormattedValue": "conversion,format_spec,value",
    "FunctionDef": "args,body,decorator_list,name,returns,type_comment,type_params",
    "FunctionType": "argtypes,returns",
    "GeneratorExp": "elt,generators",
    "Global": "names",
    "Gt": "",
    "GtE": "",
    "If": "body,orelse,test",
    "IfExp": "body,orelse,test",
    "Import": "names",
    "ImportFrom": "level,module,names",
    "In": "",
    "Interactive": "body",
    "Invert": "",
    "Is": "",
    "IsNot": "",
    "JoinedStr": "values",
    "LShift": "",
    "Lambda": "args,body",
    "List": "ctx,elts",
    "ListComp": "elt,generators",
    "Load": "",
    "Lt": "",
    "LtE": "",
    "MatMult": "",
    "Match": "cases,subject",
    "MatchAs": "name,pattern",
    "MatchClass": "cls,kwd_attrs,kwd_patterns,patterns",
    "MatchMapping": "keys,patterns,rest",
    "MatchOr": "patterns",
    "MatchSequence": "patterns",
    "MatchSingleton": "value",
    "MatchStar": "name",
    "MatchValue": "value",
    "Mod": "",
    "Module": "body,type_ignores",
    "Mult": "",
    "Name": "ctx,id",
    "NamedExpr": "target,value",
    "Nonlocal": "names",
    "Not": "",
    "NotEq": "",
    "NotIn": "",
    "Or": "",
    "Param": "",
    "ParamSpec": "default_value,name",
    "Pass": "",
    "Pow": "",
    "RShift": "",
    "Raise": "cause,exc",
    "Return": "value",
    "Set": "elts",
    "SetComp": "elt,generators",
    "Slice": "lower,step,upper",
    "Starred": "ctx,value",
    "Store": "",
    "Sub": "",
    "Subscript": "ctx,slice,value",
    "Try": "body,finalbody,handlers,orelse",
    "TryStar": "body,finalbody,handlers,orelse",
    "Tuple": "ctx,elts",
    "TypeAlias": "name,type_params,value",
    "TypeIgnore": "lineno,tag",
    "TypeVar": "bound,default_value,name",
    "TypeVarTuple": "default_value,name",
    "UAdd": "",
    "USub": "",
    "UnaryOp": "op,operand",
    "While": "body,orelse,test",
    "With": "body,items,type_comment",
    "Yield": "value",
    "YieldFrom": "value",
    "alias": "asname,name",
    "arg": "annotation,arg,type_comment",
    "arguments": "args,defaults,kw_defaults,kwarg,kwonlyargs,posonlyargs,vararg",
    "comprehension": "ifs,is_async,iter,target",
    "keyword": "arg,value",
    "match_case": "body,guard,pattern",
    "withitem": "context_expr,optional_vars",
}


def canonical_ast(value: Any) -> Any:
    """Encode an AST with the version-independent, typed v1 representation."""
    if isinstance(value, ast.AST):
        name = type(value).__name__
        if name not in NODE_FIELDS:
            raise ValueError(f"Unsupported AST node: {name}")
        fields = NODE_FIELDS[name].split(",") if NODE_FIELDS[name] else []
        if set(value._fields) - set(fields):
            raise ValueError(f"Unsupported AST fields: {name}: {value._fields}")
        entries = []
        for field in fields:
            if hasattr(value, field):
                child = getattr(value, field)
            elif field == "type_params" and name in {
                "FunctionDef",
                "AsyncFunctionDef",
                "ClassDef",
            }:
                child = []
            elif field == "default_value" and name in {
                "TypeVar",
                "ParamSpec",
                "TypeVarTuple",
            }:
                child = None
            else:
                raise ValueError(f"Missing AST field: {name}.{field}")
            entries.append([field, canonical_ast(child)])
        return ["node", name, entries]
    if isinstance(value, list):
        return ["list", [canonical_ast(child) for child in value]]
    if value is None:
        return ["none"]
    if value is Ellipsis:
        return ["ellipsis"]
    if type(value) is bool:
        return ["bool", value]
    if type(value) is int:
        return ["int", str(value)]
    if type(value) is float:
        return ["float", value.hex()]
    if type(value) is complex:
        return ["complex", value.real.hex(), value.imag.hex()]
    if type(value) is str:
        return ["str", value]
    if type(value) is bytes:
        return ["bytes", value.hex()]
    raise ValueError(f"Unsupported AST scalar shape: {type(value).__name__}")


def handler_hash(handler: ast.ExceptHandler) -> str:
    """Hash a handler, without interpreter-dependent dumps or source positions."""
    encoded = json.dumps(canonical_ast(handler), separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _contains_yield(node: ast.AST) -> bool:
    if isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
    ):
        return False
    return isinstance(node, (ast.Yield, ast.YieldFrom)) or any(
        _contains_yield(child) for child in ast.iter_child_nodes(node)
    )


def _evaluated_yields(node: ast.AST) -> bool:
    # Inspect headers/defaults/decorators as well as direct expressions, while
    # leaving compound statement bodies to the ordered control-flow analysis.
    if isinstance(node, ast.expr):
        return _contains_yield(node)
    for _, value in ast.iter_fields(node):
        children = value if isinstance(value, list) else [value]
        for child in children:
            if isinstance(child, ast.AST) and not isinstance(child, ast.stmt):
                if _evaluated_yields(child):
                    return True
    return False


def sequence_exits(statements: list[ast.stmt]) -> set[str]:
    """Follow reachable statement sequences, retaining every non-raising exit."""
    exits = {"complete"}
    for statement in statements:
        if "complete" not in exits:
            break
        exits = (exits - {"complete"}) | _statement_exits(statement)
    return exits


def _statement_exits(node: ast.stmt) -> set[str]:
    # Suspension is observable even if the resumed path eventually raises.
    if isinstance(node, ast.Raise):
        exits = {"raise"}
    elif isinstance(node, ast.Return):
        exits = {"return"}
    elif isinstance(node, ast.Break):
        exits = {"break"}
    elif isinstance(node, ast.Continue):
        exits = {"continue"}
    elif isinstance(node, ast.If):
        exits = sequence_exits(node.body) | sequence_exits(node.orelse)
    elif isinstance(node, (ast.Try, ast.TryStar)):
        exits = sequence_exits(node.body)
        if "complete" in exits:
            exits = (exits - {"complete"}) | sequence_exits(node.orelse)
        # Calls and other expressions may throw even without an explicit raise.
        # Keep an unmatched exception path; no exception-type inference is used.
        for handler in node.handlers:
            exits |= sequence_exits(handler.body)
        if node.handlers:
            exits.add("raise")
        final = sequence_exits(node.finalbody)
        exits = (exits if "complete" in final else exits & {"suspend"}) | (
            final - {"complete"}
        )
    elif isinstance(node, (ast.With, ast.AsyncWith)):
        exits = sequence_exits(node.body)
        if "raise" in exits:
            exits.add("complete")  # __exit__ may suppress the exception.
    elif isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
        body = sequence_exits(node.body)
        exits = sequence_exits(node.orelse) | (body - {"complete", "continue", "break"})
        if "break" in body:
            exits.add("complete")
    elif isinstance(node, ast.Match):
        exits = set()
        for case in node.cases:
            exits |= sequence_exits(case.body)
        last = node.cases[-1]
        if not (
            last.guard is None
            and isinstance(last.pattern, ast.MatchAs)
            and last.pattern.pattern is None
        ):
            exits.add("complete")
    else:
        # Nested definitions do not execute their bodies here. Any remaining
        # compound form may complete; preserve its possible non-raising exits.
        exits = {"complete"}
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for _, value in ast.iter_fields(node):
                if (
                    isinstance(value, list)
                    and value
                    and all(isinstance(child, ast.stmt) for child in value)
                ):
                    exits |= sequence_exits(value)
    # Compound bodies handle suspension in sequence order; don't inspect their
    # unreachable descendants. Only inspect directly evaluated expressions.
    if _evaluated_yields(node):
        exits.add("suspend")
    return exits


@dataclass(frozen=True)
class Handler:
    """One source handler, its identity, and its declared contract (if any)."""

    identity: str
    path: str
    line: int
    scope: str
    caught_type: str
    ast_exempt: bool
    marker: dict[str, str] | None


def _git(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True
    ).stdout


def _header_marker(
    handler: ast.ExceptHandler, tokens: list[tokenize.TokenInfo], path: str
) -> dict[str, str] | None:
    start = (handler.lineno, handler.col_offset)
    body = handler.body[0]
    end = (body.lineno, body.col_offset)
    colons = [
        token
        for token in tokens
        if start <= token.start < end
        and token.type == tokenize.OP
        and token.string == ":"
    ]
    if not colons:
        raise ValueError(f"{path}:{handler.lineno}: handler header colon not found")
    line = colons[-1].start[0]
    comments = [
        token.string
        for token in tokens
        if token.type == tokenize.COMMENT and token.start[0] == line
    ]
    for comment in comments:
        if MARKER_PREFIX in comment:
            match = MARKER.fullmatch(comment)
            if not match or not all(part.strip() for part in match.groups()[1:]):
                raise ValueError(f"{path}:{line}: invalid exception disposition marker")
            kind, reason, safety = match.groups()
            return {"kind": kind, "reason": reason.strip(), "safety": safety.strip()}
    return None


def collect_handlers(root: Path) -> list[Handler]:
    """Inventory git-visible Python source in nexus/ and scripts/, in order."""
    paths = sorted(
        set(
            _git(
                root,
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
                "-z",
                "--",
                "nexus",
                "scripts",
            )
            .decode("utf-8")
            .split("\0")
        )
        - {""}
    )
    result: list[Handler] = []
    for path in paths:
        if not path.endswith(".py"):
            continue
        with tokenize.open(root / path) as source_file:
            source = source_file.read()
        tree = ast.parse(source, filename=path)
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
        occurrences: Counter[tuple[str, str]] = Counter()
        pending: list[tuple[ast.ExceptHandler, str]] = []

        def visit(node: ast.AST, scope: tuple[str, ...]) -> None:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                scope = (*scope, node.name)
            if isinstance(node, ast.ExceptHandler):
                pending.append((node, ".".join(scope) or "<module>"))
            for child in ast.iter_child_nodes(node):
                visit(child, scope)

        visit(tree, ())
        for handler, scope in sorted(
            pending, key=lambda pair: (pair[0].lineno, pair[0].col_offset)
        ):
            digest = handler_hash(handler)
            occurrences[scope, digest] += 1
            result.append(
                Handler(
                    f"{path}|{scope}|{digest}|{occurrences[scope, digest]}",
                    path,
                    handler.lineno,
                    scope,
                    ast.unparse(handler.type) if handler.type else "<bare>",
                    sequence_exits(handler.body) == {"raise"},
                    _header_marker(handler, tokens, path),
                )
            )
    return result


def inventory(handlers: list[Handler]) -> dict[str, Any]:
    """Return deterministic handler records and independent census counts."""

    def counts(values: list[str]) -> dict[str, int]:
        return dict(sorted(Counter(values).items()))

    return {
        "handlers": [asdict(handler) for handler in handlers],
        "counts": {
            "total": len(handlers),
            "by_root": counts([h.path.split("/")[0] for h in handlers]),
            "by_caught_type": counts([h.caught_type for h in handlers]),
            "by_exemption": counts(
                ["always-raises" if h.ast_exempt else "not-exempt" for h in handlers]
            ),
            "by_disposition": counts(
                [h.marker["kind"] if h.marker else "unmarked" for h in handlers]
            ),
            "missing_marker": sum(
                not h.ast_exempt and h.marker is None for h in handlers
            ),
        },
    }


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate baseline key: {key}")
        result[key] = value
    return result


def load_baseline(source: str) -> dict[str, str]:
    """Validate the complete JSON schema, including duplicate keys."""
    data = json.loads(source, object_pairs_hook=_unique_object)
    if not isinstance(data, dict) or set(data) != {"schema_version", "handlers"}:
        raise ValueError("Invalid baseline schema")
    if type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("Unsupported baseline schema_version")
    handlers = data["handlers"]
    if not isinstance(handlers, dict):
        raise ValueError("Baseline handlers must be an object")
    for key, reason in handlers.items():
        if not IDENTITY.fullmatch(key):
            raise ValueError(f"Malformed baseline identity: {key}")
        path, scope, _, _ = key.split("|")
        if (
            Path(path).as_posix() != path
            or ".." in Path(path).parts
            or (
                scope != "<module>"
                and not all(name.isidentifier() for name in scope.split("."))
            )
        ):
            raise ValueError(f"Malformed baseline identity: {key}")
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(f"Blank baseline reason: {key}")
    return dict(handlers)


def _prior_baseline(root: Path, path: str, ref: str) -> dict[str, str] | None:
    # Resolve first: a nonexistent ref must never become a bootstrap exemption.
    commit = _git(root, "rev-parse", "--verify", f"{ref}^{{commit}}")
    revision = commit.decode().strip()
    if _git(root, "ls-tree", "-z", revision, "--", path):
        return load_baseline(_git(root, "show", f"{revision}:{path}").decode())
    if _git(root, "ls-tree", "-z", revision, "--", CHECKER_PATH):
        raise ValueError(f"Prior baseline missing at {ref}; checker already exists")
    return None


def check_tree(root: Path, baseline: Path, base_ref: str) -> list[str]:
    """Check exact coverage and key-by-key shrinkage against a real git ref."""
    handlers = collect_handlers(root)
    current = load_baseline(baseline.read_text(encoding="utf-8"))
    prior = _prior_baseline(root, baseline.relative_to(root).as_posix(), base_ref)
    missing = {h.identity: h for h in handlers if not h.ast_exempt and not h.marker}
    locations = {h.identity: f"{h.path}:{h.line}" for h in handlers}

    def location(key: str) -> str:
        return locations.get(key, f"{key.split('|')[0]}:1")

    findings = [
        f"{location(key)}: missing exception disposition: {key}"
        for key in missing.keys() - current.keys()
    ]
    findings += [
        f"{location(key)}: stale exception disposition baseline entry: {key}"
        for key in current.keys() - missing.keys()
    ]
    if prior is not None:
        findings += [
            f"{location(key)}: baseline growth forbidden: {key}"
            for key in current.keys() - prior.keys()
        ]
        findings += [
            f"{location(key)}: retained baseline reason changed: {key}"
            for key in current.keys() & prior.keys()
            if current[key] != prior[key]
        ]
    return sorted(findings)


def main(argv: list[str] | None = None) -> int:
    """Print deterministic inventory or enforce the shrink-only lint."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT)
    parser.add_argument("--baseline", type=Path, default=Path(BASELINE_PATH))
    parser.add_argument("--baseline-base-ref", default="HEAD")
    parser.add_argument("--inventory", action="store_true")
    args = parser.parse_args(argv)
    root = args.root.resolve()
    baseline = (root / args.baseline).resolve()
    try:
        if args.inventory:
            print(
                json.dumps(inventory(collect_handlers(root)), indent=2, sort_keys=True)
            )
            return 0
        findings = check_tree(root, baseline, args.baseline_base_ref)
    except (
        OSError,
        ValueError,
        SyntaxError,
        tokenize.TokenError,
        subprocess.CalledProcessError,
    ) as error:  # nexus-exception-disposition: fail; reason=lint error; safety=exit 1
        print(f"{baseline.relative_to(root)}:1: {error}", file=sys.stderr)
        return 1
    for finding in findings:
        print(finding, file=sys.stderr)
    if findings:
        return 1
    print("OK: exception disposition coverage and shrink-only baseline verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
