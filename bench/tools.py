"""Deterministic tool environment for micro-AgentFloor.

No filesystem, no network, no clock: every task is reproducible.
DB inspired by the AgentFloor design (arXiv 2605.00334).
"""
from __future__ import annotations

import ast
import json
import operator
import warnings

RECORDS = [
    {"id": "r1",  "name": "Atlas",    "team": "platform", "status": "active",   "budget": 120, "cost": 45,  "region": "eu", "level": 3},
    {"id": "r2",  "name": "Borealis", "team": "data",     "status": "active",   "budget": 200, "cost": 80,  "region": "us", "level": 2},
    {"id": "r3",  "name": "Cinder",   "team": "platform", "status": "paused",   "budget": 90,  "cost": 30,  "region": "eu", "level": 1},
    {"id": "r4",  "name": "Delta",    "team": "security", "status": "active",   "budget": 150, "cost": 140, "region": "us", "level": 4},
    {"id": "r5",  "name": "Ember",    "team": "data",     "status": "active",   "budget": 60,  "cost": 55,  "region": "ap", "level": 2},
    {"id": "r6",  "name": "Fjord",    "team": "platform", "status": "active",   "budget": 300, "cost": 210, "region": "eu", "level": 5},
    {"id": "r7",  "name": "Gale",     "team": "ops",      "status": "archived", "budget": 40,  "cost": 40,  "region": "us", "level": 1},
    {"id": "r8",  "name": "Harbor",   "team": "security", "status": "active",   "budget": 180, "cost": 150, "region": "us", "level": 3},
    {"id": "r9",  "name": "Iris",     "team": "data",     "status": "paused",   "budget": 75,  "cost": 20,  "region": "ap", "level": 1},
    {"id": "r10", "name": "Juniper",  "team": "ops",      "status": "active",   "budget": 110, "cost": 65,  "region": "eu", "level": 2},
    {"id": "r11", "name": "Kestrel",  "team": "security", "status": "active",   "budget": 220, "cost": 195, "region": "us", "level": 4},
    {"id": "r12", "name": "Lumen",    "team": "platform", "status": "active",   "budget": 95,  "cost": 15,  "region": "ap", "level": 1},
]

AUDITS = [
    {"id": "a1", "target": "r6", "field": "status", "value": "active", "updated": "2026-05-02"},
    {"id": "a2", "target": "r6", "field": "status", "value": "paused", "updated": "2026-08-11"},
    {"id": "a3", "target": "r4", "field": "region", "value": "eu",     "updated": "2026-06-01"},
    {"id": "a4", "target": "r4", "field": "region", "value": "us",     "updated": "2026-07-15"},
    {"id": "a5", "target": "r4", "field": "region", "value": "us",     "updated": "2026-03-20"},
    {"id": "a6", "target": "r7", "field": "status", "value": "active", "updated": "2026-09-01"},
]

DB = {r["id"]: r for r in RECORDS}
DB.update({a["id"]: a for a in AUDITS})

OPS = {
    "==": operator.eq, "!=": operator.ne,
    "<": operator.lt, "<=": operator.le,
    ">": operator.gt, ">=": operator.ge,
}

