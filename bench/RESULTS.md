# Local replication — results

**Model:** `LFM-3-Coder-Claude-Distill.Q5_K_M.gguf` (community distill of LiquidAI LFM3-1.7B, 1.73B, 1.16 GiB)
**Runtime:** llama.cpp b12242 (`0.9.0-dev`), Vulkan
**Hardware:** Intel Core Ultra 5 235U, Intel Arc iGPU (18 GB shared), 31.5 GB RAM
**Date:** 2026-11-10

## Setup

| Setting | Value |
|---|---|
| Context | `-c 16384`, `-np 1` (one slot) |
| KV cache | `-ctk q8_0 -ctv q8_0`, Flash Attention on |
| Reasoning | `--reasoning-budget 0` for main sweep, `512` for the thinking subset |
| Sampling | temperature 0, top_p 0.95, `max_tokens` 384 (1024 with thinking) |
| Reps | 2 per (task, arm); 1 for the thinking subset |
| Throughput | `pp512` = **276.6 tok/s**, `tg128` = **20.8 tok/s** |

30 tasks, 6 tiers × 5: A0 (no tools) → A (1 tool) → B (2-tool chain) → C (branch) → D (multi-source conflict) → E (long horizon, 8–12 calls).

## Headline table

| arm | A0 | A | B | C | D | E | **all** | $/pass* | tok/s |
|---|---|---|---|---|---|---|---|---|---|
| `json` (tools as text) | 60% | 100% | 100% | 0% | 20% | 0% | **47%** | $0.00420 | 7.5 |
| `native` (OpenAI tools) | 60% | 100% | 100% | 80% | 60% | 40% | **73%** | $0.00271 | 10.1 |
| `verifier` (native + retries) | 60% | 100% | 100% | 80% | 40% | 60% | **73%** | $0.00269 | 10.2 |
| `nudged` (explicit "must submit"), C/D/E only | — | — | — | 60% | 60% | 60% | **60%** | — | — |
| `native` + thinking, 6-task subset | — | — | — | — | — | — | **6/6** | — | — |

\* amortised at $0.50/h local compute, per passed task. `pass@1` equals `pass^2` because temperature 0 is deterministic.

## Finding 1 — the harness interface is the biggest lever (+26 pp)

Same weights, same tasks, same server. Only the *way* tools are exposed changed:

- native `tools` schema: **73%**
- tools described in the system prompt + JSON-in-text: **47%**

`json` produced 28 `no_submission` failures vs 10 for native, and 7.5 tok/s vs 10.1 tok/s. The model has the capability; the transport removes it. This is Karpathy's thesis #4 ("intelligence lives in the system") in its most literal form.

Caveat: this is a *capability* difference on this model, not proof that JSON emulation always loses. Sub-2B models are known to be format-fragile (see `research/SOURCES.md`), which is exactly why the interface matters.

## Finding 2 — the tier curve is the real verdict

Both native arms are perfect on A and B (single tool, 2-tool chain) and degrade exactly where AgentFloor says they should:

```
A0 60%  →  A 100%  →  B 100%  →  C 80%  →  D 60%  →  E 40-60%
```

Failure mass:
- `no_submission` (model stops calling tools before submitting): 10/60 native runs
- `payload_mismatch` (submits the wrong record/value): 2/60
- A0 wrong answers: 4/12 (see below)

**Long-horizon is behavioural, not contextual.** The largest prompt in the whole sweep was **2,207 tokens** against a 16,384 context. Models fail E because they wander (D-2 made 22–25 `compare_records` calls without ever submitting), not because they run out of room.

## Finding 3 — reasoning helps, but selectively and at a cost

6-task subset, thinking off → on (budget 512):

| task | off | on | note |
|---|---|---|---|
| A0-1 | ❌ 0.7 s | ✅ 3.4 s | counting question |
| A-2 | ✅ 8.8 s | ✅ 14.1 s | |
| B-3 | ✅ 11.9 s | ✅ 15.0 s | |
| C-1 | ✅ 10.9 s | ✅ 10.7 s | 4 → 3 calls |
| D-1 | ✅ 6.3 s | ✅ 9.8 s | |
| E-2 | ✅ 27.3 s | ✅ 28.9 s (6 calls vs 10) | fewer calls offset thinking cost |

Net: 5/6 → 6/6. Thinking fixed the arithmetic/instruction failure that no amount of tooling fixes. On tool-heavy tasks it can *reduce* calls enough to pay for itself. n=6, one rep — indicative only.

## Finding 4 — a verifier helps only where there is something to correct

`verifier` (up to 3 submit attempts with environment error messages) gained **E-3** (2/2 reps) — the model had the right record but the wrong cost and used the rejection to fix it — and lost **D-1** (kept submitting against the older audit). Overall unchanged.

`nudged` (system prompt: "you MUST call submit_decision") moved E from 40% → 60% and C from 80% → 60%: net zero. This matches AgentFloor's ablation, where the same intervention was **+100 pp on exactly one model/cell and null elsewhere**.

**Takeaway:** the verifier is not a universal multiplier. It rescues *numeric/format* errors, not *wrong-reasoning* or *never-submits* failures.

## Finding 5 — config was not the bottleneck (but was a latent bug)

First sweep: `-np auto` (4 slots) × `-c 8192` → **2,048 tokens per slot**.
Second sweep: `-np 1` × `-c 16384` + q8_0 KV.

