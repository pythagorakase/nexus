#!/usr/bin/env python3
import argparse
import sys
import tiktoken
from pathlib import Path

def count_tokens(text: str, encoding) -> int:
    """Encodes the provided text and returns the estimated token count."""
    tokens = encoding.encode(text)
    return len(tokens)

def main():
    parser = argparse.ArgumentParser(description="Count tokens in provided file(s) or piped input using tiktoken.")
    parser.add_argument("files", nargs="*", help="Path(s) to text files (e.g., .txt, .json, .md) to count tokens for")
    parser.add_argument("--model", default="gpt-4o", help="Model encoding to use (default: gpt-4o)")
    args = parser.parse_args()

    # Get the encoder for the specified model.
    encoding = tiktoken.encoding_for_model(args.model)

    total_tokens = 0

    # If input is piped, read from stdin
    if not sys.stdin.isatty():
        piped_text = sys.stdin.read()
        token_count = count_tokens(piped_text, encoding)
        print(f"Estimated tokens for piped input: {token_count}")
        total_tokens += token_count

    # If files are provided, process them as well
    for file_name in args.files:
        file_path = Path(file_name)
        if not file_path.exists():
            print(f"File not found: {file_path}")
            continue
        text = file_path.read_text(encoding="utf-8")
        token_count = count_tokens(text, encoding)
        print(f"Estimated tokens for {file_path.name}: {token_count}")
        total_tokens += token_count

    print(f"\nTotal estimated tokens: {total_tokens}")

if __name__ == "__main__":
    main()
