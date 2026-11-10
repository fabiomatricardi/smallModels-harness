# How to Get Reliable Agent Work Out of a 1.7B Model (and Where It Still Fails)

*A budget-aware termination policy took me from 70% to 76% task success and from 57% to 67% pass^5. Here are the exact flags, the loop, and the one tier that stayed at zero.*

**Fabio Matricardi** · 10 November 2026 · ~12 min read

---

Andrej Karpathy has spent the past year arguing that the interesting part of intelligence is not the memorised internet. Strip the knowledge out, keep the reasoning, and what remains — the "cognitive core" — might fit in about a billion parameters.[^1] If that is true, a small model with good tools should do real agent work: read data, call functions, check constraints, submit an answer.

I tested it cheaply: no cluster, no API key. The model is a community distill of LiquidAI's LFM3-1.7B — 1.73B parameters, Q5_K_M, fine-tuned on Claude reasoning traces.[^6] It runs on the Intel Arc integrated GPU inside a Core Ultra 5 235U, with 31.5 GB of shared memory, at **20.8 tokens per second**, for about $0.003 per solved task.

Here is the short version, because you are probably here for the actionable part:

1. **The tool interface was worth 26 percentage points.** Same weights, same tasks: native tool calling 73%, JSON-in-text 47%.
2. **Reliability is much worse than accuracy.** The best harness reached 76% pass@1 but only 67% pass^5 — and **0% pass^5 on long-horizon tasks**.
3. **The harness fixes commitment, not judgment.** A termination policy removed every "never submitted" failure and sharply raised multi-step reliability; a verifier corrected wrong numbers but never wrong reasoning.

Karpathy is right that the system matters more than the weights. He is wrong that the core is small enough — or rather, "small enough" is the wrong question.

---

## The setup: 300 runs, one laptop, no API key

I built a deterministic benchmark of 30 tasks across six tiers, modelled on the AgentFloor capability ladder.[^3] The tiers run from A0 (instruction following, no tools) through A (one call), B (two-tool chain), C (branch on an intermediate value), D (multi-source synthesis with conflicts) to E (long-horizon planning under persistent constraints, 8–12 calls).

All 30 tasks run against eight deterministic tools over an in-memory database — search, lookup, attribute read, options, constraint check, compare, compute, and submit. There is no filesystem, no network, no clock, and no route to training-data contamination. Grading is exact match on the submitted payload, plus a required tool sequence.

Four harness arms, described below, ran the same tasks. The main sweep used temperature 0 and two repetitions; the reliability sweep used temperature 0.7, five repetitions, and a fixed seed per run.

The server configuration matters:

```powershell
llama-server.exe -m models/LFM-3-Coder-Claude-Distill.Q5_K_M.gguf `
  -c 16384 -np 1 -ngl 999 `
  -ctk q8_0 -ctv q8_0 -fa on `
  --jinja --reasoning-budget 0 --host 127.0.0.1 --port 8080
```

`-np 1` is the one people miss. The default is `-1` (auto, usually four slots), which silently divides your context window by four — 16K becomes 4K, and 8K becomes 2K. I lost a first sweep to that. The quantised KV cache (`q8_0` for keys and values) halves cache memory and had no measurable effect on scores. Flash attention was on.

**Full disclosure:** the model is a third-party distill with no published benchmarks, not Liquid AI's base checkpoint. The tasks are mine, five per tier is a probe rather than a leaderboard, five repetitions is a weak tail estimate, and there is no base-model control. Treat the *shape* as the finding; the absolute numbers are provisional.

---

## Start with the interface, not the model

Before touching the model, I changed only how tools were presented.

In the first arm, the tools were described in the system prompt and the model had to emit a JSON object per turn:

```json
{"tool": "lookup_record", "args": {"id": "r5"}}
```

In the second arm, the same eight tools were passed through the server's OpenAI-compatible `tools` field, with the model's native XML tool-call template doing the formatting.

| Arm | Pass@1 (30 tasks) |
|---|---|
| JSON-in-text | **47%** |
| Native tool calls | **73%** |

Same weights. Same tasks. Same machine. A 26-point swing.

The failure mode was not subtle: 28 "no submission" runs out of 60 in the JSON arm, 10 in the native one. The model was capable of the work and kept losing the transaction — look up the right record, then format the next action incorrectly, then wander.

This is the strongest evidence I have for Karpathy's fourth thesis: intelligence lives in the system, not the weights. **Before you buy a bigger model, check your tool interface.** A native tool call is worth more than several billion parameters on short tasks.

But conceding the point makes the next result more interesting, not less.

---

## Measure pass^k, not pass@1

My first sweep used temperature 0, so every repetition produced the identical answer. "Reliability" was an illusion: pass@1 equalled pass@2 by construction. You would not deploy an agent that way; you would sample, retry, and care about whether it succeeds *every* time.

So I re-ran with temperature 0.7, fixed seeds, and five repetitions per task. `pass^k` means all k attempts succeed — the number you need if a failure costs money. `pass@k` means at least one succeeds, which is what a retry loop buys you.

| Harness | pass@1 | pass@5 (any) | pass^5 (all) | Flaky tasks |
|---|---|---|---|---|
| Native tools | 70.0% (95% CI 62–77) | 80% | **57%** | 7/30 |
| Native + deadline | **76.0%** (95% CI 69–82) | 83% | **67%** | 5/30 |

And by tier, `pass^5`, with the deadline policy described below:

| Tier | Native tools | With deadline |
|---|---|---|
| A0 (no tools) | 40% | 40% |
| A (one tool) | 100% | 100% |
| B (two-tool chain) | 100% | 100% |
| C (branch) | 60% | **100%** |
| D (multi-source) | 20% | **60%** |
| E (long horizon) | 20% | **0%** |

This is the cliff. Single-tool and two-step work is solved at 1.7B — 100% across five attempts, not "good for its size". Branching is mostly solved with the right scaffold. Multi-source synthesis is where it starts to wobble. Long-horizon planning never becomes reliable.

The E-tier failures were not context overflows. The largest prompt in the sweep was **2,207 tokens** against a 16,384-token window. The model ran out of discipline, not room: one run made 24 tool calls, never submitted, and hit the step limit.

That distinction matters for how you fix it — and it is not unique to my rig. NVIDIA's position paper argues that small models are the economical default for routine agent calls, explicitly inside heterogeneous systems rather than as replacements.[^4] A September 2026 study of harness microtasks found that 0 of 16 off-the-shelf small-model configurations met practitioner reliability thresholds.[^5] The pattern is consistent: small models are good at *calls*, not at *plans*.

---

## Give the model a deadline

The most common failure in the native arm was not a wrong answer. It was no answer. Twenty-seven of 150 runs stopped calling tools before calling `submit_decision`. The model would search, look up, compare, compare again, and then simply stop.

So I implemented the policy a production harness would use:

```text
when 2 or fewer calls remain:
    inject "BUDGET NOTICE: N call(s) left. Call submit_decision now."

