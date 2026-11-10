# Sources: do 1B models with tools beat bigger models?

Annotated evidence collected 2026-11-10 for the claim in `karpathy on SML.txt`.

## Primary source (Karpathy)

### Andrej Karpathy — AGI is still a decade away (Dwarkesh Podcast, 2025-10-17)
- URL: https://www.dwarkesh.com/p/andrej-karpathy
- Transcript, relevant section ~00:12:15–00:13:50 ("LLM cognitive deficits" / pre-training).
- Key quotes:
  - "It's doing two things that are unrelated. Number one, it's picking up all this knowledge... Number two, it's actually becoming intelligent."
  - "You don't need or want the knowledge. I think that's probably holding back the neural networks overall because it's getting them to rely on the knowledge a little too much sometimes."
  - "figure out ways to remove some of the knowledge and to keep what I call this cognitive core."
  - Dwarkesh pushback: "I'm surprised you think in 10 years the cognitive core is still a billion parameters."
- Note: the ~1B figure is a **research prediction**, not a measurement. Karpathy also says AGI is ~a decade away and that current agents "don't work" for general knowledge work.

### Provenance warning on the attached file
- `karpathy on SML.txt` is a **social-media synthesis**, not a transcript.
- The "TwIL … 8.8B" sentence matches X post by `@0xCodez` (https://x.com/0xCodez/status/2118424826968748242).
- The "5 core thesis" bullets are a paraphrase, not verbatim Karpathy.
- The linked 16-minute video is a **third-party breakdown** ("Anthony Batt", getcoai.com), URL https://youtu.be/6P2ItWQY_uw.

## Evidence FOR the thesis

### AgentFloor (arXiv 2605.00334, 2026-05-01)
- https://arxiv.org/abs/2605.00334 | HTML: https://arxiv.org/html/2605.00334v1
- 16 open-weight models (0.27B–32B) + GPT-5, 6-tier tool-use ladder, **16,542 scored runs**, deterministic abstract tools, pre-registered ±10pp margins.
- Sub-5B results that matter:
  | Model | A0 | A | B | C | D | E |
  |---|---|---|---|---|---|---|
  | qwen3:0.6b | 80 | 44 | 39 | 4 | 8 | 0 |
  | **qwen3:1.7b** | 76 | **69** | 40 | 9 | 8 | 0 |
  | qwen3.5:2b | 44 | 68 | 80 | 40 | 32 | 0 |
  | granite4:3b | 84 | 80 | 56 | 16 | 4 | 0 |
  | ministral-3:3b | 72 | **88** | 56 | 16 | 20 | 4 |
  | nemotron-3-nano:4b | 92 | 76 | 72 | 20 | 36 | 0 |
- Aggregate: gemma4:26b 60.0% vs GPT-5 59.6% (equivalent at ±10pp), 15× cheaper per passed task, 2.5× faster.
- Cliff: B→C is the steepest step. **No model clears 60% on C, D, or E.** Long-horizon E: GPT-5 10%, best open-weight 16% (ministral-3:8b).
- Interventions are model-specific: explicit-submission prompt gave +100pp on exactly one model (ministral-3:8b on E1) and was null elsewhere; a plan/execute/submit decomposition prompt **hurt every model tested**.

### Small Language Models are the Future of Agentic AI (NVIDIA, arXiv 2506.02153)
- https://arxiv.org/abs/2506.02153 | https://research.nvidia.com/labs/lpr/slm-agents
- Position paper: SLMs are "sufficiently powerful, inherently more suitable, and necessarily more economical" for many agent invocations.
- Argues for **heterogeneous** systems (SLM for routine calls, LLM for hard ones) and per-task fine-tuning — not a 1B generalist.
- Cites 2–9B models matching larger models on tool-calling, structured extraction, templated generation, short-context reasoning after light fine-tuning.

### TinyAgent (BAIR / EMNLP 2024 demo)
- https://bair.berkeley.edu/blog/2024/05/29/tiny-agent/ | https://github.com/SqueezeAILab/TinyAgent
- Fine-tuned **1.1B** + ToolRAG: **80.06%** success vs GPT-4-Turbo **79.08%**, 4-bit, 2.9s latency, on a 16-tool macOS assistant.
- Off-the-shelf TinyLlama-1.1B on the same task: **12.71%**. The gain is fine-tuning + harness, not raw size.
- Caveat: single narrow in-distribution task. On BFCL the same TinyAgent-1.1B scores only **19.7%** (TinyLLM paper).

### LFM3-1.7B vendor card (Liquid AI, 2026-10-27)
- https://huggingface.co/LiquidAI/LFM3-1.7B | https://www.liquid.ai/blog/lfm3
- Vendor-reported, vLLM BF16, no independent replication.
- Beats Qwen3.5-9B on: LiveClaw 45.60 vs 35.77; BFCL v4 71.39 vs 62.83; ToolSandbox 80.36 vs 76.41; WebArena-Verified 38.42 vs 28.94; AutomationBench 41.29 vs 15.10; IFEval 96.66 vs 92.08.
- Loses to Qwen3.5-9B on: GPQA 63.37 vs 80.40; HLE 7.17 vs 16.41; RULER-128K 65.56 vs 87.11; SWE-bench Verified 43.40 vs 51.20; Terminal-Bench 12.92 vs 17.98.
- Card explicitly: "not recommended for agentic coding or complex multi-step reasoning due to its small size."
- Vendor claim: "can power agentic applications that used to need 9B parameters."

## Evidence AGAINST / limits

### Measuring the Microtask Eligibility Gap (arXiv 2610.00025, 2026-09-01)
- https://arxiv.org/abs/2610.00025
- Qwen3 0.6/1.7/4/8B, 4 harness microtasks, pre-registered thresholds with CI-aware eligibility.
- **0 of 16 configurations pass.** Replicates on Llama-3.x (12/12 ineligible). 4-bit quantization moves none into eligibility; "the gap tracks model size more than precision."
- Practical recommendation: keep a non-LLM baseline in front, use the SLM only where the baseline fails.

### Beyond Fluent Generation (arXiv 2609.07370, 2026-09-07)
- https://arxiv.org/abs/2609.07370
- Sub-2B MCP-style tool calls on CPU. Qwen2.5-1.5B: 75% greedy / 79% sampling under a recovery parser; Qwen2.5-0.5B: 72% → **32%** under sampling; Phi-1.5 **0%**; Pythia/TinyLlama ≤7%.
- **Only 5 of 1,000 raw responses were directly parseable as JSON.**
- Failure mass: 89.4% of failures terminate at JSON recovery.

### TinyLLM: SLMs for agentic tasks on edge (arXiv 2511.22138, 2025-11-27)
- https://arxiv.org/html/2511.22138
- BFCL results: xLAM-2-3b 65.7% overall / 55.6% multi-turn; Qwen3-4B 62.0/35.3; **Qwen3-1.7B 55.5/16.9**; xLAM-2-1b 54.0/8.4; Qwen3-0.6B 45.8/1.4.
- Multi-turn reliability collapses below ~3B.

### Field report: Llama 3B ReAct (dev.to, 2026-04-03)
- https://dev.to/anak_wannaphaschaiyong_11/why-small-llms-fail-at-tool-calling-the-shocking-discovery-from-our-llama-3b-benchmark-5lg
- 9 tasks, ReAct + tools: **0 tool invocations**, 11% accuracy. Low rigour, useful anecdote.

### E-Bench (arXiv 2607.23722)
- https://arxiv.org/html/2607.23722
- Multi-step state-changing tasks: best models Pass^3 < 60%; even top agents intermittently succeed. Reliability, not peak capability, is the bottleneck.

## Secondary / context

- Poolside's Eiso Kant: gains from a small model come from **behaviour** (persistence, verification, backtracking), not just intelligence — https://getcoai.com/video/poolsides-eiso-kant-on-why-small-models-can-do-big-things-and-why-mcp-is-stupid/
- Karpathy video breakdown (third-party) — https://getcoai.com/video/andrej-karpathy-bigger-models-arent-the-answer/
- LFM3-1.7B independent commentary / caveats — https://slm.expert/models/lfm3-1.7b/