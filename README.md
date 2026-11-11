# SML-agents — can a 1.7B model do real agent work?

A local, reproducible test of Andrej Karpathy's small-model thesis: *strip the memorised knowledge, keep the
reasoning, and a ~1B "cognitive core" plus tools should be enough for agent work.*

Everything here runs on one laptop with no API key: a 1.16 GiB GGUF, an Intel iGPU, and a purpose-built
30-task agent benchmark with four harness arms.

**Author:** Fabio Matricardi · fabio.matricardi@gmail.com
**Repository:** https://github.com/fabiomatricardi/smallModels-harness

**Status (2026-11-10):** research done · benchmark built · 516 runs collected · article draft v1 written ·
published to GitHub. llama-server is stopped. Nothing is scheduled.

---

## TL;DR

| Finding | Number |
|---|---|
| Tool interface vs JSON-in-text, same weights | **47% → 73%** (+26 pp) |
| Reliability under sampling (temp 0.7, k=5) | **57% pass^5** native → **67%** with a deadline policy |
| Long-horizon (tier E) reliability | **0% pass^5** even with the best harness |
| "No knowledge required" counting task | **40% pass^5** |
| Throughput / cost | **20.8 tok/s**, **~$0.003 per passed task** |

**Verdict:** Karpathy is right about systems — the harness was worth more than several billion parameters.
He is wrong that the core is small *enough*: at 1.7B, short verifiable tasks are solved reliably and
planning is not, and no harness change closed that gap.

> Note on provenance: `karpathy on SML.txt` in this folder is a social-media **paraphrase** ("5 theses",
> "TwIL 8.8B"), not a transcript. The primary source used in the article is the Dwarkesh interview
> (2025-10-17). See `research/SOURCES.md`.

---

## File structure

```text
C:\myAI\20261110.SML-agents\
├─ README.md                     ← this file: purpose, decisions, status, handoff
├─ karpathy on SML.txt           source text that started it (paraphrase, not primary)
├─ LFM 3 1.7B Claude Distill_ModelCARD.txt   the model's card (community distill)
│
├─ llamaCPP\                     llama.cpp b12242 (0.9.0-dev) Windows x64 + Vulkan
│  └─ models\LFM-3-Coder-Claude-Distill.Q5_K_M.gguf   1.16 GiB, 1.73B params
│
├─ research\
│  ├─ SOURCES.md                 annotated evidence: for/against, links, exact numbers
│  ├─ VERDICT.md                 thesis-by-thesis verdict + local replication summary
│  ├─ HARNESSES-AND-STRUCTURED-OUTPUT.md   what OpenCode/Pi/etc. expect from a model
│  └─ QUANTIZATION-AND-STRUCTURED-OUTPUT.md   Q4/Q5/Q6/Q3 evidence, size vs reasoning
│
├─ bench\
│  ├─ README.md                  how the benchmark works, arms, usage
│  ├─ tasks.json                 30 tasks, 6 tiers, gold answers, validators
│  ├─ tools.py                   8 deterministic tools over an in-memory DB
│  ├─ run.py                     runner: json / native / verifier / nudged / deadline
│  ├─ analyze.py                 pass@1 tables, failure modes, CSV
│  ├─ reliability.py             pass@1, pass@k, pass^k, flakiness, Wilson CI
│  ├─ stats.py                   cost per pass, context usage, arm comparisons
│  ├─ regrade.py                 re-grade a JSONL after rule changes (no re-run)
│  ├─ run_server.ps1             llama-server launcher (-np 1, 16K, q8_0, budget)
│  ├─ RESULTS.md                 full write-up of all findings
│  ├─ runs.jsonl                 main sweep (180 runs, temp 0, reps 2)
│  ├─ runs_v1_np-auto.jsonl      first sweep with the wrong slot config (baseline)
│  ├─ runs_nudged.jsonl          explicit-submission arm on C/D/E (30 runs)
│  ├─ runs_thinking.jsonl        reasoning-budget subset (6 runs)
│  ├─ runs_reliability.jsonl     sampled sweep (300 runs, temp 0.7, k=5)
│  └─ results_*.csv              per-run CSVs
│
└─ article\
   └─ draft-v1.md                first-person essay, ~2,650 words, contrarian-but-fair
```

Total collected: **516 unique runs** (180 + 30 + 6 + 300), plus the 180-run config baseline in
`runs_v1_np-auto.jsonl`.

---

## The claim under test

Karpathy's position, from the Dwarkesh interview:

- pre-training does two unrelated things: it stores knowledge and it grows reasoning circuits;
- the stored knowledge may actively hurt, because models over-rely on memorised patterns;
- the goal is a **"cognitive core"** stripped of knowledge;
- that core might fit in **~1B parameters** ("plenty of room at the bottom");
- what makes agents work is **tools and a tight feedback loop**, not parameter count.

