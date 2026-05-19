# JARVIS 2026 Roadmap — Local-Native on Personal Hardware

**Date:** 2026-05-19
**Branch:** `feat/integration-revival` (pre-merge) or `main` (post-W5.1)
**Status:** Planning doc. No code changes yet. Captures three converging tracks so they survive session resets.

---

## Why this doc exists

Three forces are landing on Jarvis at once and they share dependencies. Capturing them in one place so the sequence is clear:

1. **Claude Agent SDK policy change on 2026-06-15.** SDK + `claude -p` usage stops counting toward Pro/Max chat limits. Eligible plans get a separate monthly Agent SDK credit (Pro $20, Max 5x $100, Max 20x $200). Credit drains first, then falls through to extra-usage at API rates if explicitly enabled, otherwise hard-stops. No rollover. See https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan.
2. **Operator is getting a personal PC** — confirmed build is **dual RTX 3090** (48 GB pooled VRAM, NVLink optional). Target OS: **Ubuntu 24.04 LTS**.
3. **Goal: Jarvis runs fully local on that PC** — no Claude API dependency in steady state, with optional Claude fallback per-agent during migration.

The runtime system (orchestrator, five locked agents, sentinel daemon, persona, routing, confirmation gates, state JSONL) does not change. Only the LLM substrate and a few peripheral subsystems (TTS/STT/vision) swap out.

---

## Track 1 — SDK policy response (now → 2026-06-15)

### What's changing

Today, Agent SDK calls Jarvis makes against Claude count against subscription usage. On 2026-06-15 they stop counting against the subscription and start drawing from a dedicated Agent SDK monthly credit. The credit is **per-user, not pooled, no rollover, refreshes monthly, one-time opt-in to claim**. Once the credit is exhausted, additional SDK requests either hard-stop or fall through to extra-usage at standard API rates if extra-usage is enabled.

### Impact estimate

Jarvis is a heavy SDK consumer: three Opus 4.7 agents (jarvis, atlas, forge), three Sonnet 4.6 agents (tempo, scholar, lens), a Haiku 4.5 sentinel firing scanners constantly, the J8 daily Sonnet proactive pass, draft_replies cron at 06:00, morning + evening digests, plus voice tiers. Back-of-envelope at API rates:

| Cost source | Per call | Frequency | Daily |
|---|---|---|---|
| Opus chat turn (5K in / 1K out) | ~$0.15 | interactive | $0.50–$3.00 |
| Atlas pipeline run (multi-stage Opus) | ~$0.50 | a few/day | $1.00–$2.00 |
| Sentinel scanner (Haiku) | ~$0.001 | every few minutes | $0.20–$0.50 |
| J8 proactive_intelligence (Sonnet) | ~$0.15 | 1×/day at 07:30 | $0.15 |
| Morning + evening digests | ~$0.10 | 2×/day | $0.20 |
| draft_replies (Sonnet, multiple drafts) | ~$0.20 | 1×/day at 06:00 | $0.20 |

Ambient daemon cost alone: **~$30–60/month**. With interactive Opus chat and Atlas work: **$100–200/month** easily. Pro ($20) is not viable. Max 5x ($100) is tight. Max 20x ($200) is comfortable until local migration completes.

### Actions before 2026-06-15

**Add usage telemetry.** New module `jarvis/llm/cost_tracker.py`. Wraps every call from `llm/client.py` to log `{timestamp, agent, model, input_tokens, output_tokens, est_cost_usd}` to `state/api_usage.jsonl`. Daily rollup written to `state/api_usage_daily.json`. Half-day of work.

**Run for one week.** Get real spend data per agent. This is the input to the tier decision.

**Pick the tier.** Default recommendation: **Max 20x** until local migration completes, then drop to Max 5x or Pro once Jarvis runs fully local and SDK use is only for forge code work or one-off heavy chat.

**Opt into extra-usage as a safety.** So daemon doesn't hard-stop mid-task on 2026-06-16 if the credit drains unexpectedly. Set a low cap initially.

**Claim the credit on 2026-06-15.** One-time opt-in per the policy doc.

---

## Track 2 — LLM backend abstraction layer (now → PC arrives)

### Why

Jarvis assumes Claude today. Migrating to local is impossible without a clean abstraction. Adding it now also unlocks per-agent backend routing — flip sentinel to a local 7B for cost savings before the PC arrives, on whatever hardware is available.

### Target structure

