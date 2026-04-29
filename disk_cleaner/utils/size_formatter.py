"""文件大小格式化工具。"""

from __future__ import annotations

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def format_size(num_bytes: int | float) -> str:
    """将字节数格式化为带单位的可读字符串。"""
    if num_bytes is None:
        return "0 B"
    try:
        size = float(num_bytes)
    except (TypeError, ValueError):
        return "0 B"
    if size < 0:
        size = 0.0
    idx = 0
    while size >= 1024 and idx < len(_UNITS) - 1:
        size /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(size)} {_UNITS[idx]}"
    return f"{size:.2f} {_UNITS[idx]}"


__all__ = ["format_size"]
