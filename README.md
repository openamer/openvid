# OPENVID

**An independent, self-improving agent runtime. No forks, no shared code —
100% original architecture that runs entirely on your machine.**

OPENVID is not a chatbot wrapper. It is a small kernel with a durable event
bus and a growing fleet of workers — including an agent loop where the LLM
*decides itself* which tools to use, learns from its own traffic via LoRA
fine-tuning, and improves its skills from its own failures.

```
you ──> kernel (events + gate) ──> workers: shell · files · web · browser
        │                            memory · skills · cron · sys · swarm
        └── agent-loop (LLM picks tools) ──> local fine-tuned model or cloud
```

## What makes it different

| | Typical framework | OPENVID |
|---|---|---|
| Core | monolithic agent + giant tool schema | ~1800-line kernel, tools are workers |
| Tool calls | hard-coded dispatch | **the model decides**, gate enforces policy |
| Memory | bolted-on vector DB | durable SQLite event bus = audit trail = training data |
| Learning | static | **LoRA fine-tune on its own conversations**, hot-swapped live |
| Failure handling | crash | failed results become skill-improvement proposals |
| Access | one web UI | CLI · WebUI · Desktop (tray) · Telegram · Discord · Webhook |

## Features (all live-verified)

- **Autonomous agent loop** — LLM chains tools (shell → browser → memory …)
  up to 8 steps, full permission gate (`allow`/`confirm`/`deny` as data)
- **Full machine access** — files anywhere, any shell command; only destructive
  ops (`file.delete`, `shell.rm`) ask for confirmation
- **Multi-turn sessions** with history injection
- **Self-improvement** — error clustering → skill proposals; nightly LoRA
  training on own traffic; **hot-swap** of the trained adapter without restart
- **Local-first** — runs on Ollama/your GPU; cloud LLM optional fallback
- **Voice** — mic input (Whisper STT) + spoken answers (OpenAI TTS)
- **Multi-channel** — Telegram, Discord, generic webhooks
- **Desktop app** — Electron shell with tray keep-alive
- **Windows service** — autostart, crash-restart, 24/7

## Quick start

```bash
pip install -e .
export OPENVID_LLM_KEY=sk-or-...          # or run fully local via Ollama
openvid -p "Say OPENVID-OK"               # one-shot
openvid                                    # REPL

python -m openvid.server                   # WebUI + API on :8765
python scripts/install-service.ps1         # 24/7 Windows service
python -m openvid.telegram                 # Telegram frontend
```

Desktop: `cd desktop && npm install && npm start`

## Architecture

[ARCHITECTURE.md](ARCHITECTURE.md) — event bus, worker protocol, permission
gate, learning loop.

## Tests

`pytest tests/` — 32 tests: bus durability, gate semantics, dispatcher
routing, session handling, sandbox-free file access, web, agent-loop
logic (fake-LLM), server wiring, learning-loop state machine.

## Status

Alpha, single-user, Windows-first (Linux/macOS work for the core).
Roadmap: streaming responses, Discord gateway mode, multi-machine swarm
auth, docs site.

## License

MIT — do anything, keep the notice.
