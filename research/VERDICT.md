# Verdict: Karpathy's small-model thesis vs. the evidence

Date: 2026-11-10. Sources: see `SOURCES.md`.

## One-line verdict

**Directionally confirmed, but only inside a narrow regime.** A ~1B model plus tools, a tight verifier loop and task-specific tuning can match or beat a frontier model *on that task*, at a small fraction of the cost. The strong reading — "1B is generally enough for agent work" — is **not** supported.

## Thesis by thesis

### 1. "Intelligence was never the knowledge."
**Supported as a framing, not as a measurement.**
Karpathy's own Dwarkesh interview (2025-10) makes exactly this argument: pre-training does two unrelated things (memorisation and the emergence of reasoning circuits), and the memorised part may actively hurt. The measurable consequence is real: LFM3-1.7B has 92.9% non-hallucination on AA-Omniscience while scoring only 7.1% accuracy — it knows what it doesn't know — and search nearly doubles its HLE score (7.17 → 13.90). But no experiment isolates "pure reasoning" from knowledge, so this remains a hypothesis.

### 2. "The core might fit in ~1B params."
**Plausible, unproven.** No published model demonstrates frontier-level general reasoning at 1B. What *is* demonstrated is that 1–2B models are sufficient for **structured, narrow** work: BFCL single-turn ~55–70%, instruction following ~90–97% for a good 1.7B. The 1B figure is a prediction about a future distillation recipe, not a current result.

### 3. "Size stopped being the bottleneck; tools and feedback matter more."
**Supported for short-horizon work, refuted for long-horizon.**
- AgentFloor: sub-5B models clear the 80% reliability bar on single-tool use (ministral-3:3b = 88%); a 26B open model ties GPT-5 overall.
- But the same study shows a **cliff** at branching / multi-source synthesis / long-horizon planning: qwen3:1.7b drops from 69% (single tool) to 9% / 8% / 0%. No model in the corpus clears 60% on C/D/E.
- Microtask Eligibility Gap: **0/16** off-the-shelf SLM configurations meet practitioner thresholds for harness microtasks.

### 4. "Intelligence lives in the system, not the weights."
**Strongly supported — this is the best-evidenced thesis.**
- TinyAgent: same data, same 1.1B base — 12.7% off-the-shelf vs 80.1% after fine-tuning + ToolRAG, beating GPT-4-Turbo.
- AgentFloor: interventions that help one model are null on others, and the "obvious" plan/execute/submit prompt **hurt every model tested**. The harness is not a free universal multiplier; it must be co-designed with the model.
- Beyond Fluent Generation: 995/1000 raw sub-2B tool calls needed repair. The harness's parser/schema validation is doing as much work as the model.

### 5. "You can own it."
**True and not really contested.** Cost/latency numbers: AgentFloor's cheapest reliable cell is $0.00046 per passed task (granite4:3b on a Mac) vs $0.0327 for GPT-5 — **71× cheaper**; local runs are 2.5× faster per passed task at matched accuracy.

## What the thesis gets wrong

1. **Reliability, not capability, is the wall.** Peak single-shot scores look fine; pass^3 and multi-turn scores collapse (Qwen3-1.7B multi-turn 16.9%; xLAM-1B 8.4%). Agents need repetition.
2. **The 1B-core story skips the fine-tune.** Every strong 1B result is in-distribution after targeted tuning. Zero-shot 1B agent performance is poor.
3. **Knowledge is not free to remove.** LFM3-1.7B loses badly on GPQA (63.4 vs 80.4) and RULER-128K (65.6 vs 87.1). Retrieval closes some of it, not all.
4. **The evidence base is vendor-heavy.** LFM3's agentic table is Liquid AI's own, unreplicated; seven of ten agent rows run through harnesses the vendor configured.
5. **Provenance.** The attached text is a social-media summary, not a transcript. Treat the "5 theses" as a useful synthesis, not a citation.

## Bottom line for a personal experiment

The testable claim is **not** "does a 1B beat GPT-5?" It is:

> On structured tool tasks, does LFM3-1.7B's success rate depend more on the harness (native tools vs JSON emulation, verifier retries) than on the model?

If Arm C (verifier) ≫ Arm A (JSON), the thesis is confirmed in the only sense that matters for builders.

## Local replication (2026-11-10)

Ran the test above on `LFM-3-Coder-Claude-Distill.Q5_K_M` (see `bench/RESULTS.md`):

| arm | all tiers |
|---|---|
| JSON-in-text | 47% |
| native tools | 73% |
| verifier | 73% |

- **Harness interface: +26 pp** on identical weights — thesis #4 confirmed.
- Tier curve A/B 100% → C 80% → D 60% → E 40–60% — thesis #3 confirmed only for short horizons.
- Explicit-submission prompt and verifier retries: net zero overall, large per-cell swings — interventions are model-specific, as AgentFloor found.
- Thinking (+512-token budget): fixed the one counting failure, 5/6 → 6/6 on a 6-task subset, at +1–3 s per call.
- **Sampled reliability (temp 0.7, k=5): 76% pass@1 / 67% pass^5 for the best harness vs 70% / 57% for plain native tools.** A budget-aware termination policy removed all 27 "never submits" failures and took C to 100% pass^5 — but converted them into wrong submissions on D/E, leaving E at **0% pass^5**.