#!/usr/bin/env python3
import importlib.util
import json
from pathlib import Path
from typing import Any, Optional, List, Dict
from copy import deepcopy

from mutators.osc_mutator_new import OSCMutator
from mutators.spc_mutator import TransactionSPC
from mutators.epc_mutator import EncodingEPC
from mutators.btc_mutator import BasicTypeBTC

def generate_base_skeleton(method: str) -> Dict[str, Any]:
    """read constraints/solana/{method}/{method}.json"""
    # spec_file = Path(f"constraints/solana/{method}/{method}.json")
    spec_file = Path(f"constraints/ethereum/{method}/{method}.json")
    if not spec_file.exists():
        return {}  

    data = json.loads(spec_file.read_text())
    skeleton = {}
    for param in data.get("params", []):
        _assign_empty(skeleton, param["name"], param["type"], param.get("sub_parameters", []))
    return skeleton

def _assign_empty(obj: dict, name: str, typ: str, sub: List[dict]):
    if not sub:                       # leaf node
        obj[name] = _empty_value(typ)
        return
    # sub params
    child = {}
    for sub_param in sub:
        _assign_empty(child, sub_param["name"], sub_param["type"], sub_param.get("sub_parameters", []))
    obj[name] = child

def _empty_value(typ: str) -> Any:
    if "array" in typ or "[]" in typ or "array<number>" in typ or "array[string]" in typ:
        return []
    if typ in ("object", "dict"):
        return {}
    if typ in ("int", "integer", "u64", "number"):
        return 0
    if typ in ("string", ""):
        return ""
    if typ == "boolean":
        return False
    return None

# ---------- 动态模块加载 ----------
def load_method_module(method: str) -> Optional[Any]:
    # LLM generated tools
    py_file = Path(f"tools/generated/ethereum/{method}.py")
    if not py_file.exists():
        return None
    spec = importlib.util.spec_from_file_location(method, py_file)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _assign_payload(payload: dict, path: str, value: Any) -> None:
    if "." not in path:
        payload[path] = value
        return
    
    keys = path.split(".")
    last = keys.pop()
    cur = payload
    for k in keys:
        cur = cur.setdefault(k, {})
    cur[last] = value

class ConstraintMutator:
    def __init__(self, method: str) -> None:
        self.method = method
        self._osc = OSCMutator(method)
        self._epc = EncodingEPC(method)
        self._spc = TransactionSPC()
        self._btc = BasicTypeBTC()

    def mutate(self, payload: List[Any], method: str) -> List[Any]:
        mod = load_method_module(method)
        if mod is None:
            payload = self._osc.mutate(payload)
            payload = self._spc.mutate(payload)
            payload = self._epc.mutate(payload)
            payload = self._btc.mutate(payload)
            return payload

        tools_json = Path(f"tools/generated/{method}.json")
        if tools_json.exists():
            tools = json.loads(tools_json.read_text())
            for tool in tools["tools"]:
                path = tool["param"]
                func_name = tool["script"].split("def ")[1].split("(")[0]
                if hasattr(mod, func_name):
                    value = getattr(mod, func_name)()
                    _assign_payload(payload, path, value)

        payload = self._osc.mutate(payload)
        payload = self._spc.mutate(payload)
        payload = self._epc.mutate(payload)
        payload = self._btc.mutate(payload)

        return payload

    def mutate_batch(self, base: List[Any], method: str, count: int) -> List[List[Any]]:
        mutants = []
        for _ in range(count):
            # deep copy
            new_mutant = deepcopy(base)
            new_mutant = self.mutate(new_mutant, method)
            mutants.append(new_mutant)
        return mutants

# ---------- CLI ----------
if __name__ == "__main__":
    import argparse, json, os
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True, help="RPC method name")
    parser.add_argument("--num", type=int, default=5, help="how many mutants")
    parser.add_argument("--out", default="mutants.jsonl", help="output file")
    args = parser.parse_args()

    mutator = ConstraintMutator()
    base = generate_base_skeleton(args.method)
    mutants = mutator.mutate_batch(base, args.method, args.num)

    with open(args.out, "w", encoding="utf8") as f:
        for m in mutants:
            f.write(json.dumps(m) + "\n")

    print(f"[Constraint] {args.num} mutants saved → {args.out}")