"""Tests verifying OpenAI prompt cache key plumbing."""

import json
import subprocess
import sys
from pathlib import Path


def _run_python(script: str) -> subprocess.CompletedProcess[str]:
    """Execute helper script with repository context."""
    return subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
    )


def test_openai_provider_sets_extra_body_prompt_cache_key():
    script = r"""
import json
import sys
import types

if "sqlalchemy" not in sys.modules:
    sqlalchemy_stub = types.ModuleType("sqlalchemy")
    sqlalchemy_stub.create_engine = lambda *args, **kwargs: None
    sys.modules["sqlalchemy"] = sqlalchemy_stub

from scripts.api_openai import OpenAIProvider

OpenAIProvider.initialize = lambda self: None


class FakeResponses:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        usage = types.SimpleNamespace(input_tokens=1, output_tokens=1)
        return types.SimpleNamespace(output_text="ok", usage=usage)


def make_provider():
    provider = OpenAIProvider(
        api_key="test",
        model="gpt-4o",
        temperature=0.3,
        max_tokens=6000,
        max_output_tokens=6000,
        system_prompt="system",
    )
    provider.client = types.SimpleNamespace(responses=FakeResponses())
    provider.supports_temperature = True
    provider.temperature = 0.3
    provider.reasoning_effort = None
    return provider


with_provider = make_provider()
with_provider._get_completion_unified("hello", cache_key="story-3")
with_kwargs = with_provider.client.responses.kwargs

without_provider = make_provider()
without_provider._get_completion_unified("hello")
without_kwargs = without_provider.client.responses.kwargs

print(json.dumps({"with": with_kwargs, "without": without_kwargs}))
"""

    result = _run_python(script)
    payload = json.loads(result.stdout.strip())
    assert payload["with"]["extra_body"] == {"prompt_cache_key": "story-3"}
    assert "extra_body" not in payload["without"]


def test_openai_batch_serializes_prompt_cache_key(tmp_path_factory):
    output_dir = tmp_path_factory.mktemp("batch_outputs", numbered=False)

    batch_module_path = (Path(__file__).resolve().parents[2] / "nexus" / "audition" / "batch_clients.py")
    output_dir_str = json.dumps(str(output_dir))
    module_path_str = json.dumps(str(batch_module_path))

    script_template = """
import json
import sys
import types
from pathlib import Path

if "sqlalchemy" not in sys.modules:
    sqlalchemy_stub = types.ModuleType("sqlalchemy")
    sqlalchemy_stub.create_engine = lambda *args, **kwargs: None
    sys.modules["sqlalchemy"] = sqlalchemy_stub

import importlib.machinery

module_path = Path({module_path})
module = importlib.machinery.SourceFileLoader('_test_batch_clients', str(module_path)).load_module()

BatchRequest = module.BatchRequest
OpenAIBatchClient = module.OpenAIBatchClient


class StubFiles:
    def __init__(self):
        self.uploaded = None

    def create(self, *, file, purpose):
        self.uploaded = file.read()
        file.seek(0)
        return types.SimpleNamespace(id='file-123')


class StubBatches:
    def create(self, *, input_file_id, endpoint, completion_window):
        return types.SimpleNamespace(id='batch-xyz', status='validating')


client = OpenAIBatchClient.__new__(OpenAIBatchClient)
client.client = types.SimpleNamespace(files=StubFiles(), batches=StubBatches())
client.api_key = 'test'

req_with = BatchRequest(
    custom_id='req-1',
    prompt_id=3,
    replicate_index=0,
    prompt_text='hello',
    model='gpt-4o',
    temperature=0.4,
    max_tokens=2000,
    system_prompt='system',
    cache_key='story-3',
    reasoning_effort=None,
    max_output_tokens=None,
)

req_without = BatchRequest(
    custom_id='req-2',
    prompt_id=4,
    replicate_index=1,
    prompt_text='goodbye',
    model='gpt-4o',
    temperature=0.2,
    max_tokens=1500,
    system_prompt=None,
    cache_key=None,
    reasoning_effort=None,
    max_output_tokens=None,
)

output_dir = Path({output_dir})
batch_id = client.create_batch([req_with, req_without], output_dir)

files = list(output_dir.glob('batch_input_*.jsonl'))
with files[0].open() as handle:
    lines = handle.read().splitlines()

print(json.dumps({{
    'batch_id': batch_id,
    'with_body': json.loads(lines[0])['body'],
    'without_body': json.loads(lines[1])['body'],
}}))
"""

    script = script_template.format(module_path=module_path_str, output_dir=output_dir_str)

    result = _run_python(script)
    payload = json.loads(result.stdout.strip())
    assert payload["batch_id"] == "batch-xyz"
    assert payload["with_body"]["prompt_cache_key"] == "story-3"
    assert "prompt_cache_key" not in payload["without_body"]
