---
status: canonical
sources:
  - nexus.toml
  - nexus/config/settings_models.py
  - docs/runtime.md
verified_commit: "c7ae2988d07b443f627a04d3a4eed1816b1cd438"
---

# 0079: Listener Ports, Lanes and Origins

**Kind:** decision
**Links:** #824, coordinator review 2026-10-26

## Ruling

Source: https://github.com/pythagorakase/nexus/issues/824#issuecomment-6423109883.

> - **D-824-PORT.** Which loopback port does the operator projection take, and where is it configured? Decision: The operator projection listens on 127.0.0.1:8003, configured as [runtime.gateway].operator_port in nexus.toml and validated in settings_models.py; the player projection keeps the service port (8002) and the Cloudflare ingress does not change. Basis: Ruling 43 824-Q1; 8003 is unused in the repository and on the host. Reversal cost: Edit the tunable.
> - **D-824-LANE.** Since ruling 43 inverts the lane contract of Decision 824-Q9, which environment variable names which listener in agent and test lanes? Decision: NEXUS_GATEWAY_PORT overrides the operator listener (the port NEXUS_API_URL names in lanes); a new NEXUS_PLAYER_PORT override names the player listener; dual-plane QA lanes allocate both; the existing single-listener lane contract stays for tests that run one listener. Basis: Decision 824-Q9 inverted by ruling 43. Reversal cost: Trivial.
> - **D-824-CLI-CLASS.** What transport class do clear, lock, unlock and model --set/--clear get? Decision: clear, lock, unlock and model --set/--clear move to the operator_api transport; locally they call the operator listener; remotely they call [runtime.remote].operator_base_url when set and are refused otherwise. Basis: Decision 815-Q3 handed this to #824. Reversal cost: Trivial.
> - **D-824-CLI-DEFAULT.** Where does the local CLI send its HTTP commands once 8002 is the player plane? Decision: The CLI's local default base URL becomes the configured operator URL for every HTTP command; the hardcoded localhost:8002 goes. Basis: The operator plane is the full runtime. Reversal cost: Trivial.
> - **D-824-ADMIN-HOST.** What is the admin hostname, and what does its Access policy admit? Decision: The admin hostname is nexus-admin.pythagora.net (single-level, Universal SSL), behind its own Access policy; documented with the tunnel ingress and the Access application in docs/runtime.md 'Remote Administration' (824-S3, a later order). Basis: Ruling 43 824-Q2. Reversal cost: DNS and Access edits.
> - **D-824-CORS.** How is CORS scoped per plane? Decision: Two origin lists in [runtime.gateway]: player (http://localhost:8002, http://127.0.0.1:8002, https://nexus.pythagora.net) and operator (http://localhost:8003, http://127.0.0.1:8003, the Tauri origin, https://nexus-admin.pythagora.net). Basis: Per-plane scoping. Reversal cost: Edit the lists.
> - **D-824-DEV-PROXY.** Which listener do the Vite dev proxy and the direct `python -m nexus.api.narrative` launch target? Decision: The Vite dev proxy and the direct `python -m nexus.api.narrative` launch target the operator listener; the direct launch never defaults to 8002. Basis: Map default. Reversal cost: Trivial.
> - **D-824-REMOTE-STATUS.** Under the remote profile, what do up and status probe once the player hostname answers 404 for /runtime/status? Decision: Under the remote profile, up and status probe GET /health (815-S4 lands it in parallel; whichever lands second merges). Basis: Decision 815-Q5. Reversal cost: None.
> - **D-824-TRANSITION.** Does the 824-Q4 player-plane guard also cover POST /api/story/new/transition, and what counts as occupied? Decision: On the player plane, setup/start refuses an occupied slot (409) and transition refuses to wipe a slot that holds narrative data, without any persisted record of which route started the wizard; overwrite and repin exist only on the operator plane (the desktop shell runs on the operator plane, so the owner's local overwrite flow is unchanged). Basis: Decision 824-Q4; the critique's objection to a route record. Reversal cost: Trivial.
> - **D-824-STATUS-SHAPE.** Does /runtime/status or nexus status report the operator port? Decision: /runtime/status keeps services.gateway.port as the configured service (player) port and gains an additive operator_port field; nothing is removed; the Tauri summary is unchanged. Basis: Decision 824-Q6 with the critique's correction. Reversal cost: Trivial.
> - **D-824-LOCAL-BROWSER.** Is it acceptable that the owner's local browser on 127.0.0.1:8002 shows the player plane, with no settings, keys or models? Decision: Accepted: the local browser on 127.0.0.1:8002 shows the player plane; local administration uses the desktop shell or http://127.0.0.1:8003, documented in docs/runtime.md. Basis: Consequence of ruling 43. Reversal cost: None.

## Rejected Alternatives

- None recorded in the public relay.

## Reopening Criteria

- A later owner ruling on the linked issue.
