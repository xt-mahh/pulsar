#!/usr/bin/env python3
import sys
import traceback

sys.path.insert(0, '/nas1/nas1/project/pulsar/src')

# Monkey-patch builtins to track list usage
original_list = __builtins__['list'] if isinstance(__builtins__, dict) else __builtins__.list

# Try to catch what's happening
try:
    from pulsar.execution.tools.base import BaseTool
except Exception:
    traceback.print_exc()
    
    # Now let's see what 'list' actually is
    import pulsar.execution.tools.registry as reg_mod
