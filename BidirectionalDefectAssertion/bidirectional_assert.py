import json, os, hashlib, math
from pathlib import Path
from typing import Any, Dict, Optional
from neg_rule_engine import eval_rule

ASSERT_ROOT = Path("assertions/golden")          
ASSERT_ROOT.mkdir(parents=True, exist_ok=True)

ILLEGAL_EXAMPLES = {
    "getMultipleAccounts": {
        "array": ["InvalidBase58!!!"],
        "object.minContextSlot": -1,
        "object.encoding": ["invalid_encoding","base64"],
        "object.preflightCommitment": "unknown_commitment",

    }
}

# ---------- External interface ----------
def dynamic_assert(mutant: Dict[str, Any], resp: Dict[str, Any], method: str) -> str:
    """return: NEG_PASS / GOLDEN_CREATED / PASS / FAILED / GOLDEN_UPDATED"""
    # Negative Contract
    if _is_illegal(mutant, method):
        return _assert_neg(resp, method)

    # Positive Contract
    shape_hash = _shape_hash(resp)
    golden = _load_golden(method, shape_hash)
    if golden is None:
        _save_golden(method, shape_hash, resp)
        return "GOLDEN_CREATED"

    # Difference Calculation
    try:
        _assert_golden(resp, golden)
        return "PASS"
    except AssertionError:
        if _should_update_golden(method, shape_hash, resp, golden):
            _save_golden(method, shape_hash, resp)   # Extend range
            return "GOLDEN_UPDATED"
        return "FAILED"

# Use negative_rules
def _is_illegal(mutant: Dict[str, Any], method: str) -> bool:
    NEG_RULE_FILE = Path(f"assertions/negative_rules/{method}/{method}.json")   # Read by method name
    _neg_rules = json.load(NEG_RULE_FILE.open()) if NEG_RULE_FILE.exists() else {}
    rules = _neg_rules.get('rules', {})
    for param_path, param_rules in rules.items():
        value = _deep_get(mutant, param_path)  
        if eval_rule(value, param_rules, mutant):
            return True
    return False

def _flatten(obj: dict, prefix: str = "") -> dict[str, Any]:
    """{a: {b: 1}} → {"a.b": 1}"""
    out = {}
    for k, v in obj.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, path))
        else:
            out[path] = v
    return out

# Invalid input but still returns a result
def _assert_neg(resp: Dict[str, Any], method: str) -> str:
    http_status = resp.get("http_status", 200)
    if http_status < 400 and "error" not in resp:
        return "NEG_VIOLATION"
    err = resp.get("error", {})
    return "NEG_PASS"

def _shape_hash(obj: Any) -> str:
    if isinstance(obj, dict):
        skeleton = {k: {"type": type(v).__name__, "array": isinstance(v, list), "null": v is None}
                    for k, v in obj.items()}
    elif isinstance(obj, list):
        skeleton = {"_array": True, "_len": len(obj), "_type": type(obj[0]).__name__ if obj else "Any"}
    else:
        skeleton = {"_type": type(obj).__name__}
    return hashlib.md5(json.dumps(skeleton, sort_keys=True).encode()).hexdigest()[:8]

# ---------- Golden sample I/O ----------
def _golden_path(method: str, shape_hash: str) -> Path:
    return ASSERT_ROOT / f"{method}_{shape_hash}.json"

def _load_golden(method: str, shape_hash: str) -> Optional[Dict[str, Any]]:
    path = _golden_path(method, shape_hash)
    if path.exists():
        return json.load(path.open())
    return None

def _save_golden(method: str, shape_hash: str, resp: Dict[str, Any]):
    path = _golden_path(method, shape_hash)
    # Only the skeleton is stored, 
    # plus the upper limit of the values, for range validation.
    golden = {
        "shape_hash": shape_hash,
        "upper_bounds": _extract_upper_bounds(resp)
    }
    json.dump(golden, path.open("w"), indent=2)

def _extract_upper_bounds(obj: Any, prefix: str = "") -> Dict[str, float]:
    bounds = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            bounds.update(_extract_upper_bounds(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list) and obj:
        bounds.update(_extract_upper_bounds(obj[0], f"{prefix}[0]"))
    elif isinstance(obj, (int, float)):
        bounds[prefix] = obj   
    return bounds

# ---------- Golden differ ----------
def _assert_golden(resp: Dict[str, Any], golden: Dict[str, Any]):
    ub = golden["upper_bounds"]
    for path, max_val in ub.items():
        cur = _deep_get(resp, path)
        if isinstance(cur, (int, float)):
            if cur < 0:
                continue
            lower = 0
            upper = max_val * 1.2
            if not (lower <= cur <= upper):
                raise AssertionError(f"{path}={cur} not in [{lower}, {upper}]")

def _should_update_golden(method: str, shape_hash: str, resp: Dict[str, Any], golden: Dict[str, Any]) -> bool:
    counter_file = ASSERT_ROOT / f"{method}_{shape_hash}.cnt"
    cnt = int(counter_file.read_text()) if counter_file.exists() else 0
    new_max = max(_extract_upper_bounds(resp).values())
    old_max = max(golden["upper_bounds"].values())
    if new_max > old_max:
        cnt += 1
        counter_file.write_text(str(cnt))
        return cnt >= 3
    else:
        counter_file.unlink(missing_ok=True)
        return False

def _deep_get(obj: Dict[str, Any], path: str) -> Any:
    obj = obj.get('params')
    for key in path.split("."):
        if "[" in key and "]" in key:        # list[0]
            key, idx = key.split("[", 1)
            if (idx[:-1] == ''):
                return None
            idx = int(idx[:-1])
            obj = obj.get(key, [{}])         
            if len(obj) <= idx:
                return None
            obj = obj[idx]
        else:
            if obj is None:
                return None
            else:
                obj = obj.get(key)               
        if obj is None:
            return None
    return obj