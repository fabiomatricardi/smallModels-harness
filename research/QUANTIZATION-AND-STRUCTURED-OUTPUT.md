# Quantization, structured output and reasoning: what the evidence actually supports

Notes recorded 2026-11-11, during the `smallModels-harness` experiment.
Scope: GGUF / llama.cpp-style quantisation (Q4_K_M, Q5_K_M, Q6_K, Q3_K_M), not GPTQ/AWQ serving.

---

## The claim being tested

> "Q5_K_M is the minimum acceptable for structured outputs, Q6 is the sweet spot.
> At Q4_K_M and below, the output structure degrades heavily."

**Verdict: directionally right, numerically over-stated.**

- Lower precision does hurt format-sensitive tasks first, and this model is small enough that the
  damage is proportionally larger than on a 70B.
- But there is no academic result that establishes **Q5_K_M as a minimum** or **Q6_K as the sweet
  spot**. Those are practitioner heuristics.
- "Degrades heavily at Q4" is **model-dependent**: the same bit-width costs one model 2 points and
  another 45.

---

## Evidence table

| Claim | Evidence | Verdict |
|---|---|---|
| Lower bits → more degradation | llama.cpp deltas at 7B: Q6_K **+0.0044** ppl, Q5_K_M **+0.0142**, Q4_K_M **+0.0535**, Q3_K_M **+0.2437** | Confirmed; a smooth 3–4× step per level, not a cliff |
| Structured output is hit before chat | Practitioner comparisons report "more frequent schema violations" at Q4_K_M, "reliable" at Q6_K / Q8_0 | Plausible, thin evidence (blogs) |
| Q4_K_M "degrades heavily" | Qwen3-1.7B at Q4KM: 82.8 → 80.5 (−2.3 pp) without thinking, 82.8 → 82.9 with thinking. Gemma-3 1B: 23.9 → 8.7. Qwen3-0.6B: 62.3 → 16.8 | Model-dependent; not universal |
| Q5_K_M is the minimum for structured output | No academic source; practitioner rule | Unconfirmed |
| Q6_K is the sweet spot | One 2026 survey argues Q5/Q6 recover **<1%** over Q4 and are "rarely worth it" | Contested |
| W4A16 / W8A8 can be lossless | Liu et al., COLM 2025, 1.5B–70B | Confirmed for weight+activation settings |

**Academic anchors**

- *Quantization Hurts Reasoning?* — Liu et al., COLM 2025, arXiv:2504.04823. Systematic study of
  DeepSeek-R1 distills (1.5B–70B), QwQ-32B, Qwen3-8B. Finding: W8A8 and W4A16 can be lossless;
  lower bit-widths introduce significant accuracy risk; **model size, model origin and task
  difficulty** determine the damage.
- *Small Reasoning Models are Instruction Followers in Function Calling* — arXiv:2608.22472 (Aug
  2026). Explicitly tests **Q4_K_M function calling**: reasoning-oriented models are robust
  (Qwen3-4B: 94.1 → 93.5), non-reasoning small models collapse (Gemma-3 1B: 23.9 → 8.7).
- *The case for 4-bit precision: k-bit Inference Scaling Laws* — Dettmers & Zettlemoyer,
  arXiv:2212.09720. Finds 4-bit is the best accuracy-per-bit operating point; **larger models
  tolerate lower precision better**.
- *Scaling Laws for Precision* — Kumar et al., ICLR 2025. Notes that over-trained models degrade
  more when quantized at inference.

---

## "Model size matters for reasoning, not for parseability" — in plain terms

There are two different jobs happening in one model, and they fail differently.

**Job 1: produce well-formed output.** A tool call is a rigid, repetitive pattern: a function name,
then arguments in a fixed order, with quotes and braces in the right places. The model has seen this
pattern millions of times. It is a *surface* skill, like handwriting or filling in a form. It needs
very little "thinking" and very little model capacity.

**Job 2: decide what to output.** Choosing *which* record is the right one, whether the constraint
holds, whether the newer audit should win — that is a *deep* skill. It requires holding several
facts at once, comparing them, and not losing track across steps.

Quantization damages both, but not equally:

- **Formatting is error-tolerant.** If one weight is slightly off, the model may wobble on a token
  and still produce a valid call, or the harness's parser/template repairs it. The schema itself is
  a strong constraint: most of the token sequence is determined by the format, not by knowledge.
  Grammar-constrained decoding can make the structure correct *by construction*.
- **Reasoning is error-amplifying.** A small numerical error early ("cost is 55, not 65") changes the
  branch you take, which changes the record you submit, which changes the answer. Errors compound
  over steps. Nothing validates the intermediate decision for you.

**Why model size enters.** A large model has more redundant weights and wider representations, so a
little quantisation noise gets averaged out. A 1.7B model has little redundancy: the same absolute
noise is a larger fraction of its capacity. That is why the same Q4 quant that is "basically fine"
on a 70B can visibly damage a 2B model's reasoning.

**Put together:** as precision drops, expect the *form* to survive longer than the *judgement*. You
get valid tool calls containing the wrong value. That is exactly the failure signature we saw in the
E-tier even at Q5/Q6: the model submits a well-formed payload pointing at the wrong record.

