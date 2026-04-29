"""磁盘信息模块：获取 C 盘容量信息，用于首页概览。"""

from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass(frozen=True)
class DiskUsage:
    """磁盘使用情况快照。"""

    total: int
    used: int
    free: int

    @property
    def percent(self) -> float:
        """已用百分比，范围 0~100。"""
        if self.total <= 0:
            return 0.0
        return round(self.used * 100.0 / self.total, 2)


def get_disk_usage(drive: str = "C:\\") -> DiskUsage:
    """返回指定盘符的磁盘使用情况。失败时返回全 0。"""
    try:
        usage = shutil.disk_usage(drive)
        return DiskUsage(total=usage.total, used=usage.used, free=usage.free)
    except (OSError, ValueError):
        return DiskUsage(total=0, used=0, free=0)


__all__ = ["DiskUsage", "get_disk_usage"]
