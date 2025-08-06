#!/usr/bin/env python3
"""
Transcript Chunker Script (Updated for Three-Digit Chunk Numbers)

This script processes Markdown transcript files and inserts scene markers
to break the transcript into smaller chunks for further processing.

Rules:
1. Every season/episode heading (lines starting with "# SxxExx:") begins a new chunk.
2. Every "## Storyteller" heading starts a new chunk unless it immediately follows
   a season/episode heading (only blank lines in between).

The chunk marker is inserted as a Markdown comment with the chunk ID (e.g., S02E07_001).

Usage:
    python transcript_chunker.py [file1.md file2.md ...]
If no file arguments are provided, all ".md" files in the current directory are processed.
"""

import sys
import re
import glob
from pathlib import Path

# Regex patterns for episode and storyteller headings.
EPISODE_REGEX = re.compile(r'^#\s*(S\d+E\d+):', re.IGNORECASE)
STORYTELLER_REGEX = re.compile(r'^##\s*Storyteller', re.IGNORECASE)

def process_file(file_path: Path):
    with file_path.open("r", encoding="utf-8") as f:
        lines = f.readlines()

    current_episode = "UNKNOWN"
    scene_count = 0
    output_lines = []
    skip_storyteller_marker = False  # Flag to avoid duplicating marker for initial storyteller headings

    for line in lines:
        stripped_line = line.strip()
        # Check for a season/episode heading.
        ep_match = EPISODE_REGEX.match(stripped_line)
        if ep_match:
            current_episode = ep_match.group(1).upper()
            scene_count = 0  # Reset scene count for new episode.
            scene_count += 1
            chunk_id = f"{current_episode}_{scene_count:03d}"  # Now three digits
            marker = f"<!-- SCENE BREAK: {chunk_id} (episode heading) -->\n"
            output_lines.append(marker)
            output_lines.append(line)
            skip_storyteller_marker = True
            continue

        # If the line is blank, just append it (do not reset the flag).
        if not stripped_line:
            output_lines.append(line)
            continue

        # Check for a "## Storyteller" heading.
        st_match = STORYTELLER_REGEX.match(stripped_line)
        if st_match:
            if not skip_storyteller_marker:
                scene_count += 1
                chunk_id = f"{current_episode}_{scene_count:03d}"  # Now three digits
                marker = f"<!-- SCENE BREAK: {chunk_id} (storyteller heading) -->\n"
                output_lines.append(marker)
            else:
                # Reset flag; we're now past the immediate post-episode position.
                skip_storyteller_marker = False
            output_lines.append(line)
            continue

        # For all other lines, append the line and reset the skip flag.
        output_lines.append(line)
        skip_storyteller_marker = False

    # Write the processed transcript to a new file.
    new_filename = file_path.stem + "_chunked" + file_path.suffix
    output_path = file_path.parent / new_filename
    with output_path.open("w", encoding="utf-8") as f:
        f.writelines(output_lines)

    print(f"Processed '{file_path}' → '{output_path}'")

def main():
    # Determine which files to process: use command-line arguments or all .md files in the directory.
    if len(sys.argv) > 1:
        file_paths = [Path(arg) for arg in sys.argv[1:]]
    else:
        file_paths = [Path(p) for p in glob.glob("*.md")]

    if not file_paths:
        print("No Markdown files found to process.")
        return

    for file_path in file_paths:
        if file_path.is_file():
            process_file(file_path)
        else:
            print(f"Warning: {file_path} is not a valid file. Skipping.")

if __name__ == "__main__":
    main()
