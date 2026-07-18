"""Shared configuration and path helpers for RPCSpecter.

RPCSpecter uses three constraint classes: OSC (On-chain State), PDC
(Procedural), and STC (Syntax).  The current prototype still contains
legacy module names such as SPC/EPC/BTC; this file centralizes
chain/runtime configuration so those modules can be used consistently
from any working directory.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent


def get_chain(default: str = "ethereum") -> str:
    chain = os.getenv("CHAIN", default).strip().lower()
    if chain not in {"ethereum", "solana"}:
        raise ValueError(f"Unsupported CHAIN={chain!r}; expected 'ethereum' or 'solana'.")
    return chain


def get_rpc_url(chain: Optional[str] = None) -> str:
    chain = chain or get_chain()
    env_name = "ETH_RPC" if chain == "ethereum" else "SOLANA_RPC"
    fallback = "http://127.0.0.1:8545" if chain == "ethereum" else "http://127.0.0.1:8899"
    return os.getenv(env_name, fallback)


def artifact_path(*parts: str | os.PathLike[str]) -> Path:
    return ROOT.joinpath(*parts)


CHAIN = get_chain()
RPC_URL = get_rpc_url(CHAIN)
REQUEST_TIMEOUT = float(os.getenv("RPC_TIMEOUT", "3"))
DEFAULT_MUTATIONS = int(os.getenv("MUTATION_COUNT", "500"))