```
jarvis/llm/
  backend.py          NEW  - Backend protocol (stream, complete, count_tokens)
  claude_backend.py   NEW  - wraps current Anthropic SDK code
  vllm_backend.py     NEW  - OpenAI-compatible client to vLLM
  ollama_backend.py   NEW  - OpenAI-compatible client to Ollama
  router.py           NEW  - picks backend per agent from config
  cost_tracker.py     NEW  - usage telemetry (Track 1)
  client.py           REFACTOR - thin facade over router
```

### Backend protocol sketch

```python
from typing import Protocol, AsyncIterator

class Backend(Protocol):
    name: str
    model: str

    async def stream(self, messages: list[dict], **opts) -> AsyncIterator[str]: ...
    async def complete(self, messages: list[dict], **opts) -> str: ...
    def count_tokens(self, text: str) -> int: ...
```

### Per-agent backend config

Move backend selection out of code and into config. Proposed `~/.config/jarvis/config.toml` (or `state/config.toml` during transition):

```toml
[llm]
default_backend = "claude_opus"

[llm.agents]
jarvis    = "claude_opus"     # orchestrator
atlas     = "claude_opus"
forge     = "claude_opus"
tempo     = "claude_sonnet"
scholar   = "claude_sonnet"
lens      = "claude_sonnet"
sentinel  = "claude_haiku"

[llm.backends.claude_opus]
type = "claude"
model = "claude-opus-4-6"

[llm.backends.claude_sonnet]
type = "claude"
model = "claude-sonnet-4-6"

[llm.backends.claude_haiku]
type = "claude"
model = "claude-haiku-4-5-20251001"

# Filled in once vLLM/Ollama are running:
[llm.backends.vllm_primary]
type = "vllm"
url = "http://localhost:8000/v1"
model = "Qwen/Qwen2.5-72B-Instruct-AWQ"

[llm.backends.ollama_haiku]
type = "ollama"
url = "http://localhost:11434/v1"
model = "qwen2.5:7b"
```

Env var override per agent: `JARVIS_LLM_BACKEND_sentinel=ollama_haiku` flips just sentinel to local without touching the config file. Useful for gradual cutover.

### Sequencing

This work runs in parallel with Track 1. Telemetry and abstraction share `llm/` directory but touch different files; can be one commit or two. Target: both landed before 2026-06-15.

---

## Track 3 — Local PC target spec

### Hardware

| Component | Spec | Notes |
|---|---|---|
| GPU | 2× RTX 3090 (24 GB each, 48 GB pooled) | NVLink optional but recommended |
| OS | Ubuntu 24.04 LTS | Linux is non-negotiable for local AI training |
| CPU | Modern x86_64 (Ryzen 9 or i9 class) | Inference is GPU-bound; CPU for data loading |
| RAM | 64 GB+ DDR4/DDR5 | Headroom for batched data loading during fine-tuning |
| Storage | 2 TB NVMe primary + 4 TB+ secondary | Model weights are large; 70B-class is 35–80 GB each |
| Network | Wired Ethernet preferred | For Tailscale + LAN bandwidth on remote access |

### Why Ubuntu 24.04 LTS over Windows

CUDA + NVIDIA drivers install with three apt commands and rarely break. Windows requires fighting driver/CUDA toolkit/cuDNN mismatches. vLLM (the inference server with best multi-GPU support) is Linux-first; Windows path is WSL2 with 5–10% perf cost and friction. Training frameworks — PyTorch, Axolotl, Unsloth, DeepSpeed, bitsandbytes — all publish Linux recipes; Windows recipes are afterthoughts and bitsandbytes specifically is painful. NVLink and tensor parallelism across two cards have first-class Linux support. systemd is the right service manager for Ollama, vLLM, Jarvis sentinel, Jarvis API — far cleaner than Task Scheduler or nssm. If the PC ever becomes a closet server (central-brain mode), Linux + SSH is trivial.

If gaming on this PC matters, dual-boot Windows on a separate NVMe drive. If not, Linux-only.

### Inference stack

**Primary:** vLLM serving one 70B-class model across both cards with tensor parallelism. Single always-resident "brain" for jarvis/atlas/forge/tempo/scholar/lens — different system prompts, same model.

**Sidecar:** Ollama for the small models (sentinel 7B, vision 7B, embeddings). Swap-in latency is acceptable for these.

