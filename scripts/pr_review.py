#!/usr/bin/env python3
"""
Fetch comments from the newest PR and save to temp/pr_review.md
"""

import json
import subprocess
from pathlib import Path


def get_newest_pr_number() -> int:
    """Get the number of the most recent PR."""
    result = subprocess.run(
        ["gh", "pr", "list", "--limit", "1", "--json", "number"],
        capture_output=True,
        text=True,
        check=True,
    )

    prs = json.loads(result.stdout)
    if not prs:
        raise ValueError("No PRs found")

    return prs[0]["number"]


def fetch_pr_comments(pr_number: int) -> str:
    """Fetch all comments from the specified PR."""
    result = subprocess.run(
        ["gh", "pr", "view", str(pr_number), "--json", "number,title,body,comments"],
        capture_output=True,
        text=True,
        check=True,
    )

    pr_data = json.loads(result.stdout)

    # Build markdown output
    output = f"# PR #{pr_data['number']}: {pr_data['title']}\n\n"
    output += "## Description\n\n"
    output += f"{pr_data['body'] or '(No description)'}\n\n"
    output += "## Comments\n\n"

    comments = pr_data.get("comments", [])
    if not comments:
        output += "(No comments)\n"
    else:
        for comment in comments:
            author = comment.get("author", {}).get("login", "Unknown")
            body = comment.get("body", "")
            created_at = comment.get("createdAt", "")

            output += f"### {author} - {created_at}\n\n"
            output += f"{body}\n\n"
            output += "---\n\n"

    return output


def main() -> None:
    """Main entry point."""
    # Get newest PR
    pr_number = get_newest_pr_number()
    print(f"Fetching comments from PR #{pr_number}...")

    # Fetch comments
    comments_md = fetch_pr_comments(pr_number)

    # Ensure temp directory exists
    temp_dir = Path("temp")
    temp_dir.mkdir(exist_ok=True)

    # Write to file
    output_file = temp_dir / "pr_review.md"
    output_file.write_text(comments_md)

    print(f"Comments saved to {output_file}")


if __name__ == "__main__":
    main()
