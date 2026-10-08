"""Table and fixed-text check for the 817-S3 decision-ledger backfill.

Usage: python table_check.py <worktree> [<work order .md>]

The work order defaults to order_817_S3.md next to this script: the order's
"Required Changes" section, committed so that the check runs from the branch
alone. Parses the work order's record table and the fixed text of its Required
Changes 3, and compares every record under docs/decisions/ with them: the file
name, the front matter (status, sources in order, verified_commit, the 0030 to
0005 supersession), the title, Kind and Links lines, the Ruling lead-in lines,
every Rejected Alternatives bullet and every Reopening Criteria bullet. Fixed
bullets must be equal to the order's text. Quoted bullets must be equal to the
whole sentence the order names, recomputed from a fresh `gh api` fetch. Quoted
blocks are the quote audit's job (quote_audit.py); this check only requires
that every other line of a section is a lead-in, a `Source:` line or a bullet.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

API = "repos/pythagorakase/nexus"
DEFAULT_ORDER = Path(__file__).resolve().parent / "order_817_S3.md"
USAGE = "usage: python table_check.py <worktree> [<work order .md>]"
SECTIONS = ("## Ruling", "## Rejected Alternatives", "## Reopening Criteria")
NONE_RECORDED = "- None recorded in the public relay."
SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
BOLD_LABEL = re.compile(r"^- \*\*(.+?)\*\* ")
QUOTED = re.compile(r'^- "(.*)"\.? (Reason: "(.*)"|No reason recorded\.)$')
RELAY_ROWS = [f"{n:04d}" for n in [13, 14, 15, *range(30, 56)]]
_cache: dict[str, dict] = {}


def gh(path: str) -> dict:
    """Fetch one GitHub API object as JSON (its .body is the raw Markdown)."""
    if path not in _cache:
        out = subprocess.run(
            ["gh", "api", f"{API}/{path}"], capture_output=True, text=True, check=True
        ).stdout
        _cache[path] = json.loads(out)
    return _cache[path]


def first_comment(row: dict[str, object]) -> str:
    """The id of the first ``c<ID>`` comment in a table row's Ruling Text."""
    return str(row["ruling"]).split(",")[0].strip()[1:]


def rows_of(numbers: str) -> list[str]:
    """Expand ``0016-0017`` or ``0030`` into record numbers."""
    first, _, last = numbers.partition("-")
    return [f"{n:04d}" for n in range(int(first), int(last or first) + 1)]


def order_table(order: str) -> dict[str, dict[str, object]]:
    """The order's record table, keyed by record number."""
    table: dict[str, dict[str, object]] = {}
    for line in order.splitlines():
        if not re.match(r"^\| \d{4} \|", line):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        number, slug, title, kind, links, ruling, sources = cells
        table[number] = {
            "slug": slug,
            "title": title,
            "kind": kind,
            "links": links,
            "ruling": ruling,
            "sources": [source.strip() for source in sources.split(",")],
        }
    return table


def order_bullet(order: str, heading: str) -> str:
    """The text of one of the three sub-bullets of Required Changes 3."""
    start = order.index(f"   - **{heading}.**")
    ends = [
        order.index(f"   - **{other}.**")
        for other in ("Ruling", "Rejected Alternatives", "Reopening Criteria")
        if order.index(f"   - **{other}.**") > start
    ]
    end = min(ends) if ends else order.index("\n4. ", start)
    return order[start:end]