**Voice:** Piper for TTS (CPU-bound, sub-second latency, neural quality). faster-whisper large-v3 for STT (GPU-bound when active).

### Model loadout

| Slot | Model candidate | Quant | VRAM | Where it lives |
|---|---|---|---|---|
| Primary brain (Opus + Sonnet tier) | Qwen 2.5 72B Instruct AWQ **or** Llama 3.3 70B | AWQ / Q4 | ~35–40 GB across 2 cards | vLLM, `--tensor-parallel-size 2` |
| Coder specialist (forge) | Qwen 2.5 Coder 32B | Q5 | ~22 GB | vLLM second instance OR swap into primary |
| Sentinel + voice tier 1 (Haiku) | Qwen 2.5 7B Instruct | Q5 | ~5 GB | Ollama, always resident |
| Vision | Qwen 2.5-VL 7B | Q5 | ~6 GB | Ollama, swap-in |
| STT | faster-whisper large-v3 | fp16 | ~3 GB | GPU when active |
| TTS | Piper neural (en-US Andrew-equivalent voice) | — | <1 GB | CPU |
| Embeddings (RAG/memory) | nomic-embed-text v1.5 | — | <1 GB | Ollama, always resident |

Throughput target on 72B AWQ tensor-parallel: ~25–35 tok/s single-stream, higher on batched scanner traffic. Comfortable for interactive chat (faster than reading speed).

After primary brain is loaded, ~8 GB of VRAM is free across the two cards for KV cache (~32K context) plus the 7B sentinel + 7B vision both resident. Effectively zero model-swap latency in steady state.

### Sample vLLM launch

```bash
vllm serve Qwen/Qwen2.5-72B-Instruct-AWQ \
  --tensor-parallel-size 2 \
  --max-model-len 32768 \
  --gpu-memory-utilization 0.85 \
  --host 127.0.0.1 \
  --port 8000
```

### systemd service layout

```
~/.config/systemd/user/
├── jarvis-vllm.service        # primary 70B/72B on tp=2
├── jarvis-ollama.service      # sentinel 7B + vision + embeddings
├── jarvis-api.service          # jarvis.apps.api
├── jarvis-sentinel.service     # daemon + scanners + crons
└── jarvis-voice.service        # hot-mic loop (optional)
```

Each is a user-level systemd unit so they survive logout and restart with the machine. `Restart=on-failure`, `After=network-online.target`, `WantedBy=default.target`.

### Filesystem layout

```
/opt/jarvis/                       # code (pipx-installed or symlinked clone)
~/.config/jarvis/config.toml       # backend selection, per-agent overrides
~/.local/share/jarvis/
  ├── state/                       # chat_turns, tasks, projects, facts, etc.
  ├── models/                      # downloaded weights (or symlink to NVMe)
  └── logs/
~/.cache/jarvis/                   # transient
```

Paths in `jarvis/config/paths.py` resolve these via `platformdirs`. Already on the W5+ path-abstraction shortlist.

---

## Track 4 — Migration sequence (PC arrival → fully local)

Sequenced to ship value incrementally. Sentinel migrates first because it's highest call-volume and lowest stakes — proves the local path and saves the most money. Orchestrator migrates last because it's the most capability-sensitive.

### Week 0 — pre-arrival prep on Windows (now → PC arrives)

Add backend abstraction (Track 2). Add usage telemetry (Track 1). Start local-stack proof-of-concept on current Windows machine: install Ollama, pull Qwen 2.5 7B, route sentinel to it via `JARVIS_LLM_BACKEND_sentinel=ollama_haiku`. Watch for a day. This validates the abstraction end-to-end before the new hardware arrives.

Begin dataset collection for fine-tuning (Track 5).

### Week 1 — install and validate

Day 1–2: Install Ubuntu 24.04. NVIDIA drivers (550+), CUDA 12.x, Docker, Tailscale, pyenv, uv (or pipx). Verify both 3090s with `nvidia-smi`. Confirm NVLink with `nvidia-smi nvlink -s` if bridge is installed.

Day 3: Install vLLM in a venv. Download Qwen 2.5 72B AWQ (~35 GB). Launch with the sample command above. Verify tensor parallelism (`nvidia-smi` shows both cards active during a prompt). Smoke-test throughput.

Day 4: Install Ollama. Pull `qwen2.5:7b`, `qwen2.5-vl:7b`, `nomic-embed-text`. Smoke-test each.

