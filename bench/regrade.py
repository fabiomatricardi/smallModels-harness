"""Re-grade an existing runs JSONL with the current tasks.json rules.

Payloads and tool traces are stored, so grading changes never require a re-run.
Usage: python regrade.py runs.jsonl
"""
import json
import os
import sys

from tools import grade

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "runs.jsonl")
    with open(os.path.join(HERE, "tasks.json"), encoding="utf-8") as fh:
        tasks = {t["id"]: t for t in json.load(fh)["tasks"]}

    rows, changed = [], 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            r = json.loads(line)
            ok, reason = grade(tasks[r["task"]], {
                "payload": r.get("payload"),
                "final_text": r.get("final_text", ""),
                "tools_called": r.get("tools_called", []),
            })
            if ok != r["ok"] or reason != r["reason"]:
                changed += 1
                print(f"regraded {r['arm']:8s} {r['task']:5s} rep{r['rep']}: "
                      f"{r['ok']}/{r['reason']} -> {ok}/{reason}")
            r["ok"], r["reason"] = ok, reason
            rows.append(r)

    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"{changed} records changed, {len(rows)} total")


if __name__ == "__main__":
    main()