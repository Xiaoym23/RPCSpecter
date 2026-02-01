from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langchain_core.output_parsers import JsonOutputParser
from pathlib import Path
import json
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys_prompt = Path("prompts/gen_functions.txt").read_text(encoding="utf8").replace("{", "{{").replace("}", "}}")

prompt = ChatPromptTemplate.from_messages([
    ("system", sys_prompt),
    ("user", "{osc_spc_list}")
])

llm = ChatOpenAI(  
    model="gpt-5.1",  
    base_url=os.getenv("base_url"),  # own base_url  
    api_key=os.getenv("OPENAI_API_KEY")  # own API key  
)

chain = prompt | llm | JsonOutputParser()

osc_spc_list = json.loads(Path("constraints/ethereum/final.json").read_text())
out = chain.invoke({"osc_spc_list": json.dumps(osc_spc_list, indent=2)})
Path("tools/ethereum/tools.json").write_text(json.dumps(out, indent=2))