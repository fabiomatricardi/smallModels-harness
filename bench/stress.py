"""Format stress test: parseability vs argument correctness across quantizations.

200 deterministic prompts covering schema complexity and tool-relevance.
Measures, separately:
  - call rate          : did it emit a tool call when one was required?
  - schema valid       : parsable + required keys + correct types
  - argument accuracy  : values actually correct
  - wrong tool / spurious call

Usage:
  python stress.py --label LFM3-Q6 --out stress_LFM3-Q6.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import random
import time
import urllib.error
import urllib.request
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))

SYSTEM = ("You are a precise tool-calling assistant. Call the provided tool when the request "
          "requires it. Use the exact values from the user's message. Do not explain.")


def tool(name, desc, props, required):
    return {"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": props, "required": required}}}


CITIES = ["Rome", "Paris", "Berlin", "Madrid", "Lisbon", "Vienna", "Prague", "Warsaw",
          "Dublin", "Athens", "Oslo", "Helsinki", "Zurich", "Porto", "Bologna", "Naples"]
LEVELS = ["low", "medium", "high", "critical"]
CURRENCIES = ["EUR", "USD", "GBP", "CHF"]
NAMES = ["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta"]
TITLES = ["standup", "review", "planning", "retro", "demo", "sync", "briefing", "workshop"]
DATES = ["2026-12-01", "2026-12-15", "2027-01-08", "2027-02-20", "2027-03-05"]
TIMES = ["09:00", "10:30", "14:00", "16:45", "18:00"]
PEOPLE = ["ana", "bruno", "carla", "dario", "elena", "farid"]
TAGS = ["urgent", "backend", "frontend", "infra", "docs", "bug", "feature", "ops"]


def build_cases(n=200, seed=42):
    rng = random.Random(seed)
    cases = []

    # 1. simple string argument (40)
    for i in range(40):
        city = rng.choice(CITIES)
        cases.append({
            "id": f"simple-{i+1}", "category": "simple_string",
            "prompt": f"What is the weather in {city} right now?",
            "tools": [tool("get_weather", "Get current weather for a city.",
                           {"city": {"type": "string", "description": "City name"}}, ["city"])],
            "expected": {"name": "get_weather", "args": {"city": city}},
        })

    # 2. enum argument (30)
    for i in range(30):
        lvl = rng.choice(LEVELS)
        cases.append({
            "id": f"enum-{i+1}", "category": "enum_arg",
            "prompt": f"Set the priority of ticket T-{100+i} to {lvl}.",
            "tools": [tool("set_priority", "Set ticket priority.",
                           {"ticket": {"type": "string"},
                            "level": {"type": "string", "enum": LEVELS}}, ["ticket", "level"])],
            "expected": {"name": "set_priority", "args": {"ticket": f"T-{100+i}", "level": lvl}},
        })

    # 3. numeric argument (30)
    for i in range(30):
        amount = rng.choice([12.5, 40, 99.99, 150, 275.4, 1000])
        cur = rng.choice(CURRENCIES)
        cases.append({
            "id": f"numeric-{i+1}", "category": "numeric_arg",
            "prompt": f"Transfer {amount} {cur} to account ACC-{200+i}.",
            "tools": [tool("transfer_funds", "Transfer money.",
                           {"account": {"type": "string"},
                            "amount": {"type": "number"},
                            "currency": {"type": "string", "enum": CURRENCIES}},
                           ["account", "amount", "currency"])],
            "expected": {"name": "transfer_funds",
                         "args": {"account": f"ACC-{200+i}", "amount": amount, "currency": cur}},
        })

    # 4. boolean argument (20)
    for i in range(20):
        flag = rng.choice([True, False])
        name = rng.choice(NAMES)
        cases.append({
            "id": f"bool-{i+1}", "category": "boolean_arg",
            "prompt": f"Turn the {name} feature {'on' if flag else 'off'}.",
            "tools": [tool("toggle_feature", "Enable or disable a feature.",
                           {"name": {"type": "string"}, "enabled": {"type": "boolean"}},
                           ["name", "enabled"])],
            "expected": {"name": "toggle_feature", "args": {"name": name, "enabled": flag}},
        })

    # 5. nested object (30)
    for i in range(30):
        title = rng.choice(TITLES)
        d = rng.choice(DATES)
        t = rng.choice(TIMES)
        who = rng.sample(PEOPLE, 2)
        cases.append({
            "id": f"nested-{i+1}", "category": "nested_object",
            "prompt": (f"Create a calendar event titled '{title}' on {d} at {t}, "
                       f"with attendees {who[0]} and {who[1]}."),
            "tools": [tool("create_event", "Create a calendar event.",
                           {"title": {"type": "string"},
                            "when": {"type": "object", "properties": {
                                "date": {"type": "string"}, "time": {"type": "string"}},
                                "required": ["date", "time"]},
                            "attendees": {"type": "array", "items": {"type": "string"}}},
                           ["title", "when", "attendees"])],
            "expected": {"name": "create_event",
                         "args": {"title": title, "when": {"date": d, "time": t},
                                  "attendees": who}},
        })

    # 6. array argument (20)
    for i in range(20):
        tags = rng.sample(TAGS, 2)
        cases.append({
            "id": f"array-{i+1}", "category": "array_arg",
            "prompt": f"Add the tags {tags[0]} and {tags[1]} to record R-{300+i}.",
            "tools": [tool("add_tags", "Attach tags to a record.",
                           {"record_id": {"type": "string"},
                            "tags": {"type": "array", "items": {"type": "string"}}},
                           ["record_id", "tags"])],
            "expected": {"name": "add_tags",
                         "args": {"record_id": f"R-{300+i}", "tags": tags}},
        })

    # 7. relevance: no call expected (30)
    questions = [
        "What is the capital of France?",
        "How many days are in February 2028?",
        "Explain what a token is in one sentence.",
        "What does HTTP stand for?",
        "Is 17 a prime number?",
        "What is 12 times 12?",
        "Name the largest planet in the solar system.",
        "What language is spoken in Brazil?",
        "How many continents are there?",
        "What is the boiling point of water at sea level in Celsius?",
    ]
    for i in range(30):
        q = questions[i % len(questions)]
        cases.append({
            "id": f"nocall-{i+1}", "category": "no_call",
            "prompt": q,
            "tools": [tool("get_weather", "Get current weather for a city.",
                           {"city": {"type": "string"}}, ["city"])],
            "expected": None,
        })

    return cases[:n]


def post(base, body, timeout=120):
    req = urllib.request.Request(base.rstrip("/") + "/v1/chat/completions",
                                 data=json.dumps(body).encode("utf-8"),
                                 headers={"Content-Type": "application/json"}, method="POST")
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            err = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:200]}"
        except Exception as exc:  # noqa: BLE001
            err = f"{type(exc).__name__}: {exc}"
        time.sleep(1 + attempt)
    raise RuntimeError(err)


def coerce(obj):
    if isinstance(obj, dict):
        return {k: coerce(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [coerce(v) for v in obj]
    return obj


def args_match(expected, actual):
    """Type-aware comparison. Arrays compare as multisets, numbers numerically."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        if set(expected) != set(actual):
            return False
        return all(args_match(expected[k], actual[k]) for k in expected)
    if isinstance(expected, list):
        if not isinstance(actual, list) or len(expected) != len(actual):
            return False
        return sorted(map(str, expected)) == sorted(map(str, actual))
    if isinstance(expected, bool):
        return isinstance(actual, bool) and expected == actual
    if isinstance(expected, (int, float)):
        return isinstance(actual, (int, float)) and not isinstance(actual, bool) \
            and abs(float(expected) - float(actual)) < 1e-6
    return str(expected).strip() == str(actual).strip()


