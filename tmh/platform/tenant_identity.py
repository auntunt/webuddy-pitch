"""Request identity shared by imported modules and the ``python -m`` worker.

Keep ContextVar ownership outside the executable module. Tokens are set/reset by
TenantContext.acting; no default actor has execution authority.
"""
from contextvars import ContextVar

ACTOR = ContextVar('tenant_actor', default='')
TOOL = ContextVar('tenant_tool_connection', default=None)
