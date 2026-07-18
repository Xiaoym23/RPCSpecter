from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import ROOT, get_chain  # noqa: E402

try:
    from .neg_rule_engine import eval_rule
except ImportError:  # pragma: no cover
    from neg_rule_engine import eval_rule


def _assert_root(chain: Optional[str] = None) -> Path:
    root = ROOT / "ConstraintExtraction" / "assertions" / (chain or get_chain()) / "golden"
    root.mkdir(parents=True, exist_ok=True)
    return root


# ---------- External interface ----------
def dynamic_assert(mutant: Dict[str, Any], resp: Dict[str, Any], method: str, chain: Optional[str] = None) -> str:
    """Bidirectional assertion.

    Returns detailed verdicts used by the prototype:
    NEG_PASS / NEG_VIOLATION / GOLDEN_CREATED / GOLDEN_UPDATED / PASS / FAILED.
    """
    chain = chain or get_chain()
    if _is_illegal(mutant, method, chain):
        return _assert_neg(resp)

    shape_hash = _shape_hash(resp)
    golden = _load_golden(method, shape_hash, chain)
    if golden is None:
        _save_golden(method, shape_hash, resp, chain)
        return "GOLDEN_CREATED"

    try:
        _assert_golden(resp, golden)
        return "PASS"
    except AssertionError:
        if _should_update_golden(method, shape_hash, resp, golden, chain):
            _save_golden(method, shape_hash, resp, chain)
            _reset_golden_counters(method, shape_hash, chain)
            return "GOLDEN_UPDATED"
        return "FAILED"


# Negative direction: static invalid-input contract.
def _is_illegal(mutant: Dict[str, Any], method: str, chain: str) -> bool:
    candidates = [
        ROOT / "ConstraintExtraction" / "assertions" / chain / "negative_rules" / method / f"{method}.json",
        ROOT / "ConstraintExtraction" / "assertions" / chain / "negative_rules" / f"{method}.json",
        ROOT / "assertions" / "negative_rules" / method / f"{method}.json",
    ]
    rule_file = next((p for p in candidates if p.exists()), None)
    if rule_file is None:
        return False
    _neg_rules = json.loads(rule_file.read_text(encoding="utf8"))
    rules = _neg_rules.get("rules", {})
    for param_path, param_rules in rules.items():
        value = _deep_get(mutant, param_path, default_from_params=True)
        if eval_rule(value, param_rules, mutant):
            return True
    return False


# Invalid input should be rejected explicitly.
def _assert_neg(resp: Dict[str, Any]) -> str:
    http_status = resp.get("http_status", 200)
    if http_status < 400 and "error" not in resp:
        return "NEG_VIOLATION"
    return "NEG_PASS"


def _shape_hash(obj: Any) -> str:
    skeleton = _shape_skeleton(obj)
    return hashlib.md5(json.dumps(skeleton, sort_keys=True).encode()).hexdigest()[:8]


def _shape_skeleton(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _shape_skeleton(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return {"_array": True, "_len": len(obj), "_item": _shape_skeleton(obj[0]) if obj else "Any"}
    return {"_type": type(obj).__name__, "_null": obj is None}


# ---------- Golden sample I/O ----------
def _golden_path(method: str, shape_hash: str, chain: str) -> Path:
    return _assert_root(chain) / f"{method}_{shape_hash}.json"


def _load_golden(method: str, shape_hash: str, chain: str) -> Optional[Dict[str, Any]]:
    path = _golden_path(method, shape_hash, chain)
    if path.exists():
        return json.loads(path.read_text(encoding="utf8"))
    return None


def _save_golden(method: str, shape_hash: str, resp: Dict[str, Any], chain: str) -> None:
    path = _golden_path(method, shape_hash, chain)
    golden = {
        "shape_hash": shape_hash,
        "sample": resp,
        "upper_bounds": _extract_upper_bounds(resp),
    }
    path.write_text(json.dumps(golden, indent=2, ensure_ascii=False), encoding="utf8")


def _extract_upper_bounds(obj: Any, prefix: str = "") -> Dict[str, float]:
    bounds: Dict[str, float] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            bounds.update(_extract_upper_bounds(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list) and obj:
        bounds.update(_extract_upper_bounds(obj[0], f"{prefix}[0]"))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        bounds[prefix] = float(obj)
    return bounds


# Positive direction: dynamic golden-sample contract.
def _assert_golden(resp: Dict[str, Any], golden: Dict[str, Any]) -> None:
    for path, max_val in golden.get("upper_bounds", {}).items():
        cur = _deep_get(resp, path, default_from_params=False)
        if isinstance(cur, (int, float)) and not isinstance(cur, bool):
            lower = 0
            upper = _adaptive_upper(max_val)
            if not (lower <= cur <= upper):
                raise AssertionError(f"{path}={cur} not in [{lower}, {upper}]")


def _adaptive_upper(base: float) -> float:
    """Return the tolerance upper bound for a volatile numeric field.

    The golden interval is [0, max(1, 1.2 * base)].  The additive floor
    prevents zero-valued fields from creating a degenerate interval.
    """
    return max(1.0, 1.2 * float(base))


def _counter_path(method: str, shape_hash: str, chain: str) -> Path:
    return _assert_root(chain) / f"{method}_{shape_hash}.cnt"


def _reset_golden_counters(method: str, shape_hash: str, chain: str) -> None:
    _counter_path(method, shape_hash, chain).unlink(missing_ok=True)


def _should_update_golden(method: str, shape_hash: str, resp: Dict[str, Any], golden: Dict[str, Any], chain: str) -> bool:
    """Update golden after three consecutive per-field bound exceedances."""
    counter_file = _counter_path(method, shape_hash, chain)
    counters = json.loads(counter_file.read_text(encoding="utf8")) if counter_file.exists() else {}
    new_bounds = _extract_upper_bounds(resp)
    old_bounds = golden.get("upper_bounds", {})
    if not new_bounds or not old_bounds:
        return False

    should_update = False
    for path, cur in new_bounds.items():
        old = float(old_bounds.get(path, cur))
        if cur > _adaptive_upper(old):
            counters[path] = int(counters.get(path, 0)) + 1
            if counters[path] >= 3:
                should_update = True
        else:
            counters.pop(path, None)

    if counters:
        counter_file.write_text(json.dumps(counters, indent=2, ensure_ascii=False), encoding="utf8")
    else:
        counter_file.unlink(missing_ok=True)
    return should_update


def _deep_get(obj: Dict[str, Any], path: str, default_from_params: bool = True) -> Any:
    cur: Any = obj.get("params") if default_from_params and isinstance(obj, dict) and "params" in obj else obj
    for key in path.split(".") if path else []:
        if cur is None:
            return None
        if "[" in key and "]" in key:
            key, idx = key.split("[", 1)
            idx_s = idx[:-1]
            if not idx_s:
                return None
            idx_i = int(idx_s)
            cur = cur.get(key, []) if isinstance(cur, dict) else []
            if not isinstance(cur, list) or len(cur) <= idx_i:
                return None
            cur = cur[idx_i]
        else:
            cur = cur.get(key) if isinstance(cur, dict) else None
    return cur
