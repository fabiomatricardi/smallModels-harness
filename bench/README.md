# micro-AgentFloor bench

A deterministic, local 30-task agent benchmark derived from AgentFloor (arXiv 2605.00334),
used to test the claim that *harness + tools* matters more than model size.

## Layout

| File | Purpose |
|---|---|
| `tasks.json` | 30 tasks, 6 tiers (A0/A/B/C/D/E), gold answers, required tool sequences, validators |
| `tools.py` | 8 deterministic tools over an in-memory DB (no filesystem, no network, no clock) |
| `run.py` | Runner: 3 arms (`json`, `native`, `verifier`) x N reps, writes JSONL |
| `analyze.py` | pass@1, pass^N, failure modes, CSV |
| `regrade.py` | re-grade an existing JSONL after grading-rule changes (no re-run needed) |
| `stats.py` | cost per passed task, context usage, arm comparisons |
| `reliability.py` | sampled sweep: pass@1, pass@k, pass^k, flakiness, Wilson CI |
| `run_server.ps1` | Launches llama-server (Vulkan, 127.0.0.1:8080) |
| `runs.jsonl` | Raw run log |
| `RESULTS.md` | Findings |

## Tiers

- **A0** — no tools, instruction following + format compliance
- **A** — one tool call
- **B** — two-tool chain (search → lookup → submit)
- **C** — branch on an intermediate value
- **D** — multi-source synthesis with conflicts (audits, majority, recency)
- **E** — long-horizon planning under persistent constraints (8–12 calls)

## Arms (the actual experiment)

| Arm | Tool interface | Retry on rejected submit |
|---|---|---|
| `json` | tools described in the system prompt; model emits JSON actions | no |
| `native` | OpenAI-compatible `tools` via llama-server | no |
| `verifier` | same as `native` | up to 3, with environment error messages |
| `nudged` | same as `native` + "you MUST call submit_decision" | no |
| `deadline` | budget-aware: notices when ≤2 calls remain, final turn restricted to `submit_decision` | no |

`submit_decision` validates the payload against DB facts and task constraints — **never against
the gold answer** — so retries are legitimate feedback, not answer leakage.

## Usage

```powershell
# terminal 1
powershell -NoProfile -ExecutionPolicy Bypass -File .\run_server.ps1 -Port 8080 -Ctx 16384 -Np 1

# terminal 2
python run.py --arm json,native,verifier --reps 2 --out runs.jsonl
python run.py --arm native,deadline --reps 5 --temperature 0.7 --out runs_reliability.jsonl
python run.py --arm native,verifier --tier A,B,C --thinking --reps 1 --out runs_thinking.jsonl
python analyze.py runs.jsonl
python reliability.py runs_reliability.jsonl
```

Smoke test:

```powershell
python run.py --arm native --task A-1 --reps 1 --out smoke.jsonl
```

## Known limits

- 30 tasks is a capability probe, not a leaderboard. Per-tier cells are 5 tasks.
- Grading is exact-match on the submitted payload; A0 uses substring matching.
- One model, one quant (Q5_K_M), one machine (Intel Arc iGPU).
- `reps=2` gives a weak pass^2/pass^3 signal; treat reliability numbers as indicative.