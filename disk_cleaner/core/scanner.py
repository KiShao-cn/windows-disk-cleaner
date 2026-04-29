"""
扫描模块：在白名单目录下收集可清理文件并打风险等级标签。

================== 安全边界说明 ==================
扫描模块只负责"发现"，不负责"删除"。但所有被发现的文件
都必须在 ``Scanner`` 内部经过安全校验，未通过的文件不会
出现在扫描结果中，从而避免任何危险路径流入下游。
==================================================
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

from .safety import SafetyPolicy, is_safe_to_delete
from ..utils.logger import get_logger
from ..utils.path_utils import safe_iter_files


class RiskLevel(str, Enum):
    """风险等级，对应需求文档第 8 节。"""

    LOW = "低风险"
    MEDIUM = "中风险"
    HIGH = "高风险"
    FORBIDDEN = "禁止"


class FileCategory(str, Enum):
    """文件分类，对应需求文档第 3.3 节。"""

    USER_TEMP = "用户临时文件"
    WINDOWS_TEMP = "Windows 临时文件"
    LOG = "日志文件"
    DUMP = "崩溃转储"
    BACKUP = "备份文件"
    OTHER = "其他"


# 仅在白名单目录内扫描的文件后缀（需求第 3.2 节）
_LOG_LIKE_EXTENSIONS = {".log", ".tmp", ".dmp", ".bak", ".old"}


@dataclass(frozen=True)
class ScanItem:
    """扫描出的单个候选文件。"""

    path: Path
    size: int
    mtime: float
    category: FileCategory
    risk: RiskLevel
    selected_by_default: bool


@dataclass
class ScanResult:
    """扫描结果汇总。"""

    items: list[ScanItem] = field(default_factory=list)
    scanned_files: int = 0
    skipped_files: int = 0
    total_size: int = 0
    started_at: float = 0.0
    finished_at: float = 0.0
    scanned_roots: list[Path] = field(default_factory=list)

    @property
    def releasable_size(self) -> int:
        """所有候选项目的大小总和（即可释放空间预估）。"""
        return sum(item.size for item in self.items)

    @property
    def low_risk_size(self) -> int:
        """默认勾选项的大小总和。"""
        return sum(item.size for item in self.items if item.selected_by_default)


@dataclass
class ScanOptions:
    """扫描选项。"""

    scan_user_temp: bool = True
    scan_windows_temp: bool = True
    recent_file_skip_hours: int = 24
    include_extensions: tuple[str, ...] = tuple(_LOG_LIKE_EXTENSIONS)


# 进度回调签名：(已扫描文件数, 当前文件路径)
ProgressCallback = Callable[[int, str], None]
# 取消标志签名：返回 True 表示需要中止扫描
CancelChecker = Callable[[], bool]


class Scanner:
    """安全扫描器。"""

    def __init__(self, policy: SafetyPolicy, options: ScanOptions | None = None):
        self.policy = policy
        self.options = options or ScanOptions()
        self._logger = get_logger()

    # ------------------------------------------------------------------
    # 公共入口
    # ------------------------------------------------------------------
    def scan(
        self,
        progress_cb: ProgressCallback | None = None,
        cancel_checker: CancelChecker | None = None,
    ) -> ScanResult:
        """执行扫描，返回结果。任何异常都会被吞掉并记录日志。"""
        result = ScanResult(started_at=time.time())
        roots = self._collect_scan_roots()
        result.scanned_roots = list(roots)

        self._logger.info("扫描开始，根目录数=%d", len(roots))
        for root in roots:
            if cancel_checker and cancel_checker():
                self._logger.info("扫描被用户取消")
                break
            self._scan_one_root(root, result, progress_cb, cancel_checker)

        result.finished_at = time.time()
        result.total_size = result.releasable_size
        self._logger.info(
            "扫描结束，命中=%d，跳过=%d，可释放=%d 字节",
            len(result.items),
            result.skipped_files,
            result.total_size,
        )
        return result

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------
    def _collect_scan_roots(self) -> list[Path]:
        """根据扫描选项与白名单交集得到本次扫描的根目录。"""
        roots: list[Path] = []
        for root in self.policy.safe_roots:
            root_str = str(root).lower()
            is_windows_temp = root_str.startswith(r"c:\windows\temp".lower())
            if is_windows_temp and not self.options.scan_windows_temp:
                continue
            if not is_windows_temp and not self.options.scan_user_temp:
                continue
            if root.exists():
                roots.append(root)
        return roots

    def _scan_one_root(
        self,
        root: Path,
        result: ScanResult,
        progress_cb: ProgressCallback | None,
        cancel_checker: CancelChecker | None,
    ) -> None:
        """扫描单个根目录。"""
        for file_path in safe_iter_files(root, follow_symlinks=False):
            if cancel_checker and cancel_checker():
                return
            result.scanned_files += 1

            if progress_cb is not None and result.scanned_files % 50 == 0:
                try:
                    progress_cb(result.scanned_files, str(file_path))
                except Exception:  # 进度回调异常绝不能中断扫描
                    pass

            item = self._evaluate_file(file_path, root)
            if item is None:
                result.skipped_files += 1
                continue
            result.items.append(item)

    def _evaluate_file(self, file_path: Path, root: Path) -> ScanItem | None:
        """对单个文件做安全校验与分类，未通过则返回 None。"""
        try:
            stat = file_path.stat()
        except (OSError, PermissionError):
            return None

        # 安全校验：防止符号链接等异常情况意外通过
        if not is_safe_to_delete(file_path, self.policy):
            return None

        # 跳过最近修改的文件，对应需求 3.2 / 7.2
        if self._is_recently_modified(stat.st_mtime):
            return None

        # 跳过 0 字节文件意义不大，但仍然保留以便用户查看
        category = self._classify(file_path, root)
        risk = self._risk_of(category, stat.st_size)
        selected = risk == RiskLevel.LOW

        return ScanItem(
            path=file_path,
            size=stat.st_size,
            mtime=stat.st_mtime,
            category=category,
            risk=risk,
            selected_by_default=selected,
        )

    def _is_recently_modified(self, mtime: float) -> bool:
        cutoff = time.time() - self.options.recent_file_skip_hours * 3600
        return mtime > cutoff

    def _classify(self, file_path: Path, root: Path) -> FileCategory:
        """按文件后缀和所在根目录决定分类。"""
        ext = file_path.suffix.lower()
        root_str = str(root).lower()
        if ext == ".log":
            return FileCategory.LOG
        if ext == ".dmp":
            return FileCategory.DUMP
        if ext in {".bak", ".old"}:
            return FileCategory.BACKUP
        if root_str.startswith(r"c:\windows\temp".lower()):
            return FileCategory.WINDOWS_TEMP
        return FileCategory.USER_TEMP

    def _risk_of(self, category: FileCategory, size: int) -> RiskLevel:
        """根据分类决定风险等级。"""
        if category in (FileCategory.USER_TEMP, FileCategory.WINDOWS_TEMP):
            return RiskLevel.LOW
        if category in (FileCategory.LOG, FileCategory.DUMP, FileCategory.BACKUP):
            return RiskLevel.MEDIUM
        return RiskLevel.MEDIUM


__all__ = [
    "Scanner",
    "ScanOptions",
    "ScanResult",
    "ScanItem",
    "RiskLevel",
    "FileCategory",
]
