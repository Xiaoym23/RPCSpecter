#!/usr/bin/env python3
import json, os
from pathlib import Path
from typing import Dict, List

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser

# ---------- Path ----------
# SPEC_ROOT        = Path("../solana_rpc_docs")   # solana
SPEC_ROOT        = Path("../rpc_docs_output")   # ethereum
CONSTRAINT_DIR   = Path("constraints/ethereum")       # constraints
NEGATIVE_DIR     = Path("assertions/ethereum/negative_rules")  # assertions
SYSTEM_PROMPT    = Path("prompts/prompt.txt").read_text(encoding="utf8")

SYSTEM_PROMPT = SYSTEM_PROMPT.replace("{", "{{").replace("}", "}}")

# ---------- LangChain ----------
llm = ChatOpenAI(  
    model="gpt-5.1",  
    base_url=os.getenv("base_url"),  # own base_url  
    api_key=os.getenv("OPENAI_API_KEY")  # own API key  
)
prompt = ChatPromptTemplate.from_messages([
    ("system", SYSTEM_PROMPT),
    ("user", "{rpc_json}")
])
chain = prompt | llm | JsonOutputParser()

# ---------- Tools ----------
def read_spec(path: Path) -> Dict:
    with path.open(encoding="utf8") as f:
        return json.load(f)

def write_json(out: Path, data: Dict):
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ---------- Main loop ----------
def scan_and_extract():
    i = 1
    for spec_file in SPEC_ROOT.rglob("*.json"):
        spec = read_spec(spec_file)

        # One call → Two tables
        dual = chain.invoke({"rpc_json": json.dumps(spec, indent=2)})

        # constraint_table
        rel = spec_file.relative_to(SPEC_ROOT)
        write_json(CONSTRAINT_DIR / rel, dual["constraint_table"])

        # negative_rules
        write_json(NEGATIVE_DIR / rel, dual["negative_rules"])

        print(f"No.{i} [Dual] {rel} → constraint + negative_rules")

        i = i + 1 

# ---------- Entry ----------
if __name__ == "__main__":
    scan_and_extract()