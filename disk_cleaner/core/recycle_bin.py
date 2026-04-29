"""
回收站封装：所有删除统一走 send2trash，禁止永久删除。

================== 安全边界说明 ==================
本模块是唯一允许调用文件系统删除 API 的地方。它强制把文件
移动到 Windows 回收站，绝不直接 ``os.remove`` 或 ``shutil.rmtree``。
即使上游传入了禁止路径，回收站调用也只是失败，不会造成
误删。配合 ``safety.is_safe_to_delete`` 形成双保险。
==================================================
"""

from __future__ import annotations

from pathlib import Path

try:
    from send2trash import send2trash as _send2trash
except ImportError:  # 在缺失依赖的开发环境下也能 import 模块
    _send2trash = None


class RecycleBinError(RuntimeError):
    """回收站调用失败时抛出。"""


def move_to_recycle_bin(path: Path | str) -> None:
    """把文件/目录移到回收站。失败抛出 ``RecycleBinError``。"""
    if _send2trash is None:
        raise RecycleBinError(
            "send2trash 未安装，请先运行: pip install -r requirements.txt"
        )
    try:
        _send2trash(str(path))
    except Exception as exc:  # send2trash 内部异常类型不稳定，统一包装
        raise RecycleBinError(str(exc)) from exc


__all__ = ["move_to_recycle_bin", "RecycleBinError"]