def schema_valid(tools, name, args):
    spec = next((t["function"] for t in tools if t["function"]["name"] == name), None)
    if spec is None or not isinstance(args, dict):
        return False
    params = spec["parameters"]
    if any(k not in args for k in params.get("required", [])):
        return False
    types = {"string": str, "number": (int, float), "boolean": bool,
             "array": list, "object": dict}
    for key, val in args.items():
        prop = params.get("properties", {}).get(key)
        if not prop:
            continue
        py = types.get(prop.get("type"))
        if py and not isinstance(val, py):
            return False
        if prop.get("type") == "number" and isinstance(val, bool):
            return False
        if "enum" in prop and val not in prop["enum"]:
            return False
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    ap.add_argument("--label", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    out_path = args.out or os.path.join(HERE, f"stress_{args.label}.jsonl")

    cases = build_cases()
    if args.limit:
        cases = cases[:args.limit]

    rows = []
    t0 = time.time()
    with open(out_path, "w", encoding="utf-8") as fh:
        for i, case in enumerate(cases, 1):
            body = {
                "messages": [{"role": "system", "content": SYSTEM},
                             {"role": "user", "content": case["prompt"]}],
                "tools": case["tools"], "tool_choice": "auto",
                "temperature": 0, "top_p": 0.95, "max_tokens": 256,
                "seed": 7, "chat_template_kwargs": {"enable_thinking": False},
            }
            try:
                data = post(args.base, body)
                msg = (data.get("choices") or [{}])[0].get("message") or {}
                tcs = msg.get("tool_calls") or []
                call = tcs[0].get("function", {}) if tcs else None
                name = (call or {}).get("name")
                try:
                    args_obj = json.loads((call or {}).get("arguments") or "{}")
                except json.JSONDecodeError:
                    args_obj = None
                err = None
            except Exception as exc:  # noqa: BLE001
                name, args_obj, err = None, None, str(exc)

            exp = case["expected"]
            if exp is None:
                called = name is not None
                ok_name = not called
                schema_ok = not called
                args_ok = not called
                call_ok = not called
            else:
                called = name is not None
                ok_name = name == exp["name"]
                schema_ok = bool(ok_name and schema_valid(case["tools"], name, args_obj))
                args_ok = bool(schema_ok and args_match(exp["args"], args_obj))
                call_ok = args_ok
            rec = {
                "case": case["id"], "category": case["category"], "label": args.label,
                "expected": exp, "name": name, "args": args_obj,
                "called": called, "name_ok": ok_name, "schema_ok": schema_ok,
                "args_ok": args_ok, "ok": call_ok, "error": err,
            }
            rows.append(rec)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if i % 20 == 0:
                print(f"  {i}/{len(cases)}", flush=True)

    # summary
    print(f"\n== {args.label}  ({len(rows)} cases, {time.time()-t0:.0f}s)")
    print("| category | n | call | schema | args | exact |")
    print("|---|---|---|---|---|---|")
    by = defaultdict(list)
    for r in rows:
        by[r["category"]].append(r)
    for cat, rs in by.items():
        n = len(rs)
        p = lambda k: 100 * sum(1 for r in rs if r[k]) / n  # noqa: E731
        print(f"| {cat} | {n} | {p('called'):.0f}% | {p('schema_ok'):.0f}% | "
              f"{p('args_ok'):.0f}% | {p('ok'):.0f}% |")
    n = len(rows)
    p = lambda k: 100 * sum(1 for r in rows if r[k]) / n  # noqa: E731
    print(f"| **all** | {n} | {p('called'):.0f}% | {p('schema_ok'):.0f}% | "
          f"{p('args_ok'):.0f}% | {p('ok'):.0f}% |")
    print("wrote", out_path)


if __name__ == "__main__":
    main()