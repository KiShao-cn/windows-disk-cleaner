"""
清理模块：在用户确认后将文件移至回收站。

================== 安全边界说明 ==================
本模块是删除流程的最后一道安全闸门。即便上游传入"恶意"路径，
本模块也会再次调用 ``is_safe_to_delete`` 校验；不通过即跳过
并记录日志。删除一律通过 ``recycle_bin.move_to_recycle_bin``，
绝不调用任何系统命令行删除指令。
==================================================
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from .recycle_bin import RecycleBinError, move_to_recycle_bin
from .safety import SafetyPolicy, is_safe_to_delete
from ..utils.logger import get_logger


@dataclass
class CleanFailure:
    """单个清理失败的记录。"""

    path: Path
    reason: str


@dataclass
class CleanReport:
    """清理结果汇总。"""

    succeeded_count: int = 0
    failed: list[CleanFailure] = field(default_factory=list)
    skipped_unsafe: list[Path] = field(default_factory=list)
    freed_bytes: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0


# 进度回调签名：(已处理数, 总数, 当前路径, 已释放字节)
CleanProgressCallback = Callable[[int, int, str, int], None]
CleanCancelChecker = Callable[[], bool]


class Cleaner:
    """安全清理器：默认仅移动到回收站。"""

    def __init__(self, policy: SafetyPolicy):
        self.policy = policy
        self._logger = get_logger()

    def clean(
        self,
        paths: Iterable[Path | str],
        *,
        progress_cb: CleanProgressCallback | None = None,
        cancel_checker: CleanCancelChecker | None = None,
    ) -> CleanReport:
        """对一组路径执行清理。永远不抛异常，所有失败被收集。"""
        report = CleanReport(started_at=time.time())
        path_list: list[Path] = []
        for p in paths:
            try:
                path_list.append(Path(p))
            except (TypeError, ValueError):
                continue
        total = len(path_list)
        self._logger.info("清理开始，候选数=%d", total)

        for idx, path in enumerate(path_list, start=1):
            if cancel_checker and cancel_checker():
                self._logger.info("清理被用户取消，已处理 %d/%d", idx - 1, total)
                break

            # 安全双重校验：上游可能没有再次校验，本模块必须自检
            if not is_safe_to_delete(path, self.policy):
                report.skipped_unsafe.append(path)
                self._logger.warning("安全校验未通过，跳过: %s", path)
                self._notify(progress_cb, idx, total, str(path), report.freed_bytes)
                continue

            size = self._safe_size(path)
            try:
                move_to_recycle_bin(path)
                report.succeeded_count += 1
                report.freed_bytes += size
                self._logger.info("已移至回收站: %s (%d bytes)", path, size)
            except RecycleBinError as exc:
                report.failed.append(CleanFailure(path=path, reason=str(exc)))
                self._logger.error("回收站调用失败: %s, 原因: %s", path, exc)
            except (PermissionError, OSError) as exc:
                report.failed.append(CleanFailure(path=path, reason=str(exc)))
                self._logger.error("删除失败: %s, 原因: %s", path, exc)
            except Exception as exc:  # 兜底：绝不让异常向上传导导致整体失败
                report.failed.append(CleanFailure(path=path, reason=repr(exc)))
                self._logger.exception("未知错误: %s", path)

            self._notify(progress_cb, idx, total, str(path), report.freed_bytes)

        report.finished_at = time.time()
        self._logger.info(
            "清理结束，成功=%d，失败=%d，跳过=%d，释放=%d 字节",
            report.succeeded_count,
            len(report.failed),
            len(report.skipped_unsafe),
            report.freed_bytes,
        )
        return report

    @staticmethod
    def _safe_size(path: Path) -> int:
        try:
            return path.stat().st_size
        except (OSError, PermissionError):
            return 0

    @staticmethod
    def _notify(
        cb: CleanProgressCallback | None,
        idx: int,
        total: int,
        current: str,
        freed: int,
    ) -> None:
        if cb is None:
            return
        try:
            cb(idx, total, current, freed)
        except Exception:
            # 进度回调异常绝不能中断清理
            pass


__all__ = ["Cleaner", "CleanReport", "CleanFailure"]
