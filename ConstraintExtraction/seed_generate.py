#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from config import ROOT, get_chain  # noqa: E402


def _iter_leaf_constraints(param: Dict[str, Any], prefix: str = "") -> List[Dict[str, Any]]:
    name = param.get("name", "")
    path = f"{prefix}.{name}" if prefix and name else name or prefix
    sub = param.get("sub_parameters") or []
    if sub:
        leaves: List[Dict[str, Any]] = []
        for child in sub:
            leaves.extend(_iter_leaf_constraints(child, path))
        return leaves
    item = dict(param)
    item["path"] = path
    return [item]


def collect_seed_support_input(chain_name: str) -> List[Dict[str, Any]]:
    constraint_root = ROOT / "ConstraintExtraction" / "constraints" / chain_name
    if not constraint_root.exists():
        raise FileNotFoundError(
            f"Constraint directory not found: {constraint_root}. Run ConstraintExtraction/llm.py first."
        )

    out: List[Dict[str, Any]] = []
    for file in sorted(constraint_root.rglob("*.json")):
        data = json.loads(file.read_text(encoding="utf8"))
        method = data.get("method") or data.get("method_name") or file.stem
        for param in data.get("params", []):
            for leaf in _iter_leaf_constraints(param):
                if leaf.get("constraint") in {"OSC", "PDC", "STC", "SPC", "EPC", "PTC"}:
                    leaf["method"] = method
                    out.append(leaf)
    return out


def build_chain(model: str):
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI

    sys_prompt = (ROOT / "ConstraintExtraction" / "prompts" / "gen_functions.txt").read_text(
        encoding="utf8"
    )
    sys_prompt = sys_prompt.replace("{", "{{").replace("}", "}}")
    prompt = ChatPromptTemplate.from_messages([
        ("system", sys_prompt),
        ("user", "{constraints}"),
    ])
    llm = ChatOpenAI(
        model=model,
        base_url=os.getenv("base_url"),
        api_key=os.getenv("OPENAI_API_KEY"),
    )
    return prompt | llm | JsonOutputParser()


def generate_seed_support(chain_name: str, model: str) -> None:
    constraints = collect_seed_support_input(chain_name)
    chain = build_chain(model)
    out = chain.invoke({"constraints": json.dumps(constraints, indent=2, ensure_ascii=False)})
    tools_dir = ROOT / "ConstraintExtraction" / "tools" / chain_name
    tools_dir.mkdir(parents=True, exist_ok=True)
    (tools_dir / "tools.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf8")
    print(f"Generated seed-support tools -> {tools_dir / 'tools.json'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate RPCSpecter seed-support artifacts.")
    parser.add_argument("--chain", default=get_chain(), choices=["ethereum", "solana"])
    parser.add_argument("--model", default=os.getenv("OPENAI_MODEL", "gpt-5.1"))
    args = parser.parse_args()
    generate_seed_support(args.chain, args.model)


if __name__ == "__main__":
    main()
