#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import ROOT, get_chain  # noqa: E402

try:  # support both package and script execution
    from .mutators.osc_mutator import OSCMutator
    from .mutators.pdc_mutator import PDCMutator
    from .mutators.stc_mutator import STCMutator
except ImportError:  # pragma: no cover
    from mutators.osc_mutator import OSCMutator
    from mutators.pdc_mutator import PDCMutator
    from mutators.stc_mutator import STCMutator


def _constraint_file(chain: str, method: str) -> Optional[Path]:
    root = ROOT / "ConstraintExtraction" / "constraints" / chain
    candidates = [root / method / f"{method}.json", root / f"{method}.json"]
    for p in candidates:
        if p.exists():
            return p
    matches = list(root.glob(f"**/{method}.json")) if root.exists() else []
    return matches[0] if matches else None


def generate_base_skeleton(method: str, chain: Optional[str] = None) -> Dict[str, Any]:
    """Generate an empty request-parameter skeleton from extracted constraints."""
    chain = chain or get_chain()
    spec_file = _constraint_file(chain, method)
    if spec_file is None:
        return {}

    data = json.loads(spec_file.read_text(encoding="utf8"))
    skeleton: Dict[str, Any] = {}
    for param in data.get("params", []):
        _assign_empty(skeleton, param.get("name", ""), param.get("type", ""), param.get("sub_parameters", []))
    return skeleton


def _assign_empty(obj: dict, name: str, typ: str, sub: List[dict]) -> None:
    if not name:
        return
    if not sub:
        obj[name] = _empty_value(typ)
        return
    child: Dict[str, Any] = {}
    for sub_param in sub:
        _assign_empty(child, sub_param.get("name", ""), sub_param.get("type", ""), sub_param.get("sub_parameters", []))
    obj[name] = child


def _empty_value(typ: str) -> Any:
    typ = (typ or "").lower()
    if "array" in typ or "[]" in typ:
        return []
    if typ in {"object", "dict"}:
        return {}
    if typ in {"int", "integer", "u64", "number"}:
        return 0
    if typ in {"string", "str", ""}:
        return ""
    if typ in {"boolean", "bool"}:
        return False
    return None


def load_method_module(method: str, chain: Optional[str] = None) -> Optional[Any]:
    chain = chain or get_chain()
    candidates = [
        ROOT / "ConstraintExtraction" / "tools" / "generated" / chain / f"{method}.py",
        ROOT / "tools" / "generated" / chain / f"{method}.py",
    ]
    py_file = next((p for p in candidates if p.exists()), None)
    if py_file is None:
        return None
    spec = importlib.util.spec_from_file_location(method, py_file)
    if spec is None or spec.loader is None:
        return None
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
    """OSC/PDC/STC mutation coordinator for RPCSpecter.

    The coordinator composes the three mutator families described by the
    framework: syntax-level exploration, on-chain-state mutation, and
    procedural pipeline perturbation.
    """

    def __init__(self, method: str, chain: Optional[str] = None) -> None:
        self.method = method
        self.chain = chain or get_chain()
        self._osc = OSCMutator(method, self.chain)
        self._pdc = PDCMutator(method, self.chain)
        self._stc = STCMutator(method, self.chain)

    def mutate(self, payload: Dict[str, Any], method: Optional[str] = None) -> Dict[str, Any]:
        method = method or self.method
        mod = load_method_module(method, self.chain)
        if mod is not None:
            tools_json = ROOT / "ConstraintExtraction" / "tools" / "generated" / self.chain / f"{method}.json"
            if tools_json.exists():
                tools = json.loads(tools_json.read_text(encoding="utf8"))
                for tool in tools.get("tools", []):
                    path = tool.get("path") or tool.get("param")
                    script = tool.get("script") or tool.get("legal")
                    if not path or not script or "def " not in script:
                        continue
                    func_name = script.split("def ", 1)[1].split("(", 1)[0]
                    if hasattr(mod, func_name):
                        _assign_payload(payload, path, getattr(mod, func_name)())

        # Constraint-guided scheduling: start from syntax-compatible requests,
        # instantiate or forge on-chain state, then perturb procedural artifacts.
        # This keeps most mutants near-valid while still exercising each
        # OSC/PDC/STC violation class independently.
        payload = self._stc.mutate(payload)
        payload = self._osc.mutate(payload)
        payload = self._pdc.mutate(payload)
        return payload

    def mutate_batch(self, base: Dict[str, Any], method: Optional[str] = None, count: int = 500) -> List[Dict[str, Any]]:
        method = method or self.method
        mutants: List[Dict[str, Any]] = []
        for _ in range(count):
            mutants.append(self.mutate(deepcopy(base), method))
        return mutants


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--method", required=True, help="RPC method name")
    parser.add_argument("--chain", default=get_chain(), choices=["ethereum", "solana"])
    parser.add_argument("--num", type=int, default=5, help="how many mutants")
    parser.add_argument("--out", default="mutants.jsonl", help="output file")
    args = parser.parse_args()

    mutator = ConstraintMutator(args.method, args.chain)
    base = generate_base_skeleton(args.method, args.chain)
    mutants = mutator.mutate_batch(base, args.method, args.num)

    with open(args.out, "w", encoding="utf8") as f:
        for m in mutants:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    print(f"[RPCSpecter] {args.num} mutants saved -> {args.out}")


if __name__ == "__main__":
    main()