Day 5: Install Piper, faster-whisper. Verify TTS latency and STT accuracy. Pick a Piper voice that approximates EdgeTTS Andrew Multilingual (closest English options: `en_US-lessac-high` or `en_US-ryan-high`).

Day 6–7: Clone Jarvis. Install via pipx (or editable install from clone). Run smoke test with `JARVIS_NODE_ROLE=server` and all `JARVIS_LLM_BACKEND_*` still pointing at Claude. Validates the install layout before flipping backends.

### Week 2 — flip backends one tier at a time

Day 8: Flip sentinel to `ollama_haiku`. Watch logs, scanner output, J8 proactive pass. Confirm overnight digests still run. If quality holds for 24h, proceed.

Day 9–10: Flip tempo, scholar, lens to `vllm_primary` (the 72B). These are Sonnet-tier; the 72B should match or exceed Sonnet 4.6 on most tasks. Watch tempo email drafts most carefully — voice/tone matters.

Day 11–12: Flip atlas to `vllm_primary`. This is the highest-stakes flip because atlas drives trading decisions. Keep Claude as fallback for the pipeline (one specific env var) until confidence builds.

Day 13–14: Flip jarvis orchestrator and forge to `vllm_primary`. For forge specifically, consider running Qwen 2.5 Coder 32B as a second vLLM instance and routing only forge to it.

### Week 3+ — peripheral migration

Replace EdgeTTS with Piper in `apps/voice/`. Add `PiperTTSProvider` implementing the same TTS Protocol; flip via env var. Replace cloud STT (if any) with faster-whisper. Replace vision via Qwen 2.5-VL. Each is an isolated swap behind an existing Protocol.

### Week 4+ — fine-tuning (Track 5)

Once steady-state local Jarvis is running, start personalization.

### Rollback story

Per-agent backend config means any failed migration is reverted by one env var change. Keep Claude API key and SDK credit available throughout migration as the always-available fallback. Drop the API dependency only after 30 consecutive days of stable local operation.

---

## Track 5 — Personalization via fine-tuning

### Why this is worth doing

Local 72B is competitive with Sonnet 4.6 out of the box and close to Opus on most non-frontier tasks. Where it falls short is the *Jarvis-specific* shape: chief-of-staff persona, your speech patterns, your code style, your trading commentary register. Fine-tuning on your own data closes that gap and makes the local stack feel like your stack, not a generic open-weight model.

### Datasets to collect (start now, before PC arrives)

| Dataset | Source | Use case |
|---|---|---|
| Chat persona | `state/chat_turns.jsonl` | Orchestrator + voice — match your conversational shape |
| Email voice | `state/drafted_replies.jsonl` + sent mail | Tempo — match your professional reply tone |
| Code style | Git history of `jarvis/`, `atlas/` repos | Forge — match how you actually write Python and TS |
| Trading commentary | Atlas pipeline outputs + your annotations | Atlas — internalize your trading philosophy |
| Skill execution patterns | `state/agent_log.jsonl` filtered to skill invocations | Skill library — improve auto-chaining |

Write a daily extractor: `jarvis/training/extract.py` runs nightly via sentinel, formats each source into Unsloth/Axolotl-compatible JSONL with proper system prompts. By the time the PC arrives, months of data are ready.

### Tooling

**Unsloth** for the fastest single-GPU LoRA path. Handles QLoRA, flash attention, fused operators automatically. Single command per fine-tune. Best fit for 32B LoRAs on dual 3090.

**Axolotl** for more flexible recipes (continued pretraining, multi-stage tuning, custom data formats). Slightly more setup, more control.

**Hugging Face TRL** for custom RL loops if you ever want DPO/ORPO on preference data harvested from chat thumbs-up/down.

### Fine-tune targets

| Target | Base model | Method | Dataset | Expected size |
|---|---|---|---|---|
| Jarvis persona | Qwen 2.5 32B (start) → 72B | QLoRA, r=16 | chat_turns | ~200 MB LoRA |
| Tempo email voice | Qwen 2.5 32B | QLoRA, r=8 | drafted_replies + sent mail | ~100 MB LoRA |
| Forge code style | Qwen 2.5 Coder 32B | QLoRA, r=16 | git history | ~200 MB LoRA |
| Atlas commentary | Qwen 2.5 32B | QLoRA, r=8 | atlas pipeline + annotations | ~100 MB LoRA |

