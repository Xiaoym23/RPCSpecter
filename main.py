#!/usr/bin/env python3
import json, os
from pathlib import Path
from ConstraintDrivenMutation.mutator_engine import ConstraintMutator, generate_base_skeleton
from BidirectionalDefectAssertion.bidirectional_assert import dynamic_assert
import requests
from typing import Any, Optional, List

# ---------------- config ----------------
# choose ethereum or solana or other blockchain
RPC = os.getenv("ETH_RPC")  # Ethereum RPC port
RPC = os.getenv("SOLANA_RPC")  # Solana RPC port
MUT_FILE    = Path("mutations.jsonl")
RESULT_FILE = Path("results.jsonl")
REPORT_FILE = Path("report_summary.json")
METHOD_PATH = Path("constraints/ethereum")
# METHOD_PATH = Path("constraints/ethereum")
OUTPUT_PATH = Path("results/ethereum")
# OUTPUT_PATH = Path("results/solana")

# RPC request
def send_one(req: dict, method: str) -> dict:
    req_vals = req["params"]
    req_params = []
    for v in req_vals.values():
        if isinstance(v, (list, tuple)):
            req_params.append(list(v))
        else:
            req_params.append(v)

    resp = requests.post(
        RPC,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": req_params},
        timeout=15
    )
    return {"http_status": resp.status_code, **resp.json()}

# ---------------- Main Entry ----------------
def pipeline_all():
    root = METHOD_PATH
    final_root = OUTPUT_PATH         
    final_root.mkdir(exist_ok=True)
    for method_dir in root.iterdir():
        if not method_dir.is_dir():
            continue
        method = method_dir.name               

        print(f"\n==========  Testing {method}  ==========")
        base = generate_base_skeleton(method)
        if not base:
            continue

        # Batch mutation & sending & assertion
        _test_one_method(method, base, final_root)

# Single-method complete pipeline
def _test_one_method(method: str, base: List[Any], final_root: Path):
    mutator = ConstraintMutator(method)
    # Mutation times
    count = 500
    mutants = mutator.mutate_batch(base, method, count)

    res_dir = final_root / method
    res_dir.mkdir(exist_ok=True)

    stats = {"NEG_PASS": 0, "PASS": 0, "FAILED": 0,
             "GOLDEN_CREATED": 0, "GOLDEN_UPDATED": 0, "NEG_VIOLATION": 0}

    with (res_dir / "mutations.jsonl").open("w") as fm, \
         (res_dir / "results.jsonl").open("w") as fr:

        for idx, raw_params in enumerate(mutants):      
            mutant = {"params": raw_params, "_id": f"{method}_{idx}"}   
            resp = send_one(mutant, method)
            verdict = dynamic_assert(mutant, resp, method)
            stats[verdict] += 1

            if verdict == "NEG_VIOLATION":
                print(f"[{method} {idx:03d}] 🔥 NEG_VIOLATION — Illegal input still succeeded！")
            else:
                print(f"[{method} {idx:03d}] {verdict}")

            fm.write(json.dumps(mutant) + "\n")
            fr.write(json.dumps({
                "id": mutant["_id"],
                "verdict": verdict,
                "request": mutant,
                "response": resp
            }) + "\n")

    stats["total"] = sum(stats[k] for k in stats if isinstance(stats[k], int))
    (res_dir / "report_summary.json").write_text(json.dumps(stats, indent=2))

    print(f"\n[{method}]  Summary")
    for k in ["NEG_PASS", "PASS", "FAILED", "GOLDEN_CREATED", "GOLDEN_UPDATED", "NEG_VIOLATION"]:
        print(f"{k:18} : {stats[k]}")
    print(f"{'TOTAL':18} : {stats['total']}")

# ---------------- CLI ----------------
if __name__ == "__main__":
    pipeline_all()