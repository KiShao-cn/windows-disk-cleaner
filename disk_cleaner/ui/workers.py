"""Qt 后台 Worker：把扫描和清理放到独立线程，避免阻塞 UI。"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PySide6.QtCore import QObject, QThread, Signal

from ..core.cleaner import CleanReport, Cleaner
from ..core.safety import SafetyPolicy
from ..core.scanner import ScanOptions, ScanResult, Scanner


class ScanWorker(QObject):
    """扫描 Worker。在独立线程中执行 Scanner.scan。"""

    progress = Signal(int, str)
    finished = Signal(object)  # ScanResult
    failed = Signal(str)

    def __init__(self, policy: SafetyPolicy, options: ScanOptions):
        super().__init__()
        self._policy = policy
        self._options = options
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            scanner = Scanner(self._policy, self._options)
            result: ScanResult = scanner.scan(
                progress_cb=self._emit_progress,
                cancel_checker=lambda: self._cancel,
            )
            self.finished.emit(result)
        except Exception as exc:  # 任何意外都通过信号上报，不让线程崩溃
            self.failed.emit(str(exc))

    def _emit_progress(self, count: int, current: str) -> None:
        self.progress.emit(count, current)


class CleanWorker(QObject):
    """清理 Worker。"""

    progress = Signal(int, int, str, int)  # idx, total, current, freed_bytes
    finished = Signal(object)  # CleanReport
    failed = Signal(str)

    def __init__(self, policy: SafetyPolicy, paths: Iterable[Path]):
        super().__init__()
        self._policy = policy
        self._paths = list(paths)
        self._cancel = False

    def cancel(self) -> None:
        self._cancel = True

    def run(self) -> None:
        try:
            cleaner = Cleaner(self._policy)
            report: CleanReport = cleaner.clean(
                self._paths,
                progress_cb=self._emit_progress,
                cancel_checker=lambda: self._cancel,
            )
            self.finished.emit(report)
        except Exception as exc:
            self.failed.emit(str(exc))

    def _emit_progress(self, idx: int, total: int, current: str, freed: int) -> None:
        self.progress.emit(idx, total, current, freed)


def run_in_thread(worker: QObject) -> QThread:
    """把一个 Worker 放进新线程并启动，返回 QThread 句柄。"""
    thread = QThread()
    worker.moveToThread(thread)
    thread.started.connect(worker.run)  # type: ignore[attr-defined]
    return thread


__all__ = ["ScanWorker", "CleanWorker", "run_in_thread"]
