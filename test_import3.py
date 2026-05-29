#!/usr/bin/env python3
import sys, os
sys.path.insert(0, '/nas1/nas1/project/pulsar/src')

# Import base module first (no list[str] dependency)
from pulsar.execution.tools.base import BaseTool, ToolDefinition, ToolExecutionError
print("base imports OK")

# Try importing registry directly - but it imports from base
# Let's check what happens with list[str] in a standalone module
import tempfile, textwrap
tmpdir = tempfile.mkdtemp()
testfile = os.path.join(tmpdir, 'test_list_annote.py')
with open(testfile, 'w') as f:
    f.write(textwrap.dedent("""\
        from __future__ import annotations
        def foo() -> list[str]:
            pass
        print("list[str] annotation in standalone module OK")
    """))
sys.path.insert(0, tmpdir)
import test_list_annote
print("Done")