Same aggregate: **73% vs 73%**. Max prompt observed (2,207) *did* exceed the old 2,048 slot, so the first run carried a silent truncation risk; it happened not to change any grade. q8_0 KV had no measurable effect. Use `-np 1` anyway: it is free correctness.

## Concrete failure examples

| Task | What happened | Root cause |
|---|---|---|
| A0-1 | answered **4**; correct is 3 (Atlas, Cinder, Ember active; Borealis/Fjord paused) | counting / constraint tracking |
| A0-2 | listed `Borealis,Cinder,Fjord` as paused | included an active project |
| E-3 | submitted `r10` (ops) instead of `r5` (data) | ignored the team constraint it could have checked |
| D-2 | 22–25 `compare_records` calls, no submission | no termination policy |
| E-1 | 24 calls, no submission | lost the constraint set over 12 turns |
| D-1 (verifier) | submitted against the older audit twice | recency reasoning error, feedback cannot fix it |

## Finding 6 — reliability under sampling (temperature 0.7, k=5, 300 runs)

Temperature 0 made every rep identical, so the earlier `pass@1 == pass@2` was determinism, not reliability.
Re-run with `temperature=0.7`, fixed per-run seeds, 5 reps:

| arm | pass@1 | pass@5 (any) | pass^5 (all) | flaky tasks |
|---|---|---|---|---|
| `native` | 70.0% (95% CI 62–77) | 80% | **57%** | 7/30 |
| `deadline` | **76.0%** (95% CI 69–82) | 83% | **67%** | 5/30 |

| tier | native pass@1 | native pass^5 | deadline pass@1 | deadline pass^5 |
|---|---|---|---|---|
| A0 | 48% | 40% | 52% | 40% |
| A | 100% | 100% | 100% | 100% |
| B | 100% | 100% | 100% | 100% |
| C | 68% | 60% | **100%** | **100%** |
| D | 68% | 20% | **76%** | **60%** |
| E | 36% | 20% | 28% | **0%** |

### What the termination policy actually fixed

`no_submission` failures: **27 → 0**. Every run now submits. But the failures did not disappear — they
changed shape: `payload_mismatch` went 5 → 24. The model was never refusing to answer; it was
refusing to *commit*. Forcing commitment exposes the real error rate.

- **C tier: solved.** 100% pass@1 and 100% pass^5 (was 60% pass^5). The budget notice is exactly the missing scaffolding for branch-then-submit.
- **D tier: reliability doubled.** pass^5 20% → 60%. Same accuracy per attempt, far more consistent.
- **E tier: still broken.** pass@1 28%, pass^5 **0%** — every one of the 30 E runs failed at least one of the five reps, and it now commits to the wrong record instead of stalling. Long-horizon planning is a reasoning problem, not a termination problem.
- **A0: 40% pass^5 on both.** Five short lines and a counting question, and the model gets it right in all five reps less than half the time. This is the sharpest local counter-example to "1B is enough".

**The honest reliability number for this model + harness: 76% pass@1, 67% pass^5, and 0% pass^5 on long-horizon tasks.**

## What this says about the Karpathy claim

| Thesis | Local verdict |
|---|---|
| #1 intelligence ≠ knowledge | Not directly testable here; the A0 errors show reasoning is still a bottleneck at 1.7B |
| #2 core ≈ 1B is enough | **Half true**: 1.7B is enough for A/B (100%), not for E (40–60%) |
| #3 tools/feedback > scale | **Confirmed for short horizon**; feedback alone does not fix long-horizon planning |
| #4 intelligence lives in the system | **Strongly confirmed**: +26 pp from the tool interface alone |
| #5 own it | Confirmed: 20.8 tok/s, $0.0027/passed task, no API |

The honest one-liner: **a 1.7B distill + native tools is a competent single-step and two-step agent, a mediocre multi-step agent, and a poor long-horizon planner — and the harness is worth more than the parameter count in the first two regimes.**

## Comparison with published numbers (not apples-to-apples)

AgentFloor's `qwen3:1.7b` (5 tasks/tier, paraphrases, native tools): A0 76, A 69, B 40, C 9, D 8, E 0.
Ours (easier, shorter tasks): A0 60, A 100, B 100, C 80, D 60, E 40–60.

The absolute values are not comparable — our B/C/D have 1–2 calls, theirs have branching and paraphrases — but the *shape* agrees: short-horizon is solved at ~2B, long-horizon is not.

## Threats to validity

- 30 tasks, 5 per tier; one model, one quant, one machine.
- Exact-match grading; A0 uses substring matching (a correct number inside a long answer could pass).
- Thinking subset n=6, one rep; `nudged` covers C/D/E only.
- The distill has no published benchmarks; results may not transfer to base LFM3-1.7B.
- Vendor LFM3 numbers are unreplicated and harness-configured by Liquid AI.

## Reproduction

```powershell
# terminal 1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_server.ps1 -Port 8080 -Ctx 16384 -Np 1 -ReasoningBudget 0

# terminal 2
python run.py --arm json,native,verifier --reps 2 --out runs.jsonl
python run.py --arm nudged --tier C,D,E --reps 2 --out runs_nudged.jsonl
python run.py --arm native,deadline --reps 5 --temperature 0.7 --out runs_reliability.jsonl
python analyze.py runs.jsonl
python reliability.py runs_reliability.jsonl
python stats.py
```

Artifacts: `runs.jsonl` (main), `runs_v1_np-auto.jsonl` (confounded first pass),
`runs_nudged.jsonl`, `runs_thinking.jsonl`, `runs_reliability.jsonl` (300 runs, k=5),
`results_runs.csv`.