# Tests never hand clients' words to whatever coding agent happens to be installed on the machine: understanding by
# an agent is switched on per test, with a stand-in agent (tests/test_understand.py).
import os

os.environ.setdefault("TMH_UNDERSTAND", "rules")
