"""Load one installed host carrier; missing/foreign installation is unconfigured.

No registration writer, capability admission, process or network operation lives
here. The root entry still checks its private registration and entire bundle.
"""
import json
import math
import os
from pathlib import Path
import re
import stat

from . import codex_host_completion as C
from .codex_frozen_config import FrozenConfig
from .codex_host import RootCarrier


BUNDLE = Path("/opt/webuddy-codex-registered-root-v1")
DESCRIPTOR = BUNDLE / "public-descriptor.json"
ENTRY = BUNDLE / "source/root_entry"
COMPLETIONS = BUNDLE / "completions"
SCHEMA = "codex-registered-root-descriptor-v1"
FIELDS = frozenset((
    "schema", "registration_id", "service_uid", "service_gid", "data_root",
    "source_home", "source_owner_uid", "profile", "model", "configuration",
    "execution", "controller_entry", "controller_sha256", "bundle_manifest_sha256",
    "official_runtime_manifest_sha256", "completion_root", "timeout_max_seconds",
))
HASH_FIELDS = ("registration_id", "controller_sha256", "bundle_manifest_sha256",
               "official_runtime_manifest_sha256")
MAX_DESCRIPTOR_BYTES = 64 * 1024


def _json(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate registration descriptor field")
            value[key] = item
        return value

    def constant(value):
        raise ValueError("non-finite registration descriptor field")

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_constant=constant)
    except (UnicodeError, ValueError):
        raise OSError("invalid complete registration descriptor JSON") from None


def _read_descriptor():
    # Absence at initial lookup is unconfigured. Disappearance after opening
    # the file is a changed installation and must propagate as an error.
    try:
        base = C.open_root(BUNDLE)
    except FileNotFoundError:
        return None
    try:
        anchor = os.fstat(base)
        try:
            fd = os.open(DESCRIPTOR.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=base)
        except FileNotFoundError:
            return None
        try:
            before = os.fstat(fd)
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != C.ROOT_UID
                    or stat.S_IMODE(before.st_mode) != 0o640 or before.st_nlink != 1
                    or before.st_size > MAX_DESCRIPTOR_BYTES):
                raise OSError("untrusted registration descriptor file")
            with os.fdopen(fd, "rb", closefd=False) as stream:
                raw = stream.read(MAX_DESCRIPTOR_BYTES + 1)
            if (len(raw) != before.st_size or C._identity(before) != C._identity(os.fstat(fd))
                    or C._identity(before) != C._identity(os.stat(DESCRIPTOR.name, dir_fd=base,
                                                                follow_symlinks=False))):
                raise OSError("registration descriptor changed during complete read")
        finally:
            os.close(fd)
        fresh = C.open_root(BUNDLE)
        try:
            if (anchor.st_dev, anchor.st_ino) != (os.fstat(fresh).st_dev, os.fstat(fresh).st_ino):
                raise OSError("registration installation directory replaced")
        finally:
            os.close(fresh)
        value = _json(raw)
        if not isinstance(value, dict) or set(value) != FIELDS or value["schema"] != SCHEMA:
            raise OSError("exact public registration descriptor schema required")
        if type(value["service_gid"]) is not int or value["service_gid"] < 0 or before.st_gid != value["service_gid"]:
            raise OSError("descriptor group differs from registered service group")
        return value
    finally:
        os.close(base)


def _validate(value):
    for key in HASH_FIELDS:
        if not isinstance(value[key], str) or not re.fullmatch(r"[0-9a-f]{64}", value[key]):
            raise OSError("invalid public registration digest")
    for key in ("service_uid", "service_gid", "source_owner_uid"):
        if type(value[key]) is not int or value[key] < 0:
            raise OSError("invalid public registration identity")
    if value["service_uid"] in (0, 508101) or value["source_owner_uid"] != value["service_uid"]:
        raise OSError("distinct registered service/configuration owner required")
    for key in ("data_root", "source_home", "controller_entry", "completion_root"):
        path = value[key]
        if not isinstance(path, str) or "\0" in path or not Path(path).is_absolute() or ".." in Path(path).parts:
            raise OSError("absolute registered path required")
    if value["controller_entry"] != str(ENTRY) or value["completion_root"] != str(COMPLETIONS):
        raise OSError("registered installation path differs from fixed path")
    if not isinstance(value["configuration"], dict) or not isinstance(value["execution"], dict):
        raise OSError("complete registered source/execution binding required")
    execution = C.execution_binding(value["execution"])
    if C.encoded(execution) != C.encoded(value["execution"]):
        raise OSError("registered execution must contain only frozen fields")
    config = value["configuration"]
    if (not isinstance(value["profile"], str) or not value["profile"]
            or not isinstance(value["model"], str) or not value["model"]
            or execution["profile"] != value["profile"] or config.get("profile") != value["profile"]
            or config.get("model") != value["model"]
            or type(config.get("source_owner_uid")) is not int
            or config["source_owner_uid"] != value["source_owner_uid"]):
        raise OSError("registered profile/model/source/execution differs")
    maximum = value["timeout_max_seconds"]
    if type(maximum) not in (int, float) or not math.isfinite(maximum) or not 2 < maximum <= execution["timeout"]:
        raise OSError("invalid registered original execution bound")
    return execution


def load_codex_carrier(data_dir, *, environment=None):
    """Return a fixed carrier, or None for absent installation/another data root.

    A readable but invalid descriptor raises. Foreign data roots never read the
    production source configuration or receive the production carrier.
    """
    value = _read_descriptor()
    if value is None:
        return None
    execution = _validate(value)
    if str(Path(data_dir).resolve()) != value["data_root"]:
        return None
    if os.geteuid() != value["service_uid"] or os.getegid() != value["service_gid"]:
        raise OSError("caller differs from registered service identity")
    environment = os.environ if environment is None else environment
    frozen = FrozenConfig(value["source_home"], value["profile"], value["model"], environment,
                          value["source_owner_uid"])
    if C.encoded(frozen.binding()) != C.encoded(value["configuration"]):
        raise OSError("original registered source configuration changed")
    fd = C.open_root(COMPLETIONS, value["service_gid"])
    os.close(fd)
    carrier = RootCarrier(frozen, environment, controller_entry=ENTRY,
                          controller_sha256=value["controller_sha256"],
                          registration_id=value["registration_id"], execution_binding=execution,
                          completion_root=COMPLETIONS, service_gid=value["service_gid"])
    carrier._entry_current()
    return carrier
