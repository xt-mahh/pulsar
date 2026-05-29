#!/usr/bin/env python3
import sys
sys.path.insert(0, '/nas1/nas1/project/pulsar/src')

# Check if list is shadowed
import builtins
print("list is:", type(builtins.list))
print("list[str]:", type(list[str]))

# Now try the import
try:
    import pulsar.execution.tools.base as base_mod
    print("base import OK")
except Exception as e:
    import traceback
    traceback.print_exc()