The local testable version: *on structured tool tasks, does a 1.7B model's success depend more on the
harness than on the model?*

---

## Experiment specification

| Item | Value |
|---|---|
| Model | `LFM-3-Coder-Claude-Distill.Q5_K_M.gguf` — community distill by Schnuckade of `LiquidAI/LFM3-1.7B` |
| Size | 1.73B params, 1.16 GiB, Q5_K_M |
| Runtime | llama.cpp `b12242` / `0.9.0-dev`, Vulkan backend |
| Machine | Intel Core Ultra 5 235U, Intel Arc iGPU (~18 GB shared), 31.5 GB RAM, Windows |
| Context | `-c 16384 -np 1` (one slot) |
| KV cache | `-ctk q8_0 -ctv q8_0`, `-fa on` |
| Reasoning | `--reasoning-budget 0` main sweep, `512` for the thinking subset |
| Sampling | temp 0 (main) / 0.7 (reliability), top_p 0.95, fixed seeds, max_tokens 384 (1024 thinking) |
| Throughput | pp512 **276.6 tok/s**, tg128 **20.8 tok/s** |

**Benchmark:** 30 tasks, 5 per tier, 8 deterministic tools, in-memory DB, no network/clock/fs.
Grading = exact-match payload + required tool sequence. A0 uses substring matching.

| Tier | Capability | Calls |
|---|---|---|
| A0 | instruction following, no tools | 0 |
| A | one tool call | 1–2 |
| B | two-tool chain | 3–4 |
| C | branch on an intermediate value | 4–6 |
| D | multi-source synthesis with conflicts | 3–10 |
| E | long-horizon planning, persistent constraints | 8–12 |

**Arms:**

| Arm | Tools | Extra |
|---|---|---|
| `json` | described in system prompt, model emits JSON | none |
| `native` | OpenAI-compatible `tools` | none |
| `verifier` | native | up to 3 submit retries with environment error messages |
| `nudged` | native | system prompt: "you MUST call submit_decision" |
| `deadline` | native | budget notices at ≤2 calls; final turn restricted to `submit_decision` |

`submit_decision` validates against DB facts and task constraints — never the gold answer — so retries are
feedback, not answer leakage.

---

## Results

### 1. Interface (temp 0, reps 2, 180 runs)

| arm | A0 | A | B | C | D | E | all |
|---|---|---|---|---|---|---|---|
| json | 60% | 100% | 100% | 0% | 20% | 0% | **47%** |
| native | 60% | 100% | 100% | 80% | 60% | 40% | **73%** |
| verifier | 60% | 100% | 100% | 80% | 40% | 60% | **73%** |

### 2. Reliability (temp 0.7, k=5, 300 runs)

| arm | pass@1 (95% CI) | pass@5 any | pass^5 all | flaky |
|---|---|---|---|---|
| native | 70.0% (62–77) | 80% | 57% | 7/30 |
| **deadline** | **76.0% (69–82)** | 83% | **67%** | 5/30 |

Tier `pass^5`:

| Tier | native | deadline |
|---|---|---|
| A0 | 40% | 40% |
| A | 100% | 100% |
| B | 100% | 100% |
| C | 60% | **100%** |
| D | 20% | **60%** |
| E | 20% | **0%** |

### 3. Intervention effects

- Termination policy: `no_submission` **27 → 0**, `payload_mismatch` **5 → 24**. Failure mode moved from
  "never commits" to "commits to the wrong answer".
- Verifier: fixed E-3 (right record, wrong cost) in both reps; broke D-1 (kept using the older audit).
  Net zero across 30 tasks.
- Thinking (+512 budget): 5/6 → **6/6** on a 6-task subset; fixed the counting task; E-2 used 6 calls
  instead of 10.

### 4. Configuration A/B

| Config | Native pass@1 |
|---|---|
| `-np auto` (4 slots) × `-c 8192` → 2,048 per slot | 73% |
| `-np 1` × `-c 16384` + q8_0 KV | 73% |

No score change, but max observed prompt was **2,207 tokens**, which exceeds the old 2,048 slot — the first
run carried a silent truncation risk. `-np 1` is now the default.

### 5. Notable failures

| Task | Behaviour |
|---|---|
| A0-1 | answered **4** to a 6-line "how many are active" question (answer 3) |
| A0-2 | listed an active project among the paused ones |
| E-1 | 24 tool calls, never submitted, hit step limit |
| E-3 | submitted `r10` (ops) instead of `r5` (data); ignored the team constraint |
| D-2 | 22–25 `compare_records` calls, no submission |

