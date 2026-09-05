# OPENVID — Architecture

## Core idea: Event-Kernel + Workers

OPENVID is a fully independent ASI agent runtime. No fork, no shared code with
other agent projects. The architecture is deliberately different from the
"agent-core with tool schema" pattern:

- A **Kernel** (~500 lines) knows only one thing: an event loop.
- Every capability is a **Worker**: an isolated process/thread that subscribes
  to event topics and publishes results back onto the bus.
- The **Bus** is a SQLite-backed durable queue (WAL) — events survive crashes.
- Frontends (CLI, Desktop, Telegram, ...) are just Worker-backed clients, not
  special-cased code paths.

## Topics

    user.input            -> agent.turn        (kernel routes to llm worker)
    agent.action          -> shell/browser/file (permission gate in kernel)
    worker.result         -> agent.context     (results feed the next turn)
    memory.read/write     -> memory worker
    schedule.tick         -> cron worker
    skill.invoke          -> skill worker

## Permission gate

Every `agent.action` passes through the kernel's gate before dispatch:
allowed-tools list, path sandbox, and a human-confirm rule for destructive ops.
The gate is data (a config table), not scattered if-statements.

## Learning

- Episodic memory: memory worker appends every turn to `memory/episodes.jsonl`
- Skills: markdown files in `skills/`, indexed by the skill worker, injectable
  into prompts
- Self-improvement loop: nightly worker re-reads error events, proposes skill
  patches (human-approved by default; autonomous mode behind a config flag)

## Roadmap

- [x] Phase 1: Kernel + Bus + shell/memory/llm workers + CLI REPL (this repo)
- [ ] Phase 2: browser worker, skills, cron
- [ ] Phase 3: desktop (Electron), multi-worker swarm across machines
- [ ] Phase 4: self-improvement loop, fine-tune feedback into local model
