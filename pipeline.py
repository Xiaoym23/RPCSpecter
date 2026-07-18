#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import DEFAULT_MUTATIONS, REQUEST_TIMEOUT, ROOT, get_chain, get_rpc_url  # noqa: E402
from ConstraintDrivenMutation.mutator_engine import ConstraintMutator, generate_base_skeleton  # noqa: E402
from BidirectionalDefectAssertion.bidirectional_assert import dynamic_assert  # noqa: E402


def _params_to_jsonrpc_array(params: Dict[str, Any]) -> List[Any]:
    # Python dicts preserve insertion order; the skeleton is built from the spec order.
    out: List[Any] = []
    for value in params.values():
        out.append(list(value) if isinstance(value, (list, tuple)) else value)
    return out


def send_one(req: Dict[str, Any], method: str, rpc_url: str, timeout: float = REQUEST_TIMEOUT) -> Dict[str, Any]:
    req_params = _params_to_jsonrpc_array(req.get("params", {}))
    try:
        resp = requests.post(
            rpc_url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": req_params},
            timeout=timeout,
        )
        try:
            body = resp.json()
        except Exception:
            body = {"error": {"message": resp.text}}
        return {"http_status": resp.status_code, **body}
    except Exception as exc:
        return {"http_status": 0, "error": {"message": str(exc), "type": type(exc).__name__}}


def _method_root(chain: str) -> Path:
    return ROOT / "ConstraintExtraction" / "constraints" / chain


def pipeline_all(chain: str, rpc_url: str, count: int, method_filter: Optional[str] = None) -> None:
    root = _method_root(chain)
    if not root.exists():
        raise FileNotFoundError(f"Constraint directory not found: {root}. Run ConstraintExtraction/llm.py first.")

    final_root = ROOT / "results" / chain
    final_root.mkdir(parents=True, exist_ok=True)

    method_dirs = [p for p in sorted(root.iterdir()) if p.is_dir()]
    method_files = [p for p in sorted(root.glob("*.json"))]
    method_names = [p.name for p in method_dirs] + [p.stem for p in method_files]

    for method in method_names:
        if method_filter and method != method_filter:
            continue
        print(f"\n========== Testing {chain}:{method} ==========")
        base = generate_base_skeleton(method, chain)
        if not base:
            print(f"[skip] no parameter skeleton for {method}")
            continue
        _test_one_method(method, base, final_root, chain, rpc_url, count)


def _test_one_method(method: str, base: Dict[str, Any], final_root: Path, chain: str, rpc_url: str, count: int) -> None:
    mutator = ConstraintMutator(method, chain)
    mutants = mutator.mutate_batch(base, method, count)

    res_dir = final_root / method
    res_dir.mkdir(parents=True, exist_ok=True)

    stats = {
        "NEG_PASS": 0,
        "PASS": 0,
        "FAILED": 0,
        "GOLDEN_CREATED": 0,
        "GOLDEN_UPDATED": 0,
        "NEG_VIOLATION": 0,
    }

    with (res_dir / "mutations.jsonl").open("w", encoding="utf8") as fm, (res_dir / "results.jsonl").open("w", encoding="utf8") as fr:
        for idx, raw_params in enumerate(mutants):
            mutant = {"params": raw_params, "_id": f"{method}_{idx}"}
            resp = send_one(mutant, method, rpc_url)
            verdict = dynamic_assert(mutant, resp, method, chain)
            stats.setdefault(verdict, 0)
            stats[verdict] += 1

            if verdict == "NEG_VIOLATION":
                print(f"[{method} {idx:03d}] NEG_VIOLATION — invalid input accepted")
            else:
                print(f"[{method} {idx:03d}] {verdict}")

            fm.write(json.dumps(mutant, ensure_ascii=False) + "\n")
            fr.write(json.dumps({"id": mutant["_id"], "verdict": verdict, "request": mutant, "response": resp}, ensure_ascii=False) + "\n")

    stats["total"] = sum(v for v in stats.values() if isinstance(v, int))
    (res_dir / "report_summary.json").write_text(json.dumps(stats, indent=2, ensure_ascii=False), encoding="utf8")

    print(f"\n[{method}] Summary")
    for key in ["NEG_PASS", "PASS", "FAILED", "GOLDEN_CREATED", "GOLDEN_UPDATED", "NEG_VIOLATION"]:
        print(f"{key:18} : {stats.get(key, 0)}")
    print(f"{'TOTAL':18} : {stats['total']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RPCSpecter end-to-end fuzzing pipeline.")
    parser.add_argument("--chain", default=get_chain(), choices=["ethereum", "solana"])
    parser.add_argument("--rpc", default=None, help="RPC endpoint; defaults to ETH_RPC/SOLANA_RPC.")
    parser.add_argument("--count", type=int, default=DEFAULT_MUTATIONS, help="mutations per method")
    parser.add_argument("--method", default=None, help="optional single method to test")
    args = parser.parse_args()

    rpc_url = args.rpc or get_rpc_url(args.chain)
    pipeline_all(args.chain, rpc_url, args.count, args.method)


if __name__ == "__main__":
    main()
