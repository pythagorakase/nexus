"""Quote audit for the 817-S3 decision-ledger backfill.

Usage: python quote_audit.py <worktree>

Fetches every cited comment and issue fresh from GitHub with `gh api`, reads
each record under docs/decisions/, and checks every quoted block and every
inline quotation against the fetched text. It does not import the generator.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

API = "repos/pythagorakase/nexus"
URL = "https://github.com/pythagorakase/nexus/issues/"
QUOTE_LINE = re.compile(r"^>( |$)")
STRIP = re.compile(r"^> ?")

# number -> (ruling kind, argument); transcribed from the work order's table.
RULINGS: dict[str, tuple[str, object]] = {
    "0001": ("whole", [5556777011]),
    "0002": ("whole", [5556777557]),
    "0003": ("whole", [5556778630]),
    "0004": ("whole", [5565300043]),
    "0005": ("whole", [5565301694]),
    "0006": ("whole", [5565439618]),
    "0007": ("whole", [5800949507]),
    "0008": ("whole", [5800951144]),
    "0009": ("whole", [5800952750]),
    "0010": ("whole", [5800955522]),
    "0011": ("whole", [5565414838]),
    "0012": ("whole", [5565410350]),
    "0013": ("relay", [5915495413]),
    "0014": ("relay", [5915496685]),
    "0015": ("relay", [5915670598]),
    "0016": ("issue", 837),
    "0017": ("issue", 839),
    "0018": ("killed", "C003"),
    "0019": ("killed", "C014"),
    "0020": ("killed", "C030"),
    "0021": ("killed", "C063"),
    "0022": ("killed", "C068"),
    "0023": ("killed", "C100"),
    "0024": ("killed", "C102"),
    "0025": ("baseline", (2, 6)),
    "0026": ("baseline", (7, 7)),
    "0027": ("baseline", (8, 9)),
    "0028": ("baseline", (10, 10)),
    "0029": ("baseline", (11, 16)),
    "0030": ("relay", [5035538982]),
    "0031": ("relay", [5035539149]),
    "0032": ("relay", [5035539341, 5035716638]),
    "0033": ("relay", [5070275155]),
    "0034": ("relay", [5113803006, 5113867184, 5113874777]),
    "0035": ("relay", [5817898265]),
    "0036": ("relay", [5915474062]),
    "0037": ("relay", [5915474827]),
    "0038": ("relay", [5915475165]),
    "0039": ("relay", [5915474444]),
    "0040": ("relay", [5915475477]),
    "0041": ("relay", [5915494108]),
    "0042": ("relay", [5915494408]),
    "0043": ("relay", [5915494698]),
    "0044": ("relay", [5915495072]),
    "0045": ("relay", [5915495765]),
    "0046": ("relay", [5915496016]),
    "0047": ("relay", [5915496362]),
    "0048": ("relay", [5915497021]),
    "0049": ("relay", [5915497315]),
    "0050": ("relay", [5915668877]),
    "0051": ("relay", [5915669173]),
    "0052": ("relay", [5915669468]),
    "0053": ("relay", [5915669789]),
    "0054": ("relay", [5915670142]),
    "0055": ("relay", [5915671010]),
}
DECISIONS_819 = 5915950416
SUMMARY_819 = (
    "Ambiguous semantics must route to the decision ledger rather than receiving "
    "invented documentation."
)
COMMANDS: list[str] = []
_cache: dict[str, dict] = {}


def gh(path: str) -> dict:
    """Fetch one GitHub API object as JSON (its .body is the raw Markdown)."""
    if path not in _cache:
        COMMANDS.append(f"gh api {API}/{path}")
        out = subprocess.run(
            ["gh", "api", f"{API}/{path}"], capture_output=True, text=True, check=True
        ).stdout
        _cache[path] = json.loads(out)
    return _cache[path]


def comment(cid: int) -> dict:
    return gh(f"issues/comments/{cid}")


def relay_run(body: str, cid: int) -> tuple[list[str], bool]:
    """Recompute the verbatim block from the fetched body (Required Changes 3)."""
    lines = body.splitlines()
    if cid == 5817898265:  # #737: the fenced text block, lines 3-10
        return lines[2:10], True
    start = next(i for i, line in enumerate(lines) if "verbatim" in line.lower())
    j = start + 1
    while lines[j] == "":
        j += 1
    run = []
    while j < len(lines) and QUOTE_LINE.match(lines[j]):
        run.append(lines[j])
        j += 1
    return run, False


def forward(lines: list[str]) -> list[str]:
    """The quoting rule: keep '>' lines, blank -> '>', else '> ' prefix."""
    return [
        line if line.startswith(">") else (">" if line == "" else "> " + line)
        for line in lines
    ]


def paragraph(body: str, heading: str) -> list[str]:
    lines = body.splitlines()
    i = lines.index(heading) + 1
    out = []
    while i < len(lines) and lines[i] and not lines[i].startswith("#"):
        out.append(lines[i])
        i += 1
    return out


def killed(cluster: str) -> list[str]:
    lines = gh("issues/849")["body"].splitlines()
    start = next(i for i, row in enumerate(lines) if row.startswith(f"## {cluster}: "))
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")),
        len(lines),
    )
    return lines[start:end]


def record_blocks(text: str) -> list[tuple[str, str, list[str], bool]]:
    """Every (section, source, lines, fenced) block in a record body."""
    lines = text.splitlines()
    blocks = []
    section = ""
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("## "):
            section = line
        if line.startswith("Source: ") and line.endswith("."):
            source = line[len("Source: ") : -1]
            assert lines[i + 1] == "", f"blank line after {line!r}"
            j = i + 2
            if lines[j].startswith("```"):
                k = lines.index("```", j + 1)
                blocks.append((section, source, lines[j : k + 1], True))
                i = k + 1
                continue
            k = j
            while k < len(lines) and lines[k].startswith(">"):
                k += 1
            assert k > j, f"no quoted lines after {line!r}"
            assert k == len(lines) or lines[k] == "", "block not closed by a blank"
            blocks.append((section, source, lines[j:k], False))
            i = k
            continue
        i += 1
    return blocks


def expected_blocks(
    number: str, merge_base: str, baseline: list[tuple[str, str]]
) -> list[tuple[str, str, list[str], bool, str]]:
    """(section, source, source lines, fenced, kind) recomputed from the fetch."""
    kind, arg = RULINGS[number]
    R, X = "## Ruling", "## Rejected Alternatives"
    if kind == "whole":
        (cid,) = arg
        return [
            (
                R,
                comment(cid)["html_url"],
                comment(cid)["body"].splitlines(),
                False,
                "whole",
            )
        ]
    if kind == "relay":
        first, *rest = arg
        run, fenced = relay_run(comment(first)["body"], first)
        out = [(R, comment(first)["html_url"], run, fenced, "relay")]
        for cid in rest:
            out.append(
                (
                    R,
                    comment(cid)["html_url"],
                    comment(cid)["body"].splitlines(),
                    False,
                    "whole",
                )
            )
        return out
    if kind == "issue":
        data = gh(f"issues/{arg}")
        return [
            (
                R,
                data["html_url"],
                paragraph(data["body"], "## Risks"),
                False,
                "paragraph",
            )
        ]
    if kind == "killed":
        url = gh("issues/849")["html_url"]
        section = killed(arg)
        amend = [
            row for row in section if row.startswith("**Amendment / carry-forward:**")
        ]
        summary = [row for row in section if row.startswith("**Summary:**")]
        refuted = [
            row for row in section if row.startswith("- **") and ":** REFUTED " in row
        ]
        out = [
            (R, url, amend, False, "paragraph"),
            (X, url, summary, False, "paragraph"),
        ]
        out += [(X, url, [line], False, "verdict") for line in refuted]
        return out
    if kind == "baseline":
        first_line, last_line = arg
        decision_comment = comment(DECISIONS_819)
        decision = [
            row
            for row in decision_comment["body"].splitlines()
            if row.startswith("- Decision: The routing of the 29")
        ]
        assert "**819-Q1." in decision_comment["body"]
        entries = baseline[first_line - 2 : last_line - 1]
        summary = " ".join(paragraph(gh("issues/819")["body"], "## Summary"))
        assert SUMMARY_819 in summary
        return [
            (R, decision_comment["html_url"], decision, False, "line"),
            (
                R,
                f"config/schema_docs_baseline.json at {merge_base}",
                [f"{key}: {reason}" for key, reason in entries],
                False,
                "baseline",
            ),
            (X, gh("issues/819")["html_url"], [SUMMARY_819], False, "sentence"),
        ]
    raise AssertionError(kind)


INLINE = re.compile(r'^- "(.*)"\.? (?:Reason: "(.*)"|No reason recorded\.)$')
REOPEN = re.compile(r'^- "(.*)"$')


def inline_quotes(text: str, section: str) -> list[str]:
    """Every inline quotation in one section's bullets."""
    lines = text.splitlines()
    start = lines.index(section) + 1
    end = next(
        (i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines)
    )
    quotes = []
    for line in lines[start:end]:
        match = INLINE.match(line) or REOPEN.match(line)
        if match:
            quotes += [group for group in match.groups() if group]
    return quotes


