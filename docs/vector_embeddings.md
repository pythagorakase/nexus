---
status: historical
verified_commit: "ed9531e3418f695b9e47b5c9e7fdc897ac4ecdcd"
---

# Vector Embeddings in NEXUS

This document describes the vector embedding strategy used in the NEXUS system for semantic search and similarity matching.

## Production Embedding Artifact Contract

NEXUS runs exactly one embedding model: the single `[memnon.models]` entry
with `is_active = true` (Octen-Embedding-4B, 2560 dimensions, the issue #175
bake-off winner). Loading `nexus.toml` fails when zero or several entries are
active, and the error names them. Every other registry entry is an offline
evaluation candidate only: an `ir_eval` run may activate candidates through
validated MEMNON overrides, and the entries stay registered until the legacy
vector dimensions they wrote are inventoried.

### Local-Only Loading

`EmbeddingManager` loads the active model from its `local_path` with
`local_files_only=True`. There is no Hugging Face download and no hardcoded
default model. When the directory is missing, is not a directory, or fails to
load, construction raises a `RuntimeError` naming the model, the path, and the
corrective command, for example:

```text
Embedding model 'Octen-Embedding-4B' is not installed: local_path
/Users/pythagor/nexus/models/Octen-Embedding-4B does not exist. Restore it with
`hf download Octen/Octen-Embedding-4B --local-dir /Users/pythagor/nexus/models/Octen-Embedding-4B`,
then run `nexus models verify`.
```

The production reranker is `[memnon.retrieval.cross_encoder_reranking]
model_path`; its repository is the `remote_path` of the reranker candidate
entry with the same `local_path`. `CrossEncoderReranker` (`api_type =
"cross_encoder"`) and `Qwen3LMReranker` (`api_type = "qwen3_lm"`) both load
exactly that folder with `local_files_only=True`: nothing is downloaded and no
other folder of the same name is substituted, so the folder `nexus models
verify` checks is the folder that loads. A missing folder, a path that is not
a directory, or a failed load raises a `RuntimeError` naming the key and the
path, followed by
`hf download <repo> --local-dir <path>` (or, when no candidate names the
repository, pointing `model_path` at the downloaded folder) and then
`nexus models verify`. The reranker loads on the first reranked search, and
MEMNON search still catches that error, logs it, and returns the results
without reranking. There is no 8-bit reranker setting: the locked
sentence-transformers moves every `CrossEncoder` model with `.to(device)`, and
transformers rejects `.to` on 8-bit bitsandbytes models, so a `use_8bit` key
in `[memnon.retrieval.cross_encoder_reranking]` fails config validation.

### Locking and Verifying Artifacts

`[memnon.artifacts] lock_file` (`config/model_artifacts.lock.json`, resolved
against the repository root) pins the active embedder and, while reranking is
enabled, the production reranker. For each artifact the lock records:

- the repository (`remote_path`);
- the revision: the Hub commit, read from a Hub cache snapshot directory
  (`.../snapshots/<commit>`) or from the `.cache/huggingface/download/*.metadata`
  files that `hf download --local-dir` writes, and `null` when neither exists;
- the license from the model card front matter;
- the dimensions: the embedder's output dimension is read from its
  sentence-transformers `modules.json` (Pooling and Dense configs) and must
  equal the configured `dimensions`;
- every file's path, size, and sha256, plus the total size. `.cache/`,
  `.git/`, and `.DS_Store` are not part of an artifact.

Run both commands on the host that holds the artifacts:

```bash
nexus models lock     # hash the local artifacts and write the lock; commit it
nexus models verify   # read-only; exits 1 listing each problem and its remedy
```

`verify` fails when a locked file is missing or differs in size or sha256,
when an unlisted file appears, or when the configured embedder, reranker,
repository, or dimensions no longer match the lock. Its remediation names
`hf download <repo> --revision <commit> --local-dir <path>` for a changed
artifact and re-running `nexus models lock` after an intentional upgrade. A
lock that is absent, truncated, holds merge-conflict markers, or lacks the
expected fields fails the same way (exit 1, and valid JSON under `--json`)
with `nexus models lock` as the remedy.
Only `.DS_Store` is ignored: the `._*` AppleDouble files that copying an
artifact to an exFAT or network volume creates are unexpected files, so remove
them first (on macOS, `dot_clean -m <path>`).
Neither command downloads anything, and startup does not run `verify`.

