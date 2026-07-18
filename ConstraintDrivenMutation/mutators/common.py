"""Shared utilities for RPCSpecter's constraint-aware mutators."""
from __future__ import annotations

import base64
import builtins
import hashlib
import importlib
import json
import os
import random
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

import requests

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SAFE_BUILTINS = {
    "__import__": builtins.__import__,
    "len": builtins.len,
    "bytes": builtins.bytes,
    "tuple": builtins.tuple,
    "int": builtins.int,
    "float": builtins.float,
    "str": builtins.str,
    "bool": builtins.bool,
    "list": builtins.list,
    "dict": builtins.dict,
    "set": builtins.set,
    "any": builtins.any,
    "all": builtins.all,
    "range": builtins.range,
    "isinstance": builtins.isinstance,
    "type": builtins.type,
    "hasattr": builtins.hasattr,
    "getattr": builtins.getattr,
    "setattr": builtins.setattr,
    "min": builtins.min,
    "max": builtins.max,
    "sum": builtins.sum,
    "abs": builtins.abs,
}


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf8"))


def load_tools(chain: str, method: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load generated seed-support tools and keep only tools for ``method``.

    New artifacts are written to ``ConstraintExtraction/tools/{chain}/tools.json``.
    Older prototypes used ``tools/{chain}/tools.json`` and did not always include
    a method field, so method-less tools are kept for backward compatibility.
    """
    candidates = [
        ROOT / "ConstraintExtraction" / "tools" / chain / "tools.json",
        ROOT / "tools" / chain / "tools.json",
        ROOT / "tools" / "ethereum" / "tools.json",
        Path(f"ConstraintExtraction/tools/{chain}/tools.json"),
        Path(f"tools/{chain}/tools.json"),
    ]
    for file in candidates:
        if not file.exists():
            continue
        data = _read_json(file)
        tools = data.get("tools", []) if isinstance(data, dict) else []
        if method:
            tools = [t for t in tools if not t.get("method") or t.get("method") == method]
        return tools
    return []


def load_constraint_pool(chain: str) -> Dict[str, Any]:
    candidates = [
        ROOT / "constraints_pool" / chain / "by_constraint.json",
        ROOT / "osc_spc" / chain / "by_constraint.json",
        ROOT / "osc_spc" / "ethereum" / "by_constraint.json",
        Path(f"constraints_pool/{chain}/by_constraint.json"),
        Path(f"osc_spc/{chain}/by_constraint.json"),
    ]
    for file in candidates:
        if file.exists():
            return _read_json(file)
    return {}


def constraint_kind(tool: Dict[str, Any]) -> str:
    kind = str(tool.get("constraint", "")).upper()
    # Legacy names used by the prototype.
    if kind == "SPC":
        return "PDC"
    if kind in {"EPC", "PTC", "BTC"}:
        return "STC"
    return kind


def _split_path(path: str) -> List[tuple[str, Optional[int]]]:
    parts: List[tuple[str, Optional[int]]] = []
    for raw in path.split(".") if path else []:
        m = re.fullmatch(r"([^\[]+)(?:\[(\d+)\])?", raw)
        if not m:
            parts.append((raw, None))
        else:
            parts.append((m.group(1), int(m.group(2)) if m.group(2) is not None else None))
    return parts


def path_exists(obj: Any, path: str) -> bool:
    sentinel = object()
    return deep_get(obj, path, sentinel) is not sentinel


def deep_get(obj: Any, path: str, default: Any = None) -> Any:
    cur = obj
    for key, idx in _split_path(path):
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return default
        if idx is not None:
            if not isinstance(cur, list) or idx >= len(cur):
                return default
            cur = cur[idx]
    return cur


def assign_payload(payload: Dict[str, Any], path: str, value: Any) -> None:
    """Assign ``value`` to a dotted path; supports simple ``field[0]`` segments."""
    if not path:
        return
    parts = _split_path(path)
    cur: Any = payload
    for i, (key, idx) in enumerate(parts[:-1]):
        next_key, next_idx = parts[i + 1]
        if not isinstance(cur, dict):
            return
        if key not in cur or cur[key] is None:
            cur[key] = [] if idx is not None else ({} if next_idx is None else {next_key: []})
        elif idx is not None and not isinstance(cur[key], list):
            cur[key] = []
        cur = cur[key]
        if idx is not None:
            while len(cur) <= idx:
                cur.append({})
            cur = cur[idx]
    last_key, last_idx = parts[-1]
    if not isinstance(cur, dict):
        return
    if last_idx is None:
        cur[last_key] = value
    else:
        arr = cur.setdefault(last_key, [])
        if not isinstance(arr, list):
            arr = []
            cur[last_key] = arr
        while len(arr) <= last_idx:
            arr.append(None)
        arr[last_idx] = value


def empty_value(typ: str) -> Any:
    typ = (typ or "").lower()
    if "array" in typ or "[]" in typ or typ == "list":
        return []
    if typ in {"object", "dict", "map"}:
        return {}
    if typ in {"int", "integer", "u64", "u32", "number"}:
        return 0
    if typ in {"float", "double"}:
        return 0.0
    if typ in {"string", "str", "pubkey", "hash", ""}:
        return ""
    if typ in {"boolean", "bool"}:
        return False
    return None


def fallback_value(chain: str, kind: str, path: str) -> Any:
    pool = load_constraint_pool(chain)
    items: Iterable[Dict[str, Any]] = pool.get(kind, [])
    if kind == "PDC":
        items = list(items) + list(pool.get("SPC", []))
    if kind == "STC":
        items = list(items) + list(pool.get("EPC", [])) + list(pool.get("PTC", [])) + list(pool.get("BTC", []))
    for item in items:
        if item.get("path") == path:
            return empty_value(item.get("type", ""))
    return None


def extract_func_name(code: str) -> Optional[str]:
    match = re.search(r"def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(", code or "")
    return match.group(1) if match else None


def exec_generated_func(code: str, imports: Optional[List[str]] = None, arg: Any = None, pass_arg: bool = False) -> Any:
    """Execute one generated helper in a restricted namespace.

    ``pass_arg`` is used for procedural chains where a step intentionally
    consumes the previous stage, even when that previous value is ``None``.
    """
    if not code:
        return None
    loc: Dict[str, Any] = {}
    clean_globals: Dict[str, Any] = {
        "__builtins__": SAFE_BUILTINS,
        "requests": requests,
        "os": os,
        "json": json,
        "base64": base64,
        "hashlib": hashlib,
        "random": random,
    }
    for imp in imports or []:
        try:
            module = importlib.import_module(imp)
            clean_globals[imp.split(".")[0]] = module
        except Exception:
            # Generated helpers are best-effort; missing optional blockchain SDKs
            # should not break the whole fuzzing campaign.
            continue
    try:
        exec(code, clean_globals, loc)
        func_name = extract_func_name(code)
        if not func_name or func_name not in loc:
            return None
        return loc[func_name](arg) if pass_arg else loc[func_name]()
    except TypeError:
        # Be permissive with generated helpers whose signatures are imperfect.
        try:
            func_name = extract_func_name(code)
            return loc[func_name]() if pass_arg and func_name in loc else None
        except Exception:
            return None
    except Exception:
        return None
