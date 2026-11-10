# Analyze runs.jsonl into a markdown table + CSV.
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))


def load(path):
    rows = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "runs.jsonl")
    rows = load(path)
    if not rows:
        print("no runs")
        return

    # dedupe: keep last record per (arm, task, rep, thinking)
    latest = {}
    for r in rows:
        latest[(r["arm"], r["task"], r["rep"], r.get("thinking", False))] = r
    rows = list(latest.values())

    cells = defaultdict(list)
    for r in rows:
        cells[(r["arm"], r["tier"])].append(r)

    arms = sorted({r["arm"] for r in rows})
    tiers = ["A0", "A", "B", "C", "D", "E"]
    tiers = [t for t in tiers if any(r["tier"] == t for r in rows)]

    print("\n## pass@1 by arm x tier\n")
    header = "| arm | " + " | ".join(tiers) + " | all |"
    print(header)
    print("|" + "---|" * (len(tiers) + 2))
    for arm in arms:
        vals, allr = [], []
        for t in tiers:
            rs = cells[(arm, t)]
            allr += rs
            vals.append(f"{(sum(r['ok'] for r in rs) / len(rs) * 100):.0f}%" if rs else "-")
        overall = f"{(sum(r['ok'] for r in allr) / len(allr) * 100):.0f}%" if allr else "-"
        print(f"| {arm} | " + " | ".join(vals) + f" | {overall} |")

    print("\n## reliability under sampling\n")
    print("| arm | runs | pass@1 | pass@k (any rep) | pass^k (all reps) | avg calls | avg wall | tok/s |")
    print("|---|---|---|---|---|---|---|---|")
    for arm in arms:
        rs = [r for r in rows if r["arm"] == arm]
        by_task = defaultdict(list)
        for r in rs:
            by_task[r["task"]].append(r)
        any_ok = sum(1 for v in by_task.values() if any(x["ok"] for x in v))
        all_ok = sum(1 for v in by_task.values() if all(x["ok"] for x in v))
        p_any = any_ok / len(by_task) * 100 if by_task else 0
        p_all = all_ok / len(by_task) * 100 if by_task else 0
        p1 = sum(r["ok"] for r in rs) / len(rs) * 100 if rs else 0
        calls = sum(r["steps"] for r in rs) / len(rs) if rs else 0
        wall = sum(r["wall_s"] for r in rs) / len(rs) if rs else 0
        gen = sum(r["completion_tokens"] for r in rs)
        secs = sum(r["wall_s"] for r in rs) or 1
        k = max(len(v) for v in by_task.values()) if by_task else 0
        print(f"| {arm} | {len(rs)} | {p1:.0f}% | {p_any:.0f}% | {p_all:.0f}% | "
              f"{calls:.1f} | {wall:.1f}s | {gen/secs:.1f} |")

    print("\n## failure reasons\n")
    reasons = defaultdict(int)
    for r in rows:
        if not r["ok"]:
            reasons[(r["arm"], r["reason"].split("(")[0])] += 1
    for (arm, why), n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"- {arm}: {why} = {n}")

    stem = os.path.splitext(os.path.basename(path))[0]
    csv = os.path.join(HERE, f"results_{stem}.csv")
    with open(csv, "w", encoding="utf-8") as fh:
        fh.write("arm,tier,task,rep,thinking,ok,reason,steps,attempts,wall_s,prompt_tokens,completion_tokens\n")
        for r in rows:
            fh.write(",".join(str(r.get(k, "")) for k in
                              ["arm", "tier", "task", "rep", "thinking", "ok", "reason",
                               "steps", "attempts", "wall_s", "prompt_tokens", "completion_tokens"]) + "\n")
    print("\nwrote", csv)


if __name__ == "__main__":
    main()