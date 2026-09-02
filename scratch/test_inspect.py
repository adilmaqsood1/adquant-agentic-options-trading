import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.execution.options_executor import inspect_option_contract
res = inspect_option_contract("ORCL261002C00143000")
print("inspect_option_contract result:")
for k, v in res.items():
    print(f"  {k}: {v}")
