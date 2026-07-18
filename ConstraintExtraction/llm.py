#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import ROOT, get_chain  # noqa: E402


def read_spec(path: Path) -> Dict:
    with path.open(encoding="utf8") as f:
        return json.load(f)


def write_json(out: Path, data: Dict) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def build_chain(model: str):
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    system_prompt = (ROOT / "ConstraintExtraction" / "prompts" / "prompt.txt").read_text(
        encoding="utf8"
    )
    system_prompt = system_prompt.replace("{", "{{").replace("}", "}}")
    llm = ChatOpenAI(
        model=model,
        base_url=os.getenv("base_url"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("user", "{rpc_json}"),
    ])
    return prompt | llm | JsonOutputParser()


def scan_and_extract(chain_name: str, model: str) -> None:
    spec_root = ROOT / "RPC_Specification" / chain_name
    constraint_dir = ROOT / "ConstraintExtraction" / "constraints" / chain_name
    negative_dir = ROOT / "ConstraintExtraction" / "assertions" / chain_name / "negative_rules"

    if not spec_root.exists():
        raise FileNotFoundError(f"RPC specification directory not found: {spec_root}")

    llm_chain = build_chain(model)
    for i, spec_file in enumerate(sorted(spec_root.rglob("*.json")), start=1):
        spec = read_spec(spec_file)
        dual = llm_chain.invoke({"rpc_json": json.dumps(spec, indent=2, ensure_ascii=False)})
        rel = spec_file.relative_to(spec_root)
        write_json(constraint_dir / rel, dual["constraint_table"])
        write_json(negative_dir / rel, dual["negative_rules"])
        print(f"No.{i} [{chain_name}] {rel} -> constraints + negative_rules")


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract RPCSpecter OSC/PDC/STC constraints.")
    parser.add_argument("--chain", default=get_chain(), choices=["ethereum", "solana"])
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.1"))
    args = parser.parse_args()
    scan_and_extract(args.chain, args.model)


if __name__ == "__main__":
    main()
