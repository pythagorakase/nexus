---
status: canonical
sources:
  - nexus.toml
  - config/model_artifacts.lock.json
  - nexus/agents/lore/logon_utility.py
verified_commit: "b0e9cb77af52a22673113b4910d027cd189cf281"
---

# 0074: Pinned Tokenizer Revisions

**Kind:** decision
**Links:** #1126, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/1126#issuecomment-6423092502.

> - **1126-D1.** Does the prompt-window tokenizer join the pinned fetch workflow, or stay a free Hugging Face cache fetch? Decision: The prompt-window tokenizer joins the pinned workflow. Each registry entry with `tokenizer_repository` also declares `tokenizer_revision`, a 40-hex Hub commit that is required whenever `tokenizer_repository` is set, with no local-path exception. Runtime loads use `local_files_only=True`. `nexus models fetch` is the only code path that downloads. Basis: The #812 artifact contract and the fail-loud doctrine. Reversal cost: Remove the field and the local-only flag.
> - **1126-D2.** Where does the tokenizer pin live? Decision: `tokenizer_revision` lives beside `tokenizer_repository` in the `nexus.toml` registry entry, validated by the Pydantic models. Basis: Tunables live in `nexus.toml`. Reversal cost: Trivial.
> - **1126-D3.** Where are fetched tokenizer files stored? Decision: Fetched tokenizer files stay in the default Hugging Face cache (`HF_HOME`). Ruling 42 (820-Q10) governs model folders, and the cache is not a model folder. Basis: Least change. All five tokenizers already sit there. Reversal cost: A later #820 slice can anchor the cache under the runtime home.
> - **1126-D4.** Does gateway boot refuse to start when a tokenizer is not cached? Decision: No boot gate. `nexus models plan|verify` and the doctor check `models.artifacts` cover the tokenizers. A registry tokenizer missing at its pinned revision fails `models.artifacts` loudly. The first counted turn on a missing tokenizer fails with the pin named. Basis: Fail loudly without refusing to start for seats that never use the tokenizer. Reversal cost: Trivial.
> - **1126-D5.** What does the validate-config pre-commit tokenizer probe do once runtime loads are local-only? Decision: The probe calls the same fetch function that `nexus models fetch` uses, with network allowed at commit time and the existing `tokenizer_probe_timeout_seconds`. It then loads local-only. There is no second download path. Basis: The critique found that a separate download call in the probe would make a second download path; reusing the fetch function keeps fetch the only one. Reversal cost: Trivial.
> - **1126-D6.** Which revisions are pinned at first? Decision: The initial pins are the commits the owner's Hub cache resolves today, so counts do not change when the PR lands. Basis: The map's evidence shows the cached `refs/main` commits match for all five repositories. Reversal cost: Change a pin.
> - **1126-D7.** Does `nexus models fetch` cover every registry tokenizer or only those the seats currently resolve to? Decision: `nexus models fetch` covers every registry entry that declares `tokenizer_repository`. Basis: One workflow for all pinned artifacts. Reversal cost: Trivial.
> - **1126-D8.** Does tokenizer fetch depend on the embedder lock? Decision: Tokenizer pins do not depend on the embedder lock. `config/model_artifacts.lock.json` gains a `tokenizers` section. `plan`, `fetch` and `verify` handle the tokenizer section even when the embedder section is unchanged. `read_manifest` keeps raising on an absent lock file, because the lock exists on the owner host and in the repository. Basis: The critique found that today's `plan|fetch` is tied to the embedder lock, so a 58 MB tokenizer fetch would otherwise require or be blocked by the 9.8 GB embedder and reranker. Reversal cost: Trivial.
> - **1126-D9.** Does the per-turn token counter cache key include the tokenizer revision? Decision: The per-turn counter cache key at `nexus/agents/lore/logon_utility.py:1713` includes `tokenizer_revision`. Basis: The critique found that the key holds only the encoding and the repository, so two entries for one repository at different pins would share a counter. Reversal cost: None.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
