"""Micro-AgentFloor runner.

Arms:
  json      - tools described in the system prompt, model must emit JSON actions (prompt emulation)
  native    - OpenAI-compatible tool calling through llama-server
  verifier  - native tools + up to 3 submit attempts with environment error feedback

Usage:
  python run.py --arm json,native,verifier --reps 2 --out runs.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

from tools import TOOL_SCHEMAS, TOOL_NAMES, execute, grade

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS_PATH = os.path.join(HERE, "tasks.json")

SYSTEM_NATIVE = (
    "You are a careful tool-using agent. Use the provided tools to read data; never guess a value "
    "you can look up. When the task asks for a submission, call submit_decision with exactly the "
    "payload shape the task specifies. Reply with at most one tool call per turn."
)

SYSTEM_PLAIN = (
    "You are a precise assistant. Answer the user's question and follow the requested output "
    "format exactly. Do not add explanations unless asked."
)

SYSTEM_JSON = (
    "You are a careful tool-using agent. You cannot call tools directly; instead emit exactly ONE "
    "JSON object per turn and nothing else.\n\n"
    "Available tools:\n{tools}\n\n"
    "Output formats (exactly one JSON object per turn):\n"
    '  {{"tool": "<name>", "args": {{...}}}}\n'
    '  {{"final": "<answer text>"}}   (only for tasks that need no submission)\n'
    '  {{"tool": "submit_decision", "args": {{"payload": {{...}}}}}}\n'
    "Do not write prose outside the JSON object."
)

TOOL_DOC = "\n".join(
    f"- {t['function']['name']}({', '.join(t['function']['parameters'].get('properties', {}))}): "
    f"{t['function']['description']}"
    for t in TOOL_SCHEMAS
)

SUBMIT_SCHEMA = [t for t in TOOL_SCHEMAS if t["function"]["name"] == "submit_decision"]


def post_chat(base, body, timeout=180):
    req = urllib.request.Request(
        base.rstrip("/") + "/v1/chat/completions",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    last = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')[:300]}"
        except Exception as exc:  # noqa: BLE001
            last = f"{type(exc).__name__}: {exc}"
        time.sleep(1.0 + attempt)
    raise RuntimeError(last or "request failed")


def chat(base, messages, tools=None, thinking=False, max_tokens=384, temperature=0.0, seed=None):
    body = {
        "messages": messages,
        "temperature": temperature,
        "top_p": 0.95,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": bool(thinking)},
    }
    if seed is not None:
        body["seed"] = seed
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    data = post_chat(base, body)
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    usage = data.get("usage") or {}
    return msg, usage


def parse_args_field(raw):
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # tolerate trailing commas / single quotes from small models
        cleaned = re.sub(r",\s*([}\]])", r"\1", raw).replace("'", '"')
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return {}


def extract_json_object(text):
    """Return the first parseable JSON object found in text."""
    if not text:
        return None
    candidates = []
    for block in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.S):
        candidates.append(block.strip())
    candidates.append(text.strip())
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start:i + 1])
                    break
        start = text.find("{", start + 1)

    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    return None


XML_CALL = re.compile(r"<tool_call>\s*<function=([^>\s]+)>(.*?)</function>\s*</tool_call>", re.S)
XML_PARAM = re.compile(r"<parameter=([^>\s]+)>\s*(.*?)\s*</parameter>", re.S)


def parse_xml_tool_calls(text):
    """Fallback for templates that emit LFM3 XML but are not parsed by the server."""
    out = []
    for i, (name, body) in enumerate(XML_CALL.findall(text or "")):
        args = {}
        for key, val in XML_PARAM.findall(body):
            val = val.strip()
            if val in ("true", "false"):
                args[key] = val == "true"
            else:
                try:
                    args[key] = json.loads(val)
                except json.JSONDecodeError:
                    args[key] = val
        out.append({"id": f"xml_{i}", "type": "function",
                    "function": {"name": name.strip(), "arguments": json.dumps(args)}})
    return out


def run_task(task, arm, rep, base, thinking=False, max_tokens=384, temperature=0.0):
    started = time.time()
    no_tools = task["tier"] == "A0"
    native_like = arm in ("native", "verifier", "nudged", "deadline")
    tools = TOOL_SCHEMAS if (native_like and not no_tools) else None
    if no_tools:
        system = SYSTEM_PLAIN
    elif tools:
        system = SYSTEM_NATIVE
        if arm == "nudged":
            system += (" You MUST end every completed task by calling submit_decision; "
                       "never answer in prose instead of submitting.")
        if arm == "deadline":
            system += (f" You have a hard budget of {task['max_steps']} tool calls. "
                       "Submit before the budget runs out.")
    else:
        system = SYSTEM_JSON.format(tools=TOOL_DOC)
    messages = [{"role": "system", "content": system},
                {"role": "user", "content": task["prompt"]}]
    base_seed = (sum(ord(c) for c in task["id"]) * 1009 + rep * 97
                 + (5000 if arm == "deadline" else 0) + int(temperature * 100) * 13)

    called, payload, final_text = [], None, ""
    attempts = 0
    error = None
    prompt_tokens = completion_tokens = 0
    max_prompt = 0

    for step in range(task["max_steps"]):
        remaining = task["max_steps"] - step
        step_tools = tools
        if arm == "deadline" and tools:
            if step > 0 and remaining <= 2:
                messages.append({"role": "user", "content":
                                 f"BUDGET NOTICE: {remaining} tool call(s) left. "
                                 "Call submit_decision now with your best supported answer."})
            if remaining <= 1:
                step_tools = SUBMIT_SCHEMA
        try:
            msg, usage = chat(base, messages, tools=step_tools, thinking=thinking,
                              max_tokens=max_tokens, temperature=temperature,
                              seed=base_seed + step)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
            break
        prompt_tokens += usage.get("prompt_tokens", 0) or 0
        completion_tokens += usage.get("completion_tokens", 0) or 0
        max_prompt = max(max_prompt, usage.get("prompt_tokens", 0) or 0)

        content = msg.get("content") or ""
        if no_tools:
            final_text = content
            break
        tcs = msg.get("tool_calls") or []
        if not tcs:
            tcs = parse_xml_tool_calls(content)

        if tools and not tcs:
            final_text = content
            if task["tier"] == "A0":
                break
            # model answered in prose without submitting: give it one nudge
            if step == 0:
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": "Continue using tools. If you are done, call submit_decision."})
                continue
            break

        if tools:
            messages.append({"role": "assistant", "content": content, "tool_calls": tcs})
            for tc in tcs:
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                args = parse_args_field(fn.get("arguments"))
                result = execute(task, name, args)
                called.append(name)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id") or f"call_{step}",
                    "content": json.dumps(result),
                })
                if name == "submit_decision":
                    attempts += 1
                    if result.get("ok"):
                        payload = args.get("payload", args)
                    elif arm == "verifier" and attempts < 3:
                        messages.append({"role": "user",
                                         "content": "Your submission was rejected. Fix the errors and submit again."})
                    else:
                        payload = args.get("payload", args)
        else:
            action = extract_json_object(content)
            messages.append({"role": "assistant", "content": content})
            if action is None:
                final_text = content
                break
            if "final" in action:
                final_text = str(action["final"])
                break
            name = action.get("tool") or action.get("name") or ""
            args = action.get("args") or action.get("arguments") or {}
            result = execute(task, name, args)
            called.append(name)
            messages.append({"role": "user", "content": "TOOL_RESULT " + json.dumps(result)})
            if name == "submit_decision":
                attempts += 1
                if result.get("ok"):
                    payload = args.get("payload", args)
                elif arm == "verifier" and attempts < 3:
                    messages.append({"role": "user",
                                     "content": "Your submission was rejected. Fix the errors and submit again."})
                else:
                    payload = args.get("payload", args)

        if payload is not None:
            break

    result = {"payload": payload, "final_text": final_text, "tools_called": called}
    ok, reason = grade(task, result)
    return {
        "task": task["id"], "tier": task["tier"], "arm": arm, "rep": rep,
        "thinking": thinking, "temperature": temperature, "ok": ok, "reason": reason,
        "payload": payload, "tools_called": called,
        "steps": len(called), "attempts": attempts,
        "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
        "max_prompt_tokens": max_prompt,
        "wall_s": round(time.time() - started, 2),
        "error": error,
        "final_text": (final_text or "")[:600],
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8080")
    ap.add_argument("--arm", default="json,native,verifier")
    ap.add_argument("--reps", type=int, default=0)
    ap.add_argument("--tier", default="", help="comma list, e.g. A,B or A0")
    ap.add_argument("--task", default="", help="comma list of task ids")
    ap.add_argument("--thinking", action="store_true")
    ap.add_argument("--temperature", type=float, default=0.0)
    ap.add_argument("--max-tokens", type=int, default=0,
                    help="per-turn output cap; default 384, or 1024 with --thinking")
    ap.add_argument("--out", default=os.path.join(HERE, "runs.jsonl"))
    args = ap.parse_args()

    with open(TASKS_PATH, encoding="utf-8") as fh:
        spec = json.load(fh)
    tasks = spec["tasks"]
    reps = args.reps or spec["meta"].get("reps_default", 2)

    if args.tier:
        want = {t.strip() for t in args.tier.split(",")}
        tasks = [t for t in tasks if t["tier"] in want]
    if args.task:
        want = {t.strip() for t in args.task.split(",")}
        tasks = [t for t in tasks if t["id"] in want]

    arms = [a.strip() for a in args.arm.split(",") if a.strip()]
    mt = args.max_tokens or (1024 if args.thinking else 384)
    total = len(tasks) * len(arms) * reps
    print(f"{len(tasks)} tasks x {len(arms)} arms x {reps} reps = {total} runs", flush=True)

    done = 0
    with open(args.out, "a", encoding="utf-8") as out:
        for arm in arms:
            for task in tasks:
                for rep in range(1, reps + 1):
                    rec = run_task(task, arm, rep, args.base, args.thinking, mt, args.temperature)
                    rec["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    out.flush()
                    done += 1
                    flag = "PASS" if rec["ok"] else "fail"
                    print(f"[{done}/{total}] {arm:8s} {task['id']:5s} rep{rep} {flag} "
                          f"{rec['steps']}calls {rec['wall_s']}s {rec['reason']}", flush=True)
    print("done ->", args.out)


if __name__ == "__main__":
    sys.exit(main())