def fixed_text(order: str) -> tuple[dict[str, str], dict[str, list[str]], dict]:
    """Lead-ins, fixed Rejected bullets and Reopening rules from the order."""
    ruling = order_bullet(order, "Ruling")
    leads = {
        row: text
        for numbers, text in re.findall(r"Rows (\d{4}-\d{4}): `([^`]+)`", ruling)
        for row in rows_of(numbers)
    }
    rejected = order_bullet(order, "Rejected Alternatives")
    bullets: dict[str, list[str]] = {}
    for first, second, text in re.findall(
        r"(\d{4})(?: and (\d{4}))?: `(- [^`]+)`", rejected
    ):
        for row in filter(None, (first, second)):
            bullets[row] = [text]
    assert "including 0016-0017), use the single bullet `" + NONE_RECORDED in rejected
    for row in rows_of("0016-0017"):
        bullets[row] = [NONE_RECORDED]
    single = re.search(r"Rows 0025-0029: the single bullet `(- [^`]+)`", rejected)
    for row in rows_of("0025-0029"):
        bullets[row] = [single.group(1)]
    for row in rows_of("0018-0024"):
        bullets[row] = []  # Summary and REFUTED lines are quoted blocks only
    reopening = order_bullet(order, "Reopening Criteria")
    reopen: dict = {}
    for numbers, text in re.findall(r"Rows? (\d{4}(?:-\d{4})?): `([^`]+)`", reopening):
        for row in rows_of(numbers):
            reopen[row] = text
    reopen["other"] = re.search(r"Every other row: `([^`]+)`", reopening).group(1)
    reopen["state"] = 'last sentence of the relay\'s "State of this issue." bullet'
    assert reopen["state"] in reopening
    for row, issue, prefix in (("0016", 837, "Add per-stage timing"),):
        assert f'#{issue} Verifier Amendments sentence beginning "{prefix}"' in (
            reopening
        )
        reopen[row] = (issue, prefix)
    assert '#839 sentence beginning "Require confirmation"' in reopening
    reopen["0017"] = (839, "Require confirmation")
    return leads, bullets, reopen


def sentences(line: str) -> list[str]:
    """Split one bullet line, without its marker and bold label, into sentences."""
    text = BOLD_LABEL.sub("", line)
    text = text[2:] if text.startswith("- ") else text
    return [part for part in SENTENCE_END.split(text.strip()) if part]


def section(body: list[str], heading: str) -> list[str]:
    """The non-blank lines of one ``##`` section."""
    start = body.index(heading) + 1
    end = next(
        (i for i in range(start, len(body)) if body[i].startswith("## ")), len(body)
    )
    return [line for line in body[start:end] if line.strip()]


def prose(lines: list[str]) -> list[str]:
    """The lines of a section that are neither quoted nor inside a fence."""
    out = []
    fenced = False
    for line in lines:
        if line.startswith("```"):
            fenced = not fenced
            continue
        if fenced or line.startswith(">"):
            continue
        out.append(line)
    return out


