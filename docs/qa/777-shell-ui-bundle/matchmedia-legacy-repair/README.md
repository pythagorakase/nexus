# Legacy Media Listener Repair

Tested source: `772dd499ed5cd00e5ceb5c2577efa428eb8866f8`, tree
`648acf6fee3f6bbfa2dc7ade71f4fcb4de1c1ab0`. The only source delta adds
no-op `addListener()` and `removeListener()` methods to the jsdom fallback.
Its query string, `matches: false`, modern methods and conditional install
are unchanged. Framer Motion uses the legacy listener API. Normal hooks passed.

From the worktree, with a one-minute load of 7.28:

```sh
env -u NEXUS_GATEWAY_PORT -u NEXUS_API_URL -u NEXUS_SLOT \
  -u NEXUS_RUN_LIVE_LLM NEXUS_KEYRING_DISABLE=1 PYTHONPATH="$PWD" \
  NEXUS_HOME="$PWD" nice -n 15 npm --prefix ui test -- \
  InteractiveWizard.test.tsx InteractiveWizard.transition.test.tsx \
  WizardShell.test.tsx ContinuePage.resume.test.tsx
```

**Four files passed, 77 tests passed, 5.17s.** No uncaught errors. The exact
[output](focused.txt) retains existing panel/ref and browser-data warnings.
These four files failed in the preserved [V2 full run](../capture-at-b6a704ca/full-ui.log).
No full-suite or state-surface acceptance pass is claimed here.

The [fresh input closure](inputs.json), computed with `nice -n 15 node
ui/scripts/state-surfaces/inputs.mjs "$PWD/ui"`, is
`60690c147ac027eaca62ca3f2e93a49678e7c3a576aaf3e9b09409cb6848abfb`.
Comparing its per-file hashes with V2 identifies exactly
`client/src/tests/setup.ts`; all other input hashes are unchanged. The V2
receipt must not be relabeled or reused for this input. Fresh complete capture
and full UI acceptance remain required after the pending palette disposition.
No product palette, evaluator, threshold, owner service or database changed.

Codex — GPT-6