LoRAs stack on the base model at runtime — vLLM supports LoRA adapters, so you serve the 72B base and swap the persona LoRA in/out per-agent. No retraining the base model required.

Full fine-tuning (not LoRA) of 13B-class models is also possible on 48 GB but typically not necessary; LoRA on a strong base is the right cost/quality ratio.

### When to start

Dataset collection: now (write the extractor as part of Track 2 work).

First fine-tune: ~Week 4 after PC arrival, once local stack is stable.

### Training as a research project

Operator also wants to research training own models (per chat). Realistic ladder:

1. **LoRA fine-tunes on existing open-weight bases** (Unsloth/Axolotl) — practical, works on this hardware, ships value into Jarvis.
2. **Continued pretraining** on personal corpora (continued training on a 7B base with your code+writing) — also viable on dual 3090, ~days of compute per run.
3. **Custom small-model training from scratch** (a 100M–1B param model on a curated dataset) — viable as a research project; will not match open-weight quality at the same size.
4. **Frontier-scale training** — not viable. Requires $millions of compute.

For Jarvis the realistic targets are (1) and (2). The PC is sized correctly for that ladder.

---

## Track dependencies

```
Track 1 (telemetry) ─────────────────┐
                                     │
Track 2 (backend abstraction) ───────┼──> 2026-06-15 deadline (SDK policy)
                                     │
Track 5 (dataset extractor) ─────────┘
                                     │
                                     v
                              PC arrives
                                     │
Track 3 (PC setup) ──────────────────┤
                                     │
Track 4 (cutover) ───────────────────┤
                                     │
                                     v
Track 5 (fine-tunes) ────────> steady-state local Jarvis
```

Tracks 1, 2, 5-prep run in parallel before the policy date. Tracks 3, 4 are sequential post-arrival. Track 5 fine-tunes start after Track 4 stabilizes.

---

## Operator action items

In order:

1. Finish W3-W5 commit per `docs/WEEK_IN_ONE_DAY_2026-05-18.md`. Don't merge to main yet.
2. Add Track 1 telemetry — half day of work. Commit on `feat/integration-revival` or a new branch.
3. Add Track 2 backend abstraction — 1–2 days of work. Same branch.
4. Run telemetry for 7 days. Decide subscription tier based on observed cost.
5. Add Track 5 dataset extractor — half day. Daily sentinel cron starting writing training data.
6. 2026-06-15: claim Agent SDK credit, opt into extra-usage as safety.
7. PC arrives: Track 3 setup (Week 1), Track 4 cutover (Week 2–3).
8. Local stack stable for 30 consecutive days: drop Claude API as primary backend. Keep credit for fallback / heavy chat.
9. Begin Track 5 fine-tunes.

---

## Open decisions

**Subscription tier between 2026-06-15 and PC arrival.** Default recommendation Max 20x. Revisit after telemetry data lands.

**vLLM vs TabbyAPI vs Aphrodite.** Default vLLM (most mature, best multi-GPU). TabbyAPI is lighter for single-GPU exl2 workflows but not the right fit here.

**Primary 70B model: Qwen 2.5 72B Instruct AWQ vs Llama 3.3 70B Q4.** Qwen 2.5 72B is currently the strongest open-weight Instruct model and AWQ has cleaner vLLM support. Llama 3.3 70B is close and has broader ecosystem. Recommend Qwen 2.5 72B as primary, Llama 3.3 70B as comparison/fallback. Benchmark both on your eval set before committing.

**Dual-boot Windows on the new PC.** Yes if you game on this hardware; no otherwise.

**Where state lives during transition.** Recommend keeping `state/` on the Linux box once it arrives, copying chat_turns.jsonl + facts + projects from Windows on first boot. Single source of truth from day one.

---

## What stays unchanged

Every architectural decision in CLAUDE.md remains. Locked five agents. Sentinel as infrastructure not an agent. Confirmation matrix. State conventions. Code style. Reuse-over-rebuild table. ATLAS boundary. Persona shape. None of that changes. This roadmap is exclusively about substrate — what generates the tokens and where the daemon runs.

---

## Reference

- SDK policy: https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan
- Companion docs: `docs/WEEK_IN_ONE_DAY_2026-05-18.md`, `docs/J7-J11_LANDED_2026-05-14.md`, `docs/JARVIS_PERFECTION_AUDIT_2026-05-13.md`, `docs/OPERATOR_ACTIONS.md`
- Project rules: `.claude/CLAUDE.md`