TOOL_SCHEMAS = [
    {"type": "function", "function": {
        "name": "search_records",
        "description": "Search project records. Returns matching record ids. Every whitespace-separated token must appear in some field.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string", "description": "e.g. 'Ember', 'security active', 'platform'"}
        }, "required": ["query"]}}},
    {"type": "function", "function": {
        "name": "lookup_record",
        "description": "Fetch a full record or audit by exact id (e.g. r1, a2).",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}
        }, "required": ["id"]}}},
    {"type": "function", "function": {
        "name": "get_attribute",
        "description": "Read one field of a record by id.",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "field": {"type": "string"}
        }, "required": ["id", "field"]}}},
    {"type": "function", "function": {
        "name": "list_options",
        "description": "List the distinct values of a record field (team, status, region, level).",
        "parameters": {"type": "object", "properties": {
            "field": {"type": "string"}
        }, "required": ["field"]}}},
    {"type": "function", "function": {
        "name": "check_constraint",
        "description": "Test one field of a record against a comparison, e.g. budget >= 100.",
        "parameters": {"type": "object", "properties": {
            "id": {"type": "string"}, "field": {"type": "string"},
            "op": {"type": "string", "enum": ["==", "!=", "<", "<=", ">", ">="]},
            "value": {"type": ["string", "number"]}
        }, "required": ["id", "field", "op", "value"]}}},
    {"type": "function", "function": {
        "name": "compare_records",
        "description": "Compare one field of two records. Returns both values and which is lower.",
        "parameters": {"type": "object", "properties": {
            "id_a": {"type": "string"}, "id_b": {"type": "string"}, "field": {"type": "string"}
        }, "required": ["id_a", "id_b", "field"]}}},
    {"type": "function", "function": {
        "name": "compute_value",
        "description": "Evaluate a simple arithmetic expression using numbers, + - * / and parentheses.",
        "parameters": {"type": "object", "properties": {
            "expression": {"type": "string", "description": "e.g. '220 - 195'"}
        }, "required": ["expression"]}}},
    {"type": "function", "function": {
        "name": "submit_decision",
        "description": "Submit the final answer payload. Must contain exactly the keys requested by the task.",
        "parameters": {"type": "object", "properties": {
            "payload": {"type": "object", "description": "Final answer object.", "additionalProperties": True}
        }, "required": ["payload"]}}},
]

TOOL_NAMES = [t["function"]["name"] for t in TOOL_SCHEMAS]


def _err(msg: str) -> dict:
    return {"error": msg}


def search_records(query: str = "", **_) -> dict:
    q = str(query).lower().strip()
    if not q:
        return _err("query is empty")
    tokens = q.split()
    hits = []
    for r in RECORDS:
        hay = " ".join(str(v).lower() for v in r.values())
        if all(t in hay for t in tokens):
            hits.append(r["id"])
    if not hits:
        return {"ids": [], "note": "no match; try fewer or different tokens"}
    return {"ids": hits}


def lookup_record(id: str = "", **_) -> dict:
    rec = DB.get(str(id))
    return rec if rec else _err(f"unknown id: {id}")


def get_attribute(id: str = "", field: str = "", **_) -> dict:
    rec = DB.get(str(id))
    if not rec:
        return _err(f"unknown id: {id}")
    if field not in rec:
        return _err(f"record {id} has no field '{field}'; fields: {sorted(rec)}")
    return {"id": id, "field": field, "value": rec[field]}


def list_options(field: str = "", **_) -> dict:
    vals = sorted({r[field] for r in RECORDS if field in r}, key=str)
    if not vals:
        return _err(f"no such field '{field}'; fields: {sorted(RECORDS[0])}")
    return {"field": field, "values": vals}


def check_constraint(id: str = "", field: str = "", op: str = "==", value=None, **_) -> dict:
    rec = DB.get(str(id))
    if not rec:
        return _err(f"unknown id: {id}")
    if field not in rec:
        return _err(f"record {id} has no field '{field}'")
    fn = OPS.get(str(op))
    if not fn:
        return _err(f"unknown op '{op}'")
    actual = rec[field]
    try:
        ok = bool(fn(actual, value))
    except TypeError:
        ok = bool(fn(str(actual), str(value)))
    return {"id": id, "field": field, "actual": actual, "op": op, "value": value, "ok": ok}


def compare_records(id_a: str = "", id_b: str = "", field: str = "", **_) -> dict:
    a, b = DB.get(str(id_a)), DB.get(str(id_b))
    if not a:
        return _err(f"unknown id: {id_a}")
    if not b:
        return _err(f"unknown id: {id_b}")
    if field not in a:
        return _err(f"record {id_a} has no field '{field}'")
    if field not in b:
        return _err(f"record {id_b} has no field '{field}'")
    va, vb = a[field], b[field]
    try:
        lower = id_a if va < vb else (id_b if vb < va else None)
    except TypeError:
        lower = None
    return {"id_a": id_a, "value_a": va, "id_b": id_b, "value_b": vb, "lower": lower}


