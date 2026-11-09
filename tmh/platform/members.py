"""Single-machine members: list, add, remove, role change and password reset. Owner-only, enforced by the HTTP layer."""
from __future__ import annotations

from pathlib import Path

from . import login as L


def view(data_dir) -> list[dict]:
    users = L._legacy_users(Path(data_dir))
    return [{"name": name, "role": L.role_of(Path(data_dir), name)} for name in users]


def add(data_dir, name: str, password: str, role: str) -> None:
    if name in L._legacy_users(Path(data_dir)):
        raise ValueError("这个账号已经存在")
    if role not in L.ROLES or role == "owner":
        raise ValueError("新成员的角色只能是 editor（可修改）或 viewer（可查看）")
    L.set_user(Path(data_dir), name, password)
    L.set_role(Path(data_dir), name, role)


def remove(data_dir, name: str, actor: str) -> None:
    if name == actor:
        raise ValueError("不能删除自己正在使用的账号")
    if L.role_of(Path(data_dir), name) == "owner" and sum(1 for u in view(data_dir) if u["role"] == "owner") == 1:
        raise ValueError("至少要保留一个所有者")
    if not L.del_user(Path(data_dir), name):
        raise ValueError("没有这个账号")


def set_role(data_dir, name: str, role: str, actor: str) -> None:
    if name == actor and role != "owner":
        raise ValueError("不能降低自己的角色")
    if role == "owner" or L.role_of(Path(data_dir), name) == "owner":
        if role != "owner" and sum(1 for u in view(data_dir) if u["role"] == "owner") == 1:
            raise ValueError("至少要保留一个所有者")
    L.set_role(Path(data_dir), name, role)


def reset_password(data_dir, name: str, password: str) -> None:
    if name not in L._legacy_users(Path(data_dir)):
        raise ValueError("没有这个账号")
    L.set_user(Path(data_dir), name, password)