One caveat: at very low precision (Q2 and below) even the surface skill starts to break, because the
model loses the token-level patterns that produce the format in the first place.

---

## Is Q3 acceptable for models larger than ~8B?

Mostly yes for chat, cautiously yes for tool calls, and risky for reasoning-heavy work.

| Source | Measurement | Q3 result |
|---|---|---|
| llama.cpp quantize table (7B reference) | perplexity delta | Q3_K_M **+0.2437** — about 4.5× worse than Q4_K_M and 17× worse than Q5_K_M |
| 2026 survey table | perplexity / GSM8K | Llama-4 8B: +4.8% ppl, GSM8K 78.2 → **72.1** (−7.8% relative); Qwen3-32B: +5.0% ppl, GSM8K 89.1 → **84.8** (−4.8%) |
| *Which Quantization Should I Use?* (arXiv:2601.14277) | Llama-3.1-8B, unified llama.cpp eval | **Q3_K_M is Pareto-optimal**: 75% size reduction at ≈2.02% average loss |
| Dettmers k-bit scaling laws | cross-size comparison | Larger models tolerate lower precision better; 4-bit remains the best accuracy-per-bit point |
| Practitioner rule | cross-family | A Q4 70B usually beats a Q8 13B — parameters buy more than the last bits, *until you drop past Q3* |

**Reading it honestly:**

- At 8B, Q3_K_M costs roughly **2% average** across benchmarks and **5–8% relative** on math-style
  reasoning. Acceptable for chat and retrieval; noticeable in agent work.
- At 32B+, relative reasoning loss shrinks (≈5% on GSM8K in the table above, less on many tasks),
  but it does not vanish.
- **Tool calls specifically:** the format usually survives Q3; the *arguments* and *tool selection*
  are where degradation shows. There is much less published evidence here than for math.
- **Method matters as much as bit-width.** `Q3_K_S` is worse than `Q3_K_M`; an `IQ3` or imatrix
  quant can be materially better than a plain Q3 at similar size. Never compare by the number alone.
- **Constrained decoding changes the calculus:** if the harness enforces the schema, malformed calls
  become nearly impossible, and Q3's format risk mostly disappears. Reasoning quality does not
  improve.

**Rule of thumb**

| Situation | Recommendation |
|---|---|
| >8B, chat/RAG, memory-bound | Q3_K_M or a good IQ3 is acceptable |
| >8B, agentic tool use, arguments matter | Q4_K_M or better; test on your own tool set |
| >8B, math/planning/long-horizon | Q4_K_M minimum; Q5_K_M if it fits |
| ≤4B, any structured work | Q5_K_M minimum; Q6_K if it fits |
| Any size, schema must be exact | Use grammar/JSON-schema constrained decoding |

---

## What our own experiment can and cannot say

We compared:

- community distill at **Q5_K_M** — native 70.0% pass@1, 57% pass^5; deadline 76.0%, 67%
- official base at **Q6_K** — native 68.7%, 60%; deadline 77.3%, 67%

The differences are inside the confidence intervals, so this is **not** evidence about quantization:
the two files also differ in fine-tuning. It is consistent with "Q5 vs Q6 makes no measurable
difference on this benchmark", and inconsistent with a large Q5→Q6 cliff. It says nothing about Q4
or Q3, which we have not run.

---

## How to actually settle it (next experiment)

A format-and-reasoning stress test on one model family, holding everything else constant:

1. Download the **same** base model at Q3_K_M, Q4_K_M, Q5_K_M, Q6_K (optionally Q8_0).
2. Run one fixed suite: ~200 tool-call prompts with nested JSON, enums, numbers and booleans, plus
   ~50 short multi-step tasks.
3. Measure separately:
   - **parse rate** (is the call syntactically valid?)
   - **schema-valid rate** (does it match the schema?)
   - **argument accuracy** (are the values correct?)
   - **task accuracy** (is the decision correct?)
4. Repeat with and without grammar-constrained decoding.

That separates *parseability* from *reasoning* directly, which no perplexity table can do.

---

## Sources

- Liu et al., *Quantization Hurts Reasoning?*, COLM 2025 — https://arxiv.org/abs/2504.04823
- Taheri et al., *Small Reasoning Models are Instruction Followers in Function Calling* —
  https://arxiv.org/abs/2608.22472
- Dettmers & Zettlemoyer, *The case for 4-bit precision* — https://arxiv.org/abs/2212.09720
- Kumar et al., *Scaling Laws for Precision*, ICLR 2025 —
  https://openreview.net/forum?id=wg1PCg3CUP
- *Which Quantization Should I Use? A Unified Evaluation of llama.cpp Quantization on
  Llama-3.1-8B-Instruct* — https://arxiv.org/abs/2601.14277
- llama.cpp quantisation table and discussion — https://github.com/ggml-org/llama.cpp/discussions/2094
- Local LLM quantization benchmarks (2026 survey) — https://presenc.ai/research/local-llm-quantization-quality-benchmarks-2026
- Practitioner quant comparison — https://www.sitepoint.com/q4-vs-q6-vs-q8-quantization-local-llms/
- vLLM constrained decoding for tool calls — https://www.ubicloud.com/blog/fixing-tool-call-accuracy-in-vllm