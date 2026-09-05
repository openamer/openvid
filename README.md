# OPENVID

**An independent event-kernel ASI runtime.** No forks, no shared code with any
other agent project — 100% original architecture built from scratch.

## Why OPENVID is different

Every mainstream agent framework follows the same pattern: a monolithic
agent-core that carries a giant tool schema on every model call. OPENVID
inverts this:

- **A tiny kernel that knows only events.** ~100 lines. It routes, gates,
  and does nothing else.
- **Everything is a Worker.** Shell, memory, LLM, browser, cron — isolated
  handlers that subscribe to topics on a durable SQLite event bus. Crash-safe:
  a failing worker never takes the runtime down.
- **The bus is the memory.** Every event is persisted (WAL mode). Full audit
  trail by default. Recover from any crash by replaying.
- **Frontends are peers, not privileged.** CLI, desktop, and messengers all
  publish/subscribe on the same bus.

## Status

Phase 1 — core runtime, verified end-to-end:

- [x] Durable event bus (SQLite WAL, claim/complete, crash-safe)
- [x] Kernel event loop with permission gate (allow/confirm/deny as data)
- [x] Shell worker (gated execution)
- [x] Memory worker (episodic write/search)
- [x] LLM worker (any OpenAI-compatible endpoint: OpenRouter, local, GPU)
- [x] CLI REPL + one-shot mode (`openvid -p "..."`)
- [x] Live-verified: bus roundtrip, gate denial, memory, real LLM answer

## Quick start

```bash
pip install -e .
export OPENVID_LLM_KEY=sk-or-...        # OpenRouter key
export OPENVID_LLM_MODEL=z-ai/glm-5.3-flash
openvid -p "Say OPENVID-OK"             # one-shot
openvid                                  # REPL (/run <cmd>, /remember <note>, /quit)
```

## Architecture

## Status: Phases 1–10 complete

| Phase | Feature | Verified |
|---|---|---|
| 1 | Kernel + durable bus + shell/memory/llm workers + CLI | ✓ 7/7 checks |
| 2 | Browser worker (Chrome via CDP :9222) | ✓ eval "Example Domain" |
| 3 | Skills (markdown, path-traversal guarded) | ✓ write/list/get |
| 4 | Cron (durable, daily@HH:MM + intervals, fires via bus) | ✓ job fired |
| 5 | HTTP API (/health /ask /action /result) | ✓ /ask → real answer |
| 6 | Self-improvement (error clustering → skill proposals) | ✓ proposal written |
| 7 | Telegram frontend (long-polling bus client) | ✓ code + API format |
| 8 | WebUI (zero-build chat, served at /) | ✓ HTML + /ask OK |
| 9 | Swarm mesh (health-probed peers, no coordinator) | ✓ live cross-node ask |
| 10 | Fine-tune export (bus → SFT JSONL) | ✓ correct format |
| + | Local model worker (Ollama native API, offline ASI) | ✓ "KERNEL-LOCAL-OK" |

Run everything locally, offline, on your own hardware:

```bash
python -m openvid.server        # API + WebUI on :8765
python -m openvid.telegram      # Telegram frontend
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for the design.

## License

MIT — do anything, keep the notice.
