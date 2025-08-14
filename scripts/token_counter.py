#!/usr/bin/env python3
import argparse
import sys
import tiktoken
import chardet
import mimetypes
import json
import os
from pathlib import Path
from typing import Optional

def count_tokens(text: str, encoding) -> int:
    """Encodes the provided text and returns the estimated token count."""
    tokens = encoding.encode(text)
    return len(tokens)

def detect_encoding(file_path: Path) -> str:
    """Detect the encoding of a file using chardet."""
    with open(file_path, 'rb') as f:
        raw_data = f.read(10000)  # Read first 10KB for detection
        result = chardet.detect(raw_data)
        return result['encoding'] or 'utf-8'

def read_file_with_fallback(file_path: Path) -> Optional[str]:
    """Read a file with automatic encoding detection and fallback strategies."""
    # Special handling for PDF files
    if file_path.suffix.lower() == '.pdf':
        try:
            import PyPDF2
            with open(file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                full_text = []
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    full_text.append(page.extract_text())
                return '\n'.join(full_text)
        except ImportError:
            print(f"Warning: PyPDF2 not installed. Cannot read .pdf files.")
            print(f"Install with: pip install PyPDF2")
            return None
        except Exception as e:
            print(f"Error reading PDF file {file_path.name}: {e}")
            return None
    
    # Check if it's a binary file type we should skip (excluding PDFs now)
    mime_type, _ = mimetypes.guess_type(str(file_path))
    if mime_type and (
        mime_type.startswith('image/') or 
        mime_type.startswith('video/') or 
        mime_type.startswith('audio/') or
        mime_type in ['application/zip', 'application/x-rar']
    ):
        print(f"Skipping binary file: {file_path.name} ({mime_type})")
        return None
    
    # Special handling for .docx files
    if file_path.suffix.lower() == '.docx':
        try:
            from docx import Document
            doc = Document(file_path)
            full_text = []
            for paragraph in doc.paragraphs:
                full_text.append(paragraph.text)
            return '\n'.join(full_text)
        except ImportError:
            print(f"Warning: python-docx not installed. Cannot read .docx files.")
            print(f"Install with: pip install python-docx")
            return None
        except Exception as e:
            print(f"Error reading .docx file {file_path.name}: {e}")
            return None
    
    # Try UTF-8 first (most common)
    try:
        return file_path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        pass
    
    # Try to detect encoding
    try:
        detected_encoding = detect_encoding(file_path)
        print(f"Detected encoding for {file_path.name}: {detected_encoding}")
        return file_path.read_text(encoding=detected_encoding)
    except Exception as e:
        pass
    
    # Common fallback encodings
    fallback_encodings = ['latin-1', 'windows-1252', 'iso-8859-1', 'cp1252', 'utf-16']
    for encoding in fallback_encodings:
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    
    # Last resort: read with errors='ignore'
    try:
        return file_path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        print(f"Error reading file {file_path.name}: {e}")
        return None

def get_target_model() -> str:
    """Get the target model from settings.json for accurate token counting."""
    # Find settings.json by looking up from script location
    script_dir = Path(__file__).parent
    nexus_root = script_dir.parent
    settings_path = nexus_root / "settings.json"
    
    if settings_path.exists():
        try:
            with open(settings_path, 'r') as f:
                settings = json.load(f)
                target_model = settings.get("Agent Settings", {}).get("LOGON", {}).get("apex_AI", {}).get("model", {}).get("target_model")
                if target_model:
                    # Map model names to tiktoken-compatible names
                    model_map = {
                        "gpt-5": "gpt-4o",  # Use gpt-4o encoding until gpt-5 is officially supported
                        "claude-opus-4-1": "gpt-4o",  # Claude uses similar tokenization
                        "claude-opus-4-0": "gpt-4o",
                        "claude-sonnet-4-0": "gpt-4o"
                    }
                    return model_map.get(target_model, target_model)
        except Exception as e:
            pass
    
    # Default fallback
    return "gpt-4o"

def main():
    parser = argparse.ArgumentParser(
        description="Count tokens in provided file(s) or piped input using tiktoken.",
        epilog="Supports various text formats including .txt, .json, .md, .py, .docx, .pdf, etc."
    )
    parser.add_argument("files", nargs="*", help="Path(s) to files to count tokens for")
    parser.add_argument("--model", default=None, help="Model encoding to use (default: from settings.json)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show verbose output")
    args = parser.parse_args()

    # Use specified model or get from settings
    model_name = args.model if args.model else get_target_model()
    if args.verbose:
        print(f"Using tokenizer for model: {model_name}")
    
    # Get the encoder for the specified model.
    encoding = tiktoken.encoding_for_model(model_name)

    total_tokens = 0

    # If input is piped, read from stdin
    if not sys.stdin.isatty():
        piped_text = sys.stdin.read()
        token_count = count_tokens(piped_text, encoding)
        print(f"Estimated tokens for piped input: {token_count}")
        total_tokens += token_count

    # If files are provided, process them as well
    processed_files = 0
    for file_name in args.files:
        file_path = Path(file_name)
        if not file_path.exists():
            print(f"File not found: {file_path}")
            continue
        
        if file_path.is_dir():
            print(f"Skipping directory: {file_path}")
            continue
        
        if args.verbose:
            print(f"Processing: {file_path}...")
        
        text = read_file_with_fallback(file_path)
        if text is None:
            continue
        
        token_count = count_tokens(text, encoding)
        print(f"Estimated tokens for {file_path.name}: {token_count:,}")
        total_tokens += token_count
        processed_files += 1

    if processed_files > 1 or (processed_files > 0 and not sys.stdin.isatty()):
        print(f"\nTotal estimated tokens: {total_tokens:,}")
    elif processed_files == 0 and sys.stdin.isatty():
        print("\nNo files to process. Use 'python token_counter.py --help' for usage.")

if __name__ == "__main__":
    main()
