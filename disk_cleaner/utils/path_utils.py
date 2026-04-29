"""路径工具：环境变量展开、安全规范化等。"""

from __future__ import annotations

import os
from pathlib import Path


def expand_path(template: str) -> Path | None:
    """展开包含环境变量的路径模板。无法展开时返回 None。"""
    if not template:
        return None
    try:
        expanded = os.path.expandvars(template)
        if "%" in expanded:
            return None
        return Path(expanded).resolve(strict=False)
    except (OSError, ValueError):
        return None


def safe_iter_files(root: Path, follow_symlinks: bool = False):
    """递归遍历目录下的文件，跳过权限错误，永不跟随符号链接(默认)。

    安全说明：默认 ``follow_symlinks=False``，避免被符号链接
    引导到白名单之外的目录。
    """
    if not root.exists():
        return
    try:
        for entry in os.scandir(root):
            try:
                if entry.is_symlink() and not follow_symlinks:
                    continue
                if entry.is_dir(follow_symlinks=follow_symlinks):
                    yield from safe_iter_files(Path(entry.path), follow_symlinks)
                elif entry.is_file(follow_symlinks=follow_symlinks):
                    yield Path(entry.path)
            except (PermissionError, OSError):
                continue
    except (PermissionError, OSError):
        return


__all__ = ["expand_path", "safe_iter_files"]
