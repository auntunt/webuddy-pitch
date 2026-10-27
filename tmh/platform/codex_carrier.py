"""Trusted carrier seam, without a launcher, admission switch or model adapter.

A host-installed carrier prepares a fixed launch and verifies its private final
receipt. This module owns the single original Runner/SP invocation. Preparing a
plan must do no process/network work; controller, broker and relay all belong
under that one invocation. Public job configuration cannot select a carrier.
"""
import copy
from dataclasses import dataclass
import math
import time
from types import MappingProxyType
import uuid


@dataclass(frozen=True)
class CarrierContext:
    run_id: int
    launch_nonce: str
    owner: object
    deadline_monotonic: float
    cancel_event: object
    prompt: str
    model: str
    settings: object


@dataclass(frozen=True)
class CarrierLaunch:
    command: tuple
    environment: object
    verify: object


def run_carrier(runner, rid, carrier, settings, model, workdir, parameters):
    """Execute a prepared carrier once; never accept its replacement result."""
    if (settings.get("resume") is not False or settings.get("retry_busy") is not False
            or "cmd" in settings or parameters.get("prompt_transport") != ["stdin"]
            or not isinstance(parameters.get("prompt"), str)
            or parameters.get("stdin") != parameters["prompt"]):
        raise OSError("隔离载体需要完整stdin且禁止会话继承、自定义命令和重试")
    control = runner.controls.get(rid)
    lease = runner.owners.get(rid)
    if not control or not lease:
        raise OSError("隔离载体缺少原运行所有权")
    owner = copy.deepcopy(control["owner"])
    deadline = control["start"] + control["timeout_seconds"]
    if not math.isfinite(deadline):
        raise OSError("隔离载体缺少有限原截止点")

    def current():
        if (runner.controls.get(rid) is not control or runner.owners.get(rid) is not lease
                or lease.stream.closed or control["owner"] != owner or lease.owner != owner
                or control["finished"] or control["start"] + control["timeout_seconds"] != deadline):
            raise OSError("隔离载体原运行所有权已变化")
        if time.monotonic() >= deadline:
            runner._stopped(rid, "timeout")
        if runner.stop_reason(rid):
            raise OSError("隔离载体原运行已停止")

    current()
    context = CarrierContext(rid, uuid.uuid4().hex, MappingProxyType(owner), deadline, control["event"],
                             parameters["prompt"], model, MappingProxyType(copy.deepcopy(settings)))
    launch = carrier.prepare(context)
    if (type(launch) is not CarrierLaunch or type(launch.command) is not tuple or not launch.command
            or any(not isinstance(s, str) or not s or "\0" in s for s in launch.command)
            or not isinstance(launch.environment, dict)
            or any(not isinstance(k, str) or not k or "=" in k or "\0" in k
                   or not isinstance(v, str) or "\0" in v for k, v in launch.environment.items())
            or not callable(launch.verify)):
        raise OSError("隔离载体启动计划或私有回执校验缺失")
    current()  # Plan preparation consumes the original budget, never a new one.
    fixed = dict(parameters, env=dict(launch.environment))
    # No execute callback is exposed to the carrier, so it cannot request a
    # second attempt or replace owner/stdin/output handling/remaining time.
    process, folder = runner.run_command(rid, list(launch.command), workdir, **fixed)
    if process.reason != "exited" or process.returncode != 0:
        return process, folder
    current()
    if not process.cleanup.get("complete") or getattr(process, "error", ""):
        raise OSError("隔离载体原监管回执不完整")
    if launch.verify(context, process, folder) is not None:
        raise OSError("隔离载体校验不能替换原监管结果")
    current()  # A late verification cannot convert an expired job to success.
    return process, folder