def check(root: Path, order_path: Path) -> list[str]:
    """Compare every record with the order; return one line per mismatch."""
    order = order_path.read_text(encoding="utf-8")
    table = order_table(order)
    leads, bullets, reopen = fixed_text(order)
    merge_base = subprocess.run(
        ["git", "-C", str(root), "merge-base", "origin/main", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    files = sorted(p.name for p in (root / "docs/decisions").glob("*.md"))
    expected_files = sorted(
        [f"{n}-{row['slug']}.md" for n, row in table.items()] + ["README.md"]
    )
    errors = []
    if files != expected_files:
        errors.append(f"files {sorted(set(files) ^ set(expected_files))}")
    print(f"order table rows: {len(table)}; files under docs/decisions/: {len(files)}")
    fixed_reopen = [
        k for k, v in reopen.items() if k[0].isdigit() and isinstance(v, str)
    ]
    print(
        f"lead-ins: {len(leads)}; fixed Rejected rows: {len(bullets)}; "
        f"fixed Reopening rows: {len(fixed_reopen)}"
    )
    print()
    print(
        "| Record | Front matter | Title, Kind, Links | Ruling | Rejected | Reopening |"
    )
    print("|---|---|---|---|---|---|")
    for number, row in table.items():
        path = root / "docs/decisions" / f"{number}-{row['slug']}.md"
        text = path.read_text(encoding="utf-8")
        _, front, rest = text.split("---\n", 2)
        meta = yaml.safe_load(front)
        want = {
            "status": "superseded" if number == "0030" else "canonical",
            "sources": row["sources"],
            "verified_commit": merge_base,
        }
        if number == "0030":
            want["superseded_by"] = "docs/decisions/0005-passive-drift.md"
        if number == "0005":
            want["supersedes"] = ["docs/decisions/0030-relationship-drift.md"]
        result = {}
        result["front"] = meta == want and list(meta) == list(want)
        body = rest.splitlines()
        head = body[:6]
        result["head"] = head == [
            "",
            f"# {number}: {row['title']}",
            "",
            f"**Kind:** {row['kind']}",
            f"**Links:** {row['links']}",
            "",
        ] and [line for line in body if line.startswith("## ")] == list(SECTIONS)

        ruling = prose(section(body, "## Ruling"))
        lead = [leads[number]] if number in leads else []
        result["ruling"] = ruling[: len(lead)] == lead and all(
            line.startswith("Source: ") for line in ruling[len(lead) :]
        )

        rejected = prose(section(body, "## Rejected Alternatives"))
        listed = [line for line in rejected if line.startswith("- ")]
        others = [line for line in rejected if not line.startswith("- ")]
        rejected_ok = all(line.startswith("Source: ") for line in others)
        if number in bullets:
            rejected_ok &= listed == bullets[number]
        else:  # a relay row: one bullet per "not chosen" sentence, whole
            relay = gh(f"issues/comments/{first_comment(row)}")["body"]
            said = [
                sentence
                for line in relay.splitlines()
                for sentence in sentences(line)
                if "not chosen" in sentence
            ]
            if not said:
                rejected_ok &= listed == [NONE_RECORDED]
            else:
                matches = [QUOTED.match(line) for line in listed]
                rejected_ok &= all(matches) and [m.group(1) for m in matches] == said
                for match in filter(None, matches):
                    reason = match.group(3)
                    # A quoted reason comes from the sentence itself.
                    rejected_ok &= reason is None or reason in match.group(1)
                    # A sentence with an explicit "because" must carry it.
                    rejected_ok &= not (reason is None and "because" in match.group(1))
        result["rejected"] = rejected_ok

        reopening = prose(section(body, "## Reopening Criteria"))
        if number in reopen and isinstance(reopen[number], str):
            want_reopen = [reopen[number]]
        elif number in ("0016", "0017"):
            issue, prefix = reopen[number]
            found = [
                sentence
                for line in gh(f"issues/{issue}")["body"].splitlines()
                for sentence in sentences(line)
                if sentence.startswith(prefix)
            ]
            assert len(found) == 1, (number, found)
            want_reopen = [f'- "{found[0]}"']
        elif number in ("0013", "0014", "0015"):
            relay = gh(f"issues/comments/{first_comment(row)}")["body"]
            state = [
                line
                for line in relay.splitlines()
                if line.startswith("- **State of this issue.** ")
            ]
            assert len(state) == 1, (number, state)
            want_reopen = [f'- "{sentences(state[0])[-1]}"']
        else:
            want_reopen = [reopen["other"]]
        result["reopen"] = reopening == want_reopen

        for key, ok in result.items():
            if not ok:
                errors.append(f"{number}: {key} differs from the order")
        cells = ["ok" if result[k] else "DIFFER" for k in result]
        cells[2] = f"{cells[2]} ({'lead-in, ' if lead else ''}Source lines)"
        cells[3] = f"{cells[3]} ({len(listed)} bullet{'s' * (len(listed) != 1)})"
        print(f"| {number} | " + " | ".join(cells) + " |")
    return errors


def main() -> None:
    """Run the check and print the table, then the verdict."""
    if len(sys.argv) not in (2, 3):
        sys.exit(USAGE)
    root = Path(sys.argv[1])
    order_path = Path(sys.argv[2]) if len(sys.argv) == 3 else DEFAULT_ORDER
    print(f"order: {order_path.name}")
    errors = check(root, order_path)
    print()
    if errors:
        print("MISMATCHES:")
        print("\n".join(errors))
        sys.exit(1)
    print("mismatches: 0")


if __name__ == "__main__":
    main()
