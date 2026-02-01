# RPCSpecter
## Introduction
A specification-driven, constraint-aware fuzzing tool for blockchain RPC

## Installation
### Prerequisites
- Python 3.11+
- Local Solana/Ethereum/... dev node (e.g., "http://127.0.0.1:8899" or "http://127.0.0.1:32778" or ...)
- OpenAI API key 
### Setup
```
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt  

# Set environment variables
export OPENAI_API_KEY="sk-xxx"
export SOLANA_RPC="http://127.0.0.1:8899"
export ETH_RPC="http://127.0.0.1:32778"
```

## Quick Start
```
python3 main.py
```
