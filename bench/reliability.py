"""Reliability analysis for a sampled sweep: pass@1, pass@k, pass^k, flakiness.

Usage: python reliability.py runs_reliability.jsonl
"""
import collections
import json
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "runs_reliability.jsonl")
    with open(path, encoding="utf-8") as fh:
        rows = [json.loads(l) for l in fh if l.strip()]

    # last write wins per (arm, task, rep)
    latest = {}
    for r in rows:
        latest[(r["arm"], r["task"], r["rep"])] = r
    rows = list(latest.values())

    arms = sorted({r["arm"] for r in rows})
    tiers = [t for t in ["A0", "A", "B", "C", "D", "E"] if any(r["tier"] == t for r in rows)]

    print(f"file: {os.path.basename(path)}   runs: {len(rows)}   "
          f"temperature: {rows[0].get('temperature', '?')}\n")

    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        by_task = collections.defaultdict(list)
        for r in rs:
            by_task[r["task"]].append(r)
        k = max((len(v) for v in by_task.values()), default=0)
        n_all = sum(len(v) for v in by_task.values())
        s_all = sum(sum(x["ok"] for x in v) for v in by_task.values())
        lo, hi = wilson(s_all, n_all)
        allpass = sum(1 for v in by_task.values() if all(x["ok"] for x in v))
        anypass = sum(1 for v in by_task.values() if any(x["ok"] for x in v))
        flaky = sum(1 for v in by_task.values() if any(x["ok"] for x in v) and not all(x["ok"] for x in v))

        print(f"## {arm}  (k={k}, {len(by_task)} tasks, {n_all} runs)\n")
        print(f"- pass@1: **{100 * s_all / n_all:.1f}%**  (95% CI {100 * lo:.0f}–{100 * hi:.0f}%)")
        print(f"- pass@{k} (any rep): {100 * anypass / len(by_task):.0f}%")
        print(f"- pass^{k} (all reps): **{100 * allpass / len(by_task):.0f}%**")
        print(f"- flaky tasks (some but not all reps pass): {flaky}/{len(by_task)}\n")

        print("| tier | tasks | pass@1 | pass@k | pass^k | flaky |")
        print("|---|---|---|---|---|---|")
        for t in tiers:
            ids = sorted({r["task"] for r in rs if r["tier"] == t})
            if not ids:
                continue
            n = s = 0
            ap = an = fl = 0
            for tid in ids:
                v = by_task[tid]
                ok = sum(x["ok"] for x in v)
                n += len(v)
                s += ok
                ap += ok == len(v)
                an += ok > 0
                fl += 0 < ok < len(v)
            print(f"| {t} | {len(ids)} | {100 * s / n:.0f}% | {100 * an / len(ids):.0f}% | "
                  f"{100 * ap / len(ids):.0f}% | {fl} |")
        print()

    # failure reasons
    print("## failure reasons\n")
    reasons = collections.Counter()
    for r in rows:
        if not r["ok"]:
            reasons[(r["arm"], r["reason"].split("(")[0])] += 1
    for (arm, why), n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"- {arm}: {why} = {n}")


if __name__ == "__main__":
    main()