The lock is committed: `config/model_artifacts.lock.json` records the
production embedder and reranker as they sit on the owner's host, and
`tests/test_model_artifact_lock_committed.py` fails when `nexus.toml` names a
different active embedder, reranker, repository, or embedder dimension than
the lock does. `nexus models verify` then checks, read-only, that every locked
file on this host has its locked size and sha256, that no unlisted file
appears, and that `nexus.toml` still names the locked models. Every embedder
and reranker loader passes `local_files_only=True` after checking that the
configured folder exists: the embedder loader
(`get_or_load_sentence_transformer`, shared by `EmbeddingManager`, the
embedding job, and the operator scripts `import_narratives.py`,
`query_narratives_vector.py`, and `regenerate_embeddings.py`) and both
rerankers. An artifact with missing files therefore fails to load rather than
being repaired from the Hub; a modified or extra file still loads, and only
`nexus models verify` catches it. The prompt-window tokenizer in
`nexus/telemetry/prompt_window.py` is not a retrieval artifact and is outside
this rule.

## Database Storage Strategy

To handle different vector dimensions efficiently, we use a **lazy
dimension-specific tables approach**. Tables are named
`chunk_embeddings_<dimensions>d` with four-digit padding for current model
families, such as `chunk_embeddings_1536d`.

Each table has the same logical shape:

```sql
chunk_id BIGINT NOT NULL REFERENCES narrative_chunks(id) ON DELETE CASCADE,
model TEXT NOT NULL,
embedding vector(<dimensions>) NOT NULL,
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
PRIMARY KEY (chunk_id, model)
```

This approach was chosen because pgvector requires fixed dimensions at table creation time, and mixing vectors of different dimensions in the same table would require significant padding and dimensionality management.

Fresh slots do not pre-create every possible embedding table. Write paths call
`ensure_embedding_table(...)` for the active model dimension when embeddings are
generated. Read paths inspect existing tables and never create them.

## Query Routing System

The `embedding_utils.py` utility provides functions that automatically route queries to the correct table based on the model name:

```python
from scripts.utils.embedding_utils import get_table_for_model

# Will return "chunk_embeddings_1536d"
table = get_table_for_model("inf-retriever-v1-1.5b") 

# Will return "chunk_embeddings_1024d"
table = get_table_for_model("e5-large-v2") 
table = get_table_for_model("bge-large-en")
```

## Implementation Details

### Key Functions

1. `get_model_dimensions(model_name)`: Returns the dimension (1024 or 1536) for a given model
2. `get_table_for_model(model_name)`: Returns the appropriate table name based on dimensions
3. `construct_vector_search_sql(model_name, filter_conditions, limit)`: Builds SQL with the correct table
4. `normalize_vector(vector)`: Normalizes vectors to unit length for better comparison

### Search Process

1. Generate embedding for the query using the specified model
2. Determine the appropriate table based on the model name
3. Execute a similarity search using pgvector's `<=>` operator
4. Return the most similar chunks

## Usage Example

Here's a simple example of performing a semantic search:

```python
from nexus.agents.memnon.memnon import Memnon

# Initialize Memnon (the memory utility)
memnon = Memnon()

# Search using the multi-model ensemble approach
results = memnon.hybrid_search(
    "Alex discovers the artifact",
    limit=5
)

# Or search with a specific model
inf_results = memnon.vector_search(
    "Alex discovers the artifact",
    model="inf-retriever-v1-1.5b",
    limit=5
)

e5_results = memnon.vector_search(
    "Alex discovers the artifact", 
    model="e5-large-v2",
    limit=5
)
```

## Validation Tools

Use the `validate_embeddings.py` script to verify that both tables are functioning correctly:

```bash
python scripts/validate_embeddings.py
```

This will:
1. Count embeddings in each table by model
2. Perform a simple vector similarity search with each model type
3. Validate that the appropriate table is being used for each model

## Testing

The `test_embedding_utils.py` script allows testing the table selection logic:

```bash
python scripts/test_embedding_utils.py
```

## Hybrid Search Capabilities

MEMNON implements sophisticated hybrid search combining:
- **Vector similarity**: The single production embedder (Octen-Embedding-4B)
- **PostgreSQL full-text search**: For keyword matching
- **Cross-encoder reranking**: Using Naver TREC-DL22 model for final result refinement
- **Temporal boosting**: Time-aware search for queries with temporal context
- **Query-type-specific weighting**: Different strategies for different query types

## Future Considerations

Potential enhancements include:

1. **Dynamic model weighting**: Adjusting weights based on query characteristics
2. **Additional specialized models**: Task-specific embeddings for different narrative aspects
3. **Hybrid dimensionality reduction**: Combining models at different dimensional scales

The dimension-specific tables approach provides optimal performance while maintaining flexibility for future model additions.