on the final allowed call:
    restrict the tool list to submit_decision only
```

That is the whole intervention. No fine-tuning, no retries, no model swap.

Result: **`no_submission` went from 27 to 0.** Every run submitted something.

But the failures did not disappear; they changed shape. `payload_mismatch` went from 5 to 24. The model had never been unable to answer — it had been unwilling to commit. Forcing commitment revealed what it actually believed, which was often wrong.

The tier-level effect is the payoff:

- **C tier: 100% pass@1 and 100% pass^5**, up from 60%.
- **D tier: pass^5 went from 20% to 60%** at roughly the same accuracy per attempt.
- **E tier: pass@1 fell from 36% to 28%, and pass^5 to 0%.**

On long-horizon tasks the deadline did not help: the model was not stalling, it was confidently picking the wrong record. Forcing a submission just made the error visible.

The lesson generalises: **a termination policy makes a small model honest, not smart.** If your failures are "never finishes", it is the highest-value change you can make. If your failures are "finishes with the wrong answer", it will only improve your logging.

---

## Use a verifier for numbers, never for judgment

The next obvious lever is feedback: let the environment reject a bad submission, explain why, and allow up to three retries.

I made the rejection check facts, never the gold answer. Submit the wrong cost and the tool replies with the actual cost; violate a stated constraint and it names the constraint. That is legitimate feedback, not answer leakage.

The result was almost nothing overall — and that is the interesting part.

It fixed one task completely. On E-3, the model had the right record and the wrong cost; the rejection told it the actual value, and it corrected itself in both repetitions. It broke another: on D-1, it kept re-submitting against the older of two audits, because the problem was recency reasoning, and no error message can tell you which source is newer.

Net change across all 30 tasks: zero.

Feedback loops are excellent at *verifiable, local* errors — a wrong number, a missing field, a malformed payload. They are useless at *judgment* errors — the wrong record, an ignored constraint, the wrong authoritative source. Karpathy's "tight feedback loop" is true, but narrower than it sounds: the loop only helps where the environment can tell right from wrong without knowing the answer.

---

## Turn thinking on for arithmetic — and cap it

LFM3 ships with a reasoning mode. I tested six representative tasks with thinking off and on, capped at a 512-token reasoning budget.

| Task | Thinking off | Thinking on |
|---|---|---|
| A0-1 (counting) | ❌ 0.7 s | ✅ 3.4 s |
| A-2 | ✅ 8.8 s | ✅ 14.1 s |
| B-3 | ✅ 11.9 s | ✅ 15.0 s |
| C-1 | ✅ 10.9 s | ✅ 10.7 s |
| D-1 | ✅ 6.3 s | ✅ 9.8 s |
| E-2 | ✅ 27.3 s (10 calls) | ✅ 28.9 s (6 calls) |

Five of six became six of six. On E-2, thinking paid for itself: it used six tool calls instead of ten, and the saved calls offset the reasoning tokens.

Now the kicker. A0-1 is a six-line passage listing which projects are active, and the question is how many are active. The answer is three. With thinking off, the model answered **four** — every single repetition. With thinking on, three.

No external knowledge required: no retrieval, no tool use, no ambiguity. Just six short sentences and a count. Across five attempts at temperature 0.7, it gets all five right only **40% of the time**. On A0-2, it listed an active project among the paused ones.

This is where the "cognitive core" story gets shaky. If you strip the knowledge away and what remains is a billion-parameter engine that cannot reliably count six lines, then the thing you have isolated is not a reasoning core. It is a very fast pattern matcher with a small working memory.

---

## Know where the cliff is

At **20.8 tokens per second**, a 1.7B model on an integrated GPU costs about **$0.003 per passed task** (amortising the machine at $0.50 per hour). A frontier model at posted prices is roughly an order of magnitude more per call. On single-tool and two-step work, the small model is not a compromise; it is the correct engineering choice.

But cost per *passed* task is not cost per *reliably* passed task. Multiply by the failure rate and the retries. If you are routing work today, this is the deliverable:

| Work type | What I would use |
|---|---|
| Classification, extraction, single tool call | 1.7B, locally, confidently |
| Two-step lookup → submit | 1.7B with native tools |
| Branching with a clear predicate | 1.7B + deadline policy |
| Multi-source conflict resolution | 1.7B, but verify the output |
| Long-horizon planning with persistent constraints | Not this model |

The last row is not a tuning problem. It is a capability gap that survived every harness change I made. Route the top three rows to the small model. Keep the bottom row on something bigger, or restructure the task so it stops being long-horizon.

---

## What I'd do differently on the next run

Three things would make this result much harder to argue with.

**Run the base model.** Everything here used a community distill. Its tool template may be better or worse than Liquid AI's base checkpoint. A Q5 GGUF of `LiquidAI/LFM3-1.7B` is 1.2 GB and one evening away.

**Make the tasks harder to game.** Five tasks per tier is a probe. I would add paraphrase variants — same capability, different wording — because a model that passes only the exact phrasing has not demonstrated the capability. AgentFloor used four paraphrases per task for exactly this reason.

**Test a real fine-tune.** My result is zero-shot. The strongest small-model evidence is not: TinyAgent took a 1.1B model from 12.7% to 80.1% on a 16-tool task with targeted fine-tuning and tool retrieval. That is the version of the thesis I have not tested, and the one most likely to embarrass my conclusion.

What would change my mind? A 1.7B model that holds 80% pass^5 on tier E with a deadline and a verifier, on tasks it has never seen. I do not have that result.

---

## The core is real, the reliability is not

Karpathy's argument is directionally right, and my own best result proves it: same weights, 26 points of difference, purely from the interface. If you are building agents, spend your next week on the harness, not the model card.

But "a 1B cognitive core" is a statement about capability, and capability is not what breaks agents. Reliability is. My 1.7B model is perfect on the tasks I would have used to demo it, and 0% reliable on the tasks where an agent actually has to think ahead.

So here is the revised claim I would defend: **a 1.7B model plus a well-built harness is a genuinely useful worker for short, verifiable tasks, and a poor planner.** It is not a brain. It is a very fast intern with a checklist — and if you give it the checklist, it will surprise you. Just don't put it in charge of the project.

---

### Reproduce it

```powershell
# terminal 1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_server.ps1 -Port 8080 -Ctx 16384 -Np 1

