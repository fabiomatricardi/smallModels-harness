"""Summary stats for the report."""
import collections
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


main = load("runs.jsonl")
nud = load("runs_nudged.jsonl")
th = load("runs_thinking.jsonl")

print("=== per-arm cost (30 tasks, reps=2) ===")
for arm in ["json", "native", "verifier"]:
    rs = [r for r in main if r["arm"] == arm]
    wall = sum(r["wall_s"] for r in rs)
    passes = sum(r["ok"] for r in rs)
    gen = sum(r["completion_tokens"] for r in rs)
    usd = (wall / 3600 * 0.5) / max(passes, 1)
    print(f"{arm:8s} runs={len(rs):3d} passes={passes:2d} wall={wall/60:5.1f}min "
          f"gen_tok={gen:6d} $/pass@0.5usd/h={usd:.5f} tok/s={gen/wall:4.1f} "
          f"max_ctx={max(r['max_prompt_tokens'] for r in rs)}")

print("\n=== nudged vs native on C/D/E ===")
for arm, src in [("native", main), ("verifier", main), ("nudged", nud)]:
    rs = [r for r in src if r["arm"] == arm and r["tier"] in ("C", "D", "E")]
    by = collections.defaultdict(lambda: [0, 0])
    for r in rs:
        by[r["tier"]][0] += r["ok"]
        by[r["tier"]][1] += 1
    cells = " ".join(f"{t}:{100 * v[0] // v[1]}%" for t, v in sorted(by.items()))
    print(f"{arm:8s} {cells}  overall={100 * sum(r['ok'] for r in rs) // len(rs)}%")

print("\n=== thinking subset (6 tasks, 1 rep) ===")
for r in th:
    print(f"{r['task']:5s} ok={str(r['ok']):5s} calls={r['steps']:2d} "
          f"wall={r['wall_s']:6.1f}s gen_tok={r['completion_tokens']:4d} "
          f"max_ctx={r['max_prompt_tokens']}")

print("\n=== context usage ===")
v1 = load("runs_v1_np-auto.jsonl")
print("v1 max_prompt_tokens:", max(r.get("max_prompt_tokens", 0) for r in v1), "(2048-token slots, not instrumented)")
print("v2 max_prompt_tokens:", max(r["max_prompt_tokens"] for r in main), "(16384-token slot)")

print("\n=== same 6 tasks, thinking OFF (from main run) ===")
for r in main:
    if r["arm"] == "native" and r["task"] in {"A0-1", "A-2", "B-3", "C-1", "D-1", "E-2"} and r["rep"] == 1:
        print(f"{r['task']:5s} ok={str(r['ok']):5s} calls={r['steps']:2d} wall={r['wall_s']:6.1f}s")