def main() -> None:
    root = Path(sys.argv[1])
    merge_base = subprocess.run(
        ["git", "-C", str(root), "merge-base", "origin/main", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    baseline = list(
        json.loads((root / "config/schema_docs_baseline.json").read_text()).items()
    )
    records = sorted((root / "docs/decisions").glob("[0-9][0-9][0-9][0-9]-*.md"))
    assert [p.name[:4] for p in records] == sorted(RULINGS), "record set"
    failures = []
    rows = []
    for path in records:
        number = path.name[:4]
        text = path.read_text(encoding="utf-8")
        found = record_blocks(text)
        expected = expected_blocks(number, merge_base, baseline)
        ok = len(found) == len(expected)
        if not ok:
            failures.append(f"{number}: {len(found)} blocks, expected {len(expected)}")
        for (fsec, fsrc, flines, ffenced), (esec, esrc, elines, efenced, kind) in zip(
            found, expected
        ):
            if (fsec, fsrc, ffenced) != (esec, esrc, efenced):
                failures.append(
                    f"{number}: block header {(fsec, fsrc, ffenced)} != "
                    f"{(esec, esrc, efenced)}"
                )
                ok = False
                continue
            if ffenced:
                same = flines == elines  # the #737 fence is kept as it is
            else:
                stripped = "\n".join(STRIP.sub("", line, count=1) for line in flines)
                target = (
                    "\n".join(STRIP.sub("", line, count=1) for line in elines)
                    if kind == "relay"
                    else "\n".join(elines)
                )
                # Equality on the whole text, then byte equality of the quoting.
                same = stripped == target and flines == forward(elines)
            if not same:
                failures.append(f"{number}: block from {fsrc} differs")
                ok = False
        # Inline quotations must occur verbatim in the cited text.
        kind, arg = RULINGS[number]
        haystack = ""
        if kind in ("whole", "relay"):
            first_issue = int(re.search(r"\*\*Links:\*\* #(\d+)", text).group(1))
            haystack = (
                gh(f"issues/{first_issue}")["body"]
                + "\n"
                + "\n".join(comment(cid)["body"] for cid in arg)
            )
        elif kind == "issue":
            haystack = gh(f"issues/{arg}")["body"]
        inline = inline_quotes(text, "## Rejected Alternatives") + inline_quotes(
            text, "## Reopening Criteria"
        )
        for quote in inline:
            if quote not in haystack:
                failures.append(f"{number}: inline quotation not in source: {quote!r}")
                ok = False
        if kind == "relay" and number not in ("0033", "0044"):
            not_chosen = comment(arg[0])["body"].count("not chosen")
            bullets = sum(
                1
                for q in inline_quotes(text, "## Rejected Alternatives")
                if "not chosen" in q
            )
            if not_chosen != bullets:
                failures.append(
                    f"{number}: {bullets} not-chosen bullets, {not_chosen} in relay"
                )
                ok = False
        rows.append(
            f"| {number} | {', '.join(sorted({e[1] for e in expected}))} | "
            f"{len(found)} | {len(inline)} | {'MATCH' if ok else 'DIFFER'} |"
        )
    print("| Record | Sources | Blocks | Inline quotes | Result |")
    print("|---|---|---|---|---|")
    print("\n".join(rows))
    print()
    print("Fetch commands:")
    print("\n".join(sorted(set(COMMANDS))))
    print()
    if failures:
        print("FAILURES:")
        print("\n".join(failures))
        sys.exit(1)
    print(f"all {len(records)} records match (merge base {merge_base})")


if __name__ == "__main__":
    main()