# terminal 2
python run.py --arm json,native,verifier --reps 2 --out runs.jsonl
python run.py --arm native,deadline --reps 5 --temperature 0.7 --out runs_reliability.jsonl
python reliability.py runs_reliability.jsonl
```

Raw data: [`runs_reliability.jsonl`](https://github.com/fabiomatricardi/smallModels-harness/blob/main/bench/runs_reliability.jsonl) · Tasks: [`tasks.json`](https://github.com/fabiomatricardi/smallModels-harness/blob/main/bench/tasks.json) · Harness: [`run.py`](https://github.com/fabiomatricardi/smallModels-harness/blob/main/bench/run.py)

---

[^1]: Andrej Karpathy, interviewed by Dwarkesh Patel, *AGI is still a decade away*, 17 October 2025. Transcript: https://www.dwarkesh.com/p/andrej-karpathy. The "cognitive core" phrasing and the ~1B estimate appear in the section on pre-training and knowledge. Note that the widely shared "5 theses" summary is a paraphrase, not a transcript.

[^3]: Karmakar & Chatterjee, *AgentFloor: How Far Up the tool use Ladder Can Small Open-Weight Models Go?*, arXiv:2605.00334, May 2026. https://arxiv.org/abs/2605.00334

[^4]: Belcak et al., *Small Language Models are the Future of Agentic AI*, NVIDIA Research, arXiv:2506.02153. https://arxiv.org/abs/2506.02153

[^5]: Hu & Ramachandran, *Measuring the Microtask Eligibility Gap*, arXiv:2610.00025, September 2026. https://arxiv.org/abs/2610.00025

[^6]: `Schnuckade/LFM-3-Coder-Claude-Distill`, a community fine-tune of `LiquidAI/LFM3-1.7B`. Model card: https://huggingface.co/LiquidAI/LFM3-1.7B