---

## Decisions log

### Research (morning)
1. Treated `karpathy on SML.txt` as a **paraphrase**, found the primary Dwarkesh transcript. — avoids
   quoting a summary as Karpathy.
2. Chose to **validate and confute** rather than pick a side; recorded both in `research/SOURCES.md`.
3. Included the counter-evidence (microtask eligibility gap, sub-2B tool-call reliability) because the
   thesis is strongest as a "yes, but".

### Experiment
4. Built a **deterministic 30-task, 6-tier benchmark** modelled on AgentFloor, with no network/clock/fs.
5. Four arms to isolate variables: **interface** (`json` vs `native`), **feedback** (`verifier`),
   **instruction** (`nudged`), **termination policy** (`deadline`).
6. Grading = exact payload + required tool sequence; validators check DB facts, never the gold answer.
7. Temperature 0 for the capability sweep, **0.7 with seeds and k=5** for reliability, because temp 0 makes
   pass^k meaningless.
8. Config corrected to `-np 1 -c 16384 -ctk/-ctv q8_0 -fa on` after discovering the 4-slot context split.
9. Kept the first sweep (`runs_v1_np-auto.jsonl`) as a config baseline instead of deleting it.
10. Added `deadline` only after observing 27 `no_submission` failures; it was not in the original plan.
11. No base-model control (`LiquidAI/LFM3-1.7B`) yet — deliberate scope cut, listed as open item.

### Article
12. Angle: **"right about systems, wrong about the core"**, not a blanket takedown — the +26 pp result
    confirms thesis #4, so a full contrarian piece would refute itself.
13. Format: first-person essay, ~2,000–2,500 words (draft is ~2,650), English, portable Markdown.
14. Tone: contrarian but fair; concede the interface result in the first 600 words.
15. Full disclosure: community distill, self-authored tasks, one machine, k=5, no base control.
16. Code inline where it earns its place: server flags, termination policy, reproduce block.
17. Research literature limited to **one paragraph** (AgentFloor, NVIDIA position paper, eligibility gap).
18. Data sharing: raw JSONL, `tasks.json`, and `run.py` published at
    https://github.com/fabiomatricardi/smallModels-harness and linked from the article.
19. Title: *How to Get Reliable Agent Work Out of a 1.7B Model (and Where It Still Fails)*.

---

## Reproduce

```powershell
# terminal 1
powershell -NoProfile -ExecutionPolicy Bypass -File .\bench\run_server.ps1 -Port 8080 -Ctx 16384 -Np 1

# terminal 2 (from bench\)
python run.py --arm json,native,verifier --reps 2 --out runs.jsonl
python run.py --arm native,deadline --reps 5 --temperature 0.7 --out runs_reliability.jsonl
python reliability.py runs_reliability.jsonl
python analyze.py runs.jsonl
python stats.py
```

Smoke test: `python run.py --arm native --task A-1 --reps 1 --out smoke.jsonl`

---

## Open items for tomorrow

1. ~~Fill article placeholders~~ **done**: byline, date, and repository links are in `article/draft-v1.md`.
2. **Trim the draft** from ~2,650 to ≤2,500 words if the length target matters; the candidates are the
   TL;DR bullets and the "What I'd do differently" section.
3. **Optional control experiment:** run `LiquidAI/LFM3-1.7B` Q5 (~1.2 GB) on the same 30 tasks. This is the
   single biggest threat to the article's conclusion.
4. **Optional rigor:** paraphrase variants per task (AgentFloor uses four) and higher k.
5. **Optional:** Italian adaptation of the finished article.
6. Optional: add a `LICENSE` (code and text currently unlicensed) and tag a `v1.0` release.

---

## Caveats

- One model, one quant, one machine; 5 tasks per tier is a probe, not a leaderboard.
- The model is a third-party distill with no published benchmarks; results may not transfer to base LFM3.
- A0 grading is substring-based; a correct token inside a longer answer could pass.
- k=5 is a weak tail estimate; CIs are Wilson intervals on pass@1.
- Vendor numbers (Liquid AI's agentic table) are unreplicated and harness-configured by the vendor.

## Key sources

- Karpathy / Dwarkesh, *AGI is still a decade away* — https://www.dwarkesh.com/p/andrej-karpathy
- AgentFloor, arXiv:2605.00334 — https://arxiv.org/abs/2605.00334
- NVIDIA, *Small Language Models are the Future of Agentic AI*, arXiv:2506.02153
- *Measuring the Microtask Eligibility Gap*, arXiv:2610.00025
- LFM3-1.7B model card — https://huggingface.co/LiquidAI/LFM3-1.7B