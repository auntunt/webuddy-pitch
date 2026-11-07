"""传统 toB 软件项目维护 harness：业务流理解、新需求、改造（含信创）。"""
__version__ = "0.4.0"

# Service and CLI imports are read-only, including cold imports inside audited tools.
# Python checks this flag after executing a module, before publishing its .pyc.
import sys
sys.dont_write_bytecode = True
