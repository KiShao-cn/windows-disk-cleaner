"""
安全校验模块 - 整个项目的安全边界。

================== 安全边界说明 ==================
本模块是所有删除操作的最终守门人。任何文件在被删除之前
必须通过本模块的 ``is_safe_to_delete`` 校验，否则一律拒绝。

设计原则：
1. 白名单优先：目标文件必须位于显式白名单根目录之内。
2. 黑名单一票否决：只要命中黑名单（系统目录、用户个人目录、
   程序目录等），无论是否在白名单内都禁止删除。
3. 路径规范化：使用 ``Path.resolve(strict=False)`` 解析真实
   路径，防止 ``..`` 路径穿越和符号链接欺骗。
4. 拒绝符号链接：任何指向白名单外的符号链接禁止删除。
5. 默认拒绝：任何无法判断是否安全的情况一律返回 False。

严禁修改本文件以扩大删除范围；如需新增白名单路径，必须经过
代码审查，并确保不会与黑名单冲突。
==================================================
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# ----------------------------------------------------------------------
# 系统级黑名单：绝对禁止删除/修改的目录（一票否决）
# 这些路径下的任何文件都不允许通过本工具删除。
# ----------------------------------------------------------------------
SYSTEM_BLOCKED_DIRS: tuple[str, ...] = (
    r"C:\Windows\System32",
    r"C:\Windows\SysWOW64",
    r"C:\Windows\WinSxS",
    r"C:\Windows\Boot",
    r"C:\Windows\Fonts",
    r"C:\Windows\Installer",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData\Microsoft",
)


# ----------------------------------------------------------------------
# 用户个人文件黑名单（相对用户目录）
# 这些目录只能用于"大文件展示"，绝不允许自动清理。
# ----------------------------------------------------------------------
USER_PERSONAL_SUBDIRS: tuple[str, ...] = (
    "Desktop",
    "Documents",
    "Pictures",
    "Videos",
    "Music",
    "Downloads",
    "OneDrive",
    "iCloudDrive",
    "Google Drive",
    "Dropbox",
    "Favorites",
    "Contacts",
    "Links",
    "Saved Games",
    "Searches",
)


# ----------------------------------------------------------------------
# 默认安全清理白名单（环境变量字符串，使用前会被展开）
# 仅这些目录及其子目录下满足规则的文件才允许被清理。
# ----------------------------------------------------------------------
DEFAULT_SAFE_PATH_TEMPLATES: tuple[str, ...] = (
    "%TEMP%",
    "%TMP%",
    r"%LOCALAPPDATA%\Temp",
    r"C:\Windows\Temp",
)


@dataclass(frozen=True)
class SafetyPolicy:
    """安全策略：包含白名单与黑名单的解析结果。"""

    safe_roots: tuple[Path, ...]
    blocked_roots: tuple[Path, ...]

    @classmethod
    def build_default(cls) -> "SafetyPolicy":
        """根据当前用户环境构造默认安全策略。"""
        safe_roots = tuple(_resolve_unique_paths(DEFAULT_SAFE_PATH_TEMPLATES))
        blocked_roots = tuple(_resolve_unique_paths(_collect_blocked_templates()))
        return cls(safe_roots=safe_roots, blocked_roots=blocked_roots)


def _expand_path(template: str) -> Path | None:
    """展开环境变量并返回 ``Path``，失败时返回 ``None``。"""
    try:
        expanded = os.path.expandvars(template)
        if not expanded or "%" in expanded:
            return None
        # strict=False 允许路径不存在；不存在时仍可用于父目录推断
        return Path(expanded).resolve(strict=False)
    except (OSError, ValueError):
        return None


def _resolve_unique_paths(templates: Iterable[str]) -> list[Path]:
    """批量展开模板路径并去重。"""
    resolved: list[Path] = []
    seen: set[str] = set()
    for tpl in templates:
        path = _expand_path(tpl)
        if path is None:
            continue
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        resolved.append(path)
    return resolved


def _collect_blocked_templates() -> list[str]:
    """汇总所有黑名单路径（系统 + 用户个人）。"""
    blocked: list[str] = list(SYSTEM_BLOCKED_DIRS)
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        for sub in USER_PERSONAL_SUBDIRS:
            blocked.append(os.path.join(user_profile, sub))
    public = os.environ.get("PUBLIC")
    if public:
        for sub in ("Desktop", "Documents", "Pictures", "Videos", "Music", "Downloads"):
            blocked.append(os.path.join(public, sub))
    return blocked


def _is_under(path: Path, root: Path) -> bool:
    """判断 ``path`` 是否等于 ``root`` 或位于其子目录之下。

    使用规范化后的字符串比较以兼容大小写不敏感的 Windows 文件系统。
    """
    try:
        path_str = str(path).lower().rstrip("\\/")
        root_str = str(root).lower().rstrip("\\/")
    except Exception:
        return False
    if path_str == root_str:
        return True
    return path_str.startswith(root_str + os.sep.lower()) or path_str.startswith(
        root_str + "/"
    )


def is_safe_to_delete(
    path: Path | str,
    policy: SafetyPolicy,
    *,
    allow_symlink: bool = False,
) -> bool:
    """判断给定路径是否允许被本工具删除。

    本函数即《需求文档》第 15 节描述的安全校验函数。
    任何删除操作必须先经过此函数返回 True 才能继续。

    参数:
        path: 待检查的文件或目录路径。
        policy: 当前安全策略（白名单 + 黑名单）。
        allow_symlink: 是否允许目标为符号链接，默认 False。

    返回:
        True 表示通过校验，可以删除；False 表示禁止删除。
    """
    try:
        target = Path(path)
    except (TypeError, ValueError):
        return False

    # 解析真实路径，防止 .. 路径穿越和符号链接欺骗
    try:
        resolved = target.resolve(strict=False)
    except (OSError, RuntimeError):
        return False

    # 拒绝指向白名单外的符号链接
    try:
        if target.is_symlink() and not allow_symlink:
            return False
    except OSError:
        return False

    # 黑名单一票否决：命中任何一项都直接拒绝
    for blocked in policy.blocked_roots:
        if _is_under(resolved, blocked):
            return False

    # 必须位于某个白名单根目录之内
    is_under_safe_root = any(_is_under(resolved, root) for root in policy.safe_roots)
    if not is_under_safe_root:
        return False

    # 不允许删除白名单根目录本身（仅允许删除其内部文件）
    for root in policy.safe_roots:
        if str(resolved).lower().rstrip("\\/") == str(root).lower().rstrip("\\/"):
            return False

    return True


def filter_safe_paths(
    paths: Iterable[Path | str],
    policy: SafetyPolicy,
) -> list[Path]:
    """从一组路径中筛选出通过安全校验的部分。"""
    safe: list[Path] = []
    for p in paths:
        try:
            path_obj = Path(p)
        except (TypeError, ValueError):
            continue
        if is_safe_to_delete(path_obj, policy):
            safe.append(path_obj)
    return safe


__all__ = [
    "SafetyPolicy",
    "SYSTEM_BLOCKED_DIRS",
    "USER_PERSONAL_SUBDIRS",
    "DEFAULT_SAFE_PATH_TEMPLATES",
    "is_safe_to_delete",
    "filter_safe_paths",
]
