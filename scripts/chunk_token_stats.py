#!/usr/bin/env python3
"""
chunk_token_stats.py
--------------------

A tool to compute token count statistics for narrative chunks in the NEXUS database.

Example
-------
python chunk_token_stats.py \
    --model claude-3-7-sonnet-20250219 \
    --pct 0.1 0.25 0.75 0.9 \
    --appendix              # include per‑chunk token counts
    --out stats.json

Default values set for NEXUS:
- Uses 'narrative_chunks' table
- 'id' column for chunk ID
- 'raw_text' column for text content
- Default database parameters from environment variables or localhost settings

Dependencies
------------
pip install psycopg2-binary tiktoken
# or: pip install psycopg2-binary transformers

Notes
-----
* Supported models:
  - Anthropic: claude-3-7-sonnet-20250219, claude-3-opus-20240229, etc.
  - OpenAI: gpt-4o, gpt-4o-mini, text-embedding-3-small, etc.
  - Base encodings: cl100k_base, p50k_base, etc.
* If you prefer HuggingFace, replace `tiktoken` with
  `from transformers import AutoTokenizer` and adjust `encode_fn`.
"""

import argparse, json, os, statistics, sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Callable, List

import psycopg2

try:
    import tiktoken
except ImportError:  # pragma: no cover
    tiktoken = None


def get_db_connection_string():
    """Get the database connection string from environment variables or defaults."""
    DB_USER = os.environ.get("DB_USER", "pythagor") 
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = os.environ.get("DB_PORT", "5432")
    DB_NAME = os.environ.get("DB_NAME", "NEXUS")
    
    # Build connection string (with password if provided)
    if DB_PASSWORD:
        return f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    else:
        return f"postgresql://{DB_USER}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute token‑count stats for narrative chunks.")
    p.add_argument("--dsn", help="PostgreSQL DSN (optional, defaults to environment variables)")
    p.add_argument("--table", default="narrative_chunks", help="Table with chunk text (default: narrative_chunks)")
    p.add_argument("--id-col", default="id", help="PK column (default: id)")
    p.add_argument("--text-col", default="raw_text", help="Text column (default: raw_text)")
    p.add_argument("--where", help="Optional WHERE clause (no 'WHERE' keyword)")
    p.add_argument("--model", default="claude-3-7-sonnet-20250219", help="Tokenizer model name")
    p.add_argument("--pct", nargs="+", type=float, default=[0.1, 0.25, 0.5, 0.75, 0.9], metavar="P",
                   help="Percentiles 0<P<1 (default: 0.1 0.25 0.5 0.75 0.9)")
    p.add_argument("--appendix", action="store_true",
                   help="Include per‑chunk token counts in output")
    p.add_argument("--out", help="Write JSON to this file instead of stdout")
    p.add_argument("--limit", type=int, help="Limit number of chunks to process")
    return p.parse_args()


def make_tokenizer(model: str) -> Callable[[str], int]:
    # For Claude models, use cl100k_base encoding (same as GPT-4)
    # This is an approximation as Claude's exact tokenization isn't public
    if model.startswith("claude"):
        model_name = "cl100k_base"
    else:
        model_name = model
        
    if tiktoken:
        try:
            # Try to get the encoding directly
            enc = tiktoken.get_encoding(model_name)
        except KeyError:
            # If that fails, try to get it by model name
            try:
                enc = tiktoken.encoding_for_model(model_name)
            except KeyError:
                # If all else fails, default to cl100k_base (GPT-4/Claude3 encoding)
                print(f"⚠️  Unknown model '{model}', falling back to cl100k_base encoding", file=sys.stderr)
                enc = tiktoken.get_encoding("cl100k_base")
                
        return lambda s: len(enc.encode(s))
    
    # fallback: crude whitespace tokenizer
    print("⚠️  tiktoken not installed; using whitespace tokenizer", file=sys.stderr)
    return lambda s: len(s.split())


def fetch_chunks(cur, table: str, id_col: str, text_col: str, where: str | None, limit: int | None = None):
    q = f"SELECT {id_col}, {text_col} FROM {table}"
    if where:
        q += f" WHERE {where}"
    q += f" ORDER BY {id_col}"
    if limit:
        q += f" LIMIT {limit}"
    
    print(f"Executing query: {q}", file=sys.stderr)
    cur.execute(q)
    
    for row in cur:
        yield row[0], row[1]


def descriptive_stats(data: List[int], extra_pcts: List[float]):
    data_sorted = sorted(data)
    n = len(data_sorted)
    mean = statistics.fmean(data_sorted)
    stdev = statistics.pstdev(data_sorted) if n > 1 else 0.0
    median = statistics.median(data_sorted)

    pct_values = {p: data_sorted[int(p * (n - 1))] for p in extra_pcts if 0 < p < 1}

    return {
        "n": n,
        "min": data_sorted[0],
        "max": data_sorted[-1],
        "mean": round(mean, 2),
        "median": median,
        "stdev": round(stdev, 2),
        **{f"p{int(p*100)}": v for p, v in pct_values.items()},
    }


def main():
    args = parse_args()
    encode_len = make_tokenizer(args.model)

    # Get DSN from args or environment
    dsn = args.dsn or get_db_connection_string()
    
    print(f"Connecting to database... (model: {args.model})", file=sys.stderr)
    conn = psycopg2.connect(dsn)
    cur = conn.cursor(name="chunk_cursor")  # named cursor = streaming, low memory

    token_counts = []
    appendix = []
    
    # Track progress
    chunk_count = 0
    start_time = datetime.now()
    
    print("Fetching and processing chunks...", file=sys.stderr)
    for cid, text in fetch_chunks(cur, args.table, args.id_col, args.text_col, args.where, args.limit):
        tok_len = encode_len(text)
        token_counts.append(tok_len)
        if args.appendix:
            appendix.append({"id": cid, "tokens": tok_len})
        
        chunk_count += 1
        if chunk_count % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            print(f"Processed {chunk_count} chunks ({chunk_count/elapsed:.1f} chunks/sec)...", file=sys.stderr)

    # Calculate processing speed
    elapsed_time = (datetime.now() - start_time).total_seconds()
    rate = chunk_count / elapsed_time if elapsed_time > 0 else 0
    
    # Get summary statistics
    stats = descriptive_stats(token_counts, args.pct)
    
    # Add some more useful derived stats
    total_tokens = sum(token_counts)
    avg_processing_time = 1 / rate if rate > 0 else 0
    
    output = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "table": args.table,
        "tokenizer": args.model,
        "stats": stats,
        "total_tokens": total_tokens,
        "processing": {
            "elapsed_seconds": round(elapsed_time, 2),
            "chunks_per_second": round(rate, 2),
            "avg_seconds_per_chunk": round(avg_processing_time, 3),
        }
    }
    
    # Add batch size recommendations if we have enough data
    if len(token_counts) > 5:
        # Calculate optimal batch sizes for different contexts
        # These are rough heuristics based on typical LLM context windows
        p95_tok = token_counts[int(0.95 * (len(token_counts) - 1))]
        
        output["batch_recommendations"] = {
            "8k_context": max(1, int(8000 / p95_tok)),
            "16k_context": max(1, int(16000 / p95_tok)),
            "32k_context": max(1, int(32000 / p95_tok)),
            "100k_context": max(1, int(100000 / p95_tok)),
            "200k_context": max(1, int(200000 / p95_tok))
        }
    
    if appendix:
        output["chunks"] = appendix

    json_str = json.dumps(output, indent=2)
    if args.out:
        Path(args.out).write_text(json_str)
        print(f"Results written to {args.out}", file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()