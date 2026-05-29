#!/usr/bin/env python3
import sys
sys.path.insert(0, 'src')
try:
    from pulsar.execution.tools.base import BaseTool
    print("base OK")
except Exception as e:
    import traceback
    traceback.print_exc()
