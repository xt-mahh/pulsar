#!/usr/bin/env python3
"""Debug import issue."""
import sys
sys.path.insert(0, '/nas1/nas1/project/pulsar/src')

# First, let's verify we can import base module directly without going through __init__
import importlib.util

spec = importlib.util.spec_from_file_location(
    "pulsar.execution.tools.base",
    "/nas1/nas1/project/pulsar/src/pulsar/execution/tools/base.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
print("base module loaded, ToolDefinition:", mod.ToolDefinition)

# Now try registry directly
spec2 = importlib.util.spec_from_file_location(
    "pulsar.execution.tools.registry",
    "/nas1/nas1/project/pulsar/src/pulsar/execution/tools/registry.py"
)
mod2 = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(mod2)
print("registry module loaded OK")
print("ToolRegistry:", mod2.ToolRegistry)
