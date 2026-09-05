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

See [ARCHITECTURE.md](ARCHITECTURE.md) for the full design and roadmap
(browser worker, skills, cron, desktop, cross-machine swarm, self-improvement).

## License

MIT — do anything, keep the notice.