_ALLOWED = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Constant,
            ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd, ast.Load)


def compute_value(expression: str = "", **_) -> dict:
    expr = str(expression).replace(" ", "")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(expr, mode="eval")
        for node in ast.walk(tree):
            if not isinstance(node, _ALLOWED):
                raise ValueError("only numbers and + - * / ( ) are allowed")
        val = eval(compile(tree, "<expr>", "eval"), {"__builtins__": {}}, {})
        return {"expression": expression, "value": val}
    except Exception as exc:  # noqa: BLE001
        return _err(f"cannot evaluate '{expression}': {exc}")


def submit_decision(task: dict, payload, **_) -> dict:
    """Validate a submission using task constraints and DB facts - never the gold answer."""
    v = task.get("validator") or {}
    if payload is None:
        return {"ok": False, "errors": ["payload missing"]}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return {"ok": False, "errors": ["payload must be a JSON object"]}
    if not isinstance(payload, dict):
        return {"ok": False, "errors": ["payload must be a JSON object"]}

    errors = []
    for key in v.get("required", []):
        if key not in payload:
            errors.append(f"missing key '{key}'")

    rec = None
    rk = v.get("record_key")
    if rk:
        rid = payload.get(rk)
        rec = DB.get(str(rid)) if rid is not None else None
        if rid is None:
            errors.append(f"missing key '{rk}'")
        elif rec is None:
            errors.append(f"unknown id '{rid}'")

    # Numeric/field consistency against the DB (feedback, not the answer).
    if rec:
        for key, val in payload.items():
            if key in rec and key != "id" and key != "name":
                if rec[key] != val:
                    errors.append(f"{key} mismatch: submitted {val!r}, actual {rec[key]!r}")
        for con in v.get("constraints", []):
            actual = rec.get(con["field"])
            fn = OPS.get(con["op"], operator.eq)
            try:
                ok = bool(fn(actual, con["value"]))
            except TypeError:
                ok = bool(fn(str(actual), str(con["value"])))
            if not ok:
                errors.append(f"constraint failed: selected record has {con['field']}={actual!r}, "
                              f"required {con['op']} {con['value']!r}")

    if errors:
        return {"ok": False, "errors": errors}
    return {"ok": True, "accepted": payload}


def execute(task: dict, name: str, args: dict) -> dict:
    args = args or {}
    if name == "search_records":
        return search_records(**args)
    if name == "lookup_record":
        return lookup_record(**args)
    if name == "get_attribute":
        return get_attribute(**args)
    if name == "list_options":
        return list_options(**args)
    if name == "check_constraint":
        return check_constraint(**args)
    if name == "compare_records":
        return compare_records(**args)
    if name == "compute_value":
        return compute_value(**args)
    if name == "submit_decision":
        return submit_decision(task, args.get("payload", args))
    return _err(f"unknown tool '{name}'")


def _norm(s: str) -> str:
    return " ".join(str(s).lower().split())


def _is_subsequence(required, actual) -> bool:
    it = iter(actual)
    return all(any(r == a for a in it) for r in required)


def grade(task: dict, result: dict) -> tuple[bool, str]:
    """result: {payload, final_text, tools_called}."""
    if task["tier"] == "A0":
        text = _norm(result.get("final_text") or "")
        ans = _norm(task["answer"])
        if ans in text:
            return True, "answer_match"
        return False, f"answer_mismatch(expected {task['answer']!r})"

    payload = result.get("payload")
    if payload is None:
        return False, "no_submission"
    if payload != task["gold"]:
        return False, f"payload_mismatch(expected {task['gold']})"
    # The old rule demanded a specific tool sequence, which penalised equally valid paths
    # (e.g. get_attribute twice instead of compare_records). Require only that the model
    # actually read data before answering; the payload itself proves it looked things up.
    if task["tier"] != "A0" and not any(t != "submit_decision" for t in result.get("tools_called", [])):
        return False, "no_tool_use"
    return True, "ok"