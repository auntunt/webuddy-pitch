"""`tmh serve`: the platform's HTTP server (stdlib only) and JSON API.

Bound to 127.0.0.1 by default. Writes need the `X-TMH: 1` header (a browser
cannot send it cross-site without a preflight we never answer), and when
TMH_TOKEN is set every API call needs it too, as `X-TMH-Token` or `?token=`.
Serving to a team on the LAN: `tmh serve --host 0.0.0.0` with TMH_TOKEN set.
"""
from __future__ import annotations

import errno
from .http_encoding import encode_json
import hashlib
import hmac
import http.client
import json
import mimetypes
import os
import re
import secrets
import threading
import time
import traceback
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .. import __version__
from .agents import Runner, available, git, is_git, pick_model
from .metrics import compute as compute_metrics, md_html, report_md, ts_norm
from . import command, agent_routes
from .coderefs import FILE_LINE
from .errors import ApiError
from .knowledge import Knowledge
from .orchestra import Orchestra
from .store import PRIORITIES, RUN_MODES, STATUSES, TYPES, Store, now, timestamp_offset

# Compatibility surface: the platform was split into app.py, api/ and httpd/. Everything that used to be
# importable from here still is.
from .app import (  # noqa: F401
    Platform,
    _map_pri,
    _map_type,
    _routed_agent,
    _section,
)
from .api import (  # noqa: F401
    ROUTES,
    route,
)
from .api._common import (  # noqa: F401
    _allowed_project_ids,
    _chooser,
    _direct_api_allowed,
    _human_action,
    _lesson_human_actor,
    _personal_review_access,
    _platform_admin,
    _private,
    _route_metadata,
    _session_actor,
    _workspace_id,
)
from .api.workspace import (  # noqa: F401
    _handoff_work,
    api_agent,
    api_candidate,
    api_delivery_packet,
    api_development,
    api_development_action,
    api_handoff_action,
    api_handoffs,
    api_learning,
    api_learning_action,
    api_meeting,
    api_meeting_action,
    api_meeting_create,
    api_meetings,
    api_memory,
    api_memory_action,
    api_memory_brief,
    api_meta,
    api_pilot,
    api_pilot_action,
    api_pilot_create,
    api_pilots,
    api_project_ci,
    api_project_ci_save,
    api_team,
    api_team_action,
    api_ticket_ci,
    api_work_brief,
    api_work_brief_save,
    api_workspace,
)
from .api.projects import (  # noqa: F401
    _importer,
    api_add_project,
    api_bootstrap_project,
    api_create_delivery,
    api_create_delivery_content,
    api_deliveries,
    api_delivery,
    api_delivery_action,
    api_delivery_catalog,
    api_delivery_content,
    api_delivery_coverage,
    api_delivery_coverage_action,
    api_habits,
    api_import_chunk,
    api_import_finish,
    api_import_project,
    api_import_status,
    api_knowledge_file,
    api_knowledge_search,
    api_library,
    api_library_action,
    api_org_knowledge,
    api_project,
    api_projects,
    api_save_delivery_content,
)
from .api.knowledge import (  # noqa: F401
    _kb_confirm_actor,
    api_arch,
    api_arch_domain,
    api_code_map_create,
    api_code_maps,
    api_entries_detect,
    api_flow,
    api_kb,
    api_kb_answer,
    api_kb_ask,
    api_kb_confirm,
    api_kb_page,
    api_kb_questions,
    api_kb_tree,
    api_kb_triage,
    api_related,
    api_statechart_renderer,
    api_statecharts,
)
from .api.sessions import (  # noqa: F401
    _default_session,
    api_ask_client,
    api_assist,
    api_assist_list,
    api_bots,
    api_capture_token,
    api_catchup,
    api_client_change,
    api_import,
    api_inbox,
    api_intake_act,
    api_intake_get,
    api_intake_retry,
    api_intake_start,
    api_ints,
    api_kb_metrics,
    api_kb_overrule,
    api_lead,
    api_loop,
    api_new_session,
    api_path_map,
    api_path_map_record,
    api_pin,
    api_pin_add,
    api_pin_intake,
    api_pins,
    api_points,
    api_points_add,
    api_project_similar,
    api_session,
    api_session_ask,
    api_session_assistant,
    api_sessions,
    api_survey,
    api_survey_start,
    api_survey_stop,
    api_ticket_ops,
    api_ticket_ops_act,
    api_ticket_similar,
    api_update_session,
)
from .api.lessons import (  # noqa: F401
    api_accept,
    api_alert_paste,
    api_command,
    api_command_state,
    api_eval_case,
    api_eval_history,
    api_eval_history_import,
    api_eval_run,
    api_external_requirement,
    api_learn,
    api_learn_holdout,
    api_lesson,
    api_lesson_share_preview,
    api_lesson_snapshot,
    api_session_ticket,
    api_ticket_draft,
)
from .api.tickets import (  # noqa: F401
    _api_update_ticket,
    api_baseline,
    api_baseline_seal,
    api_epic,
    api_epic_act,
    api_evidence,
    api_evidence_add,
    api_ledger,
    api_new_ticket,
    api_ticket,
    api_tickets,
    api_update_ticket,
    api_upstream,
    api_upstream_act,
    api_upstream_list,
)
from .api.settings import (  # noqa: F401
    api_access_config,
    api_access_config_save,
    api_agent_scan,
    api_agent_settings,
    api_agent_settings_save,
    api_agent_test,
    api_channels,
    api_claim,
    api_handwork,
    api_handwork_scan,
    api_mode,
    api_mode_set,
    api_notify_set,
    api_preview,
    api_preview_conf,
    api_preview_conf_set,
    api_preview_do,
    api_project_test_report,
    api_project_tests,
    api_project_tests_save,
    api_readiness,
    api_release_again,
    api_releases,
    api_repo_set,
    api_rollback,
    api_starter,
    api_testbox,
    api_testbox_act,
    api_testbox_save,
)
from .api.runs import (  # noqa: F401
    _require_unmanaged_run,
    api_cancel,
    api_comment,
    api_decide,
    api_metrics,
    api_page_check,
    api_page_check_state,
    api_project_run,
    api_push,
    api_recheck,
    api_recheck_recover,
    api_recheck_state,
    api_recover_run,
    api_report,
    api_retry_run,
    api_review_feedback,
    api_run,
    api_run_say,
    api_runs,
    api_start_run,
    api_stats,
    api_ticket_context,
    api_ticket_prompt,
    api_ticket_related,
    api_use_prompt,
)
from .api.workbench import (  # noqa: F401
    _public_link,
    api_chats,
    api_client,
    api_client_act,
    api_client_new,
    api_clients,
    api_prod_request_act,
    api_prod_requests,
    api_requirements,
    api_share_new,
    api_share_revoke,
    api_standing,
    api_system_new,
    api_systems,
    api_ticket_system,
    api_today,
    api_versions,
    api_workbench_intake,
)
from .httpd.util import (  # noqa: F401
    _cookie,
    _length,
)
from .httpd.preview import (  # noqa: F401
    _pvkey,
    make_preview_handler,
    serve_preview,
)
from .httpd.handler import (  # noqa: F401
    Req,
    make_handler,
)
from .httpd.serve import (  # noqa: F401
    serve,
)
