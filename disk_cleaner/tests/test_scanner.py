"""扫描模块单元测试。"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from disk_cleaner.core.safety import SafetyPolicy  # noqa: E402
from disk_cleaner.core.scanner import (  # noqa: E402
    FileCategory,
    RiskLevel,
    ScanOptions,
    Scanner,
)


class ScannerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.policy = SafetyPolicy(safe_roots=(self.root,), blocked_roots=())

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_old_file(self, relpath: str, size: int = 100) -> Path:
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        # 修改时间设为 2 天前以绕过 24 小时的最近修改过滤
        old = time.time() - 48 * 3600
        os.utime(path, (old, old))
        return path

    def test_scan_finds_old_files(self):
        self._make_old_file("a.tmp")
        self._make_old_file("sub/b.log")
        scanner = Scanner(self.policy, ScanOptions())
        result = scanner.scan()
        paths = {item.path for item in result.items}
        self.assertEqual(len(paths), 2)
        self.assertEqual(result.releasable_size, 200)

    def test_recent_files_are_skipped(self):
        recent = self.root / "recent.tmp"
        recent.write_bytes(b"y" * 50)  # 当前时间 mtime
        scanner = Scanner(self.policy, ScanOptions(recent_file_skip_hours=24))
        result = scanner.scan()
        self.assertEqual([item.path for item in result.items], [])

    def test_classification_and_risk(self):
        log = self._make_old_file("x.log")
        tmp = self._make_old_file("y.tmp")
        scanner = Scanner(self.policy, ScanOptions())
        result = scanner.scan()
        by_path = {item.path: item for item in result.items}
        self.assertEqual(by_path[log].category, FileCategory.LOG)
        self.assertEqual(by_path[log].risk, RiskLevel.MEDIUM)
        self.assertFalse(by_path[log].selected_by_default)
        self.assertEqual(by_path[tmp].risk, RiskLevel.LOW)
        self.assertTrue(by_path[tmp].selected_by_default)

    def test_cancel_short_circuits(self):
        for i in range(5):
            self._make_old_file(f"f{i}.tmp")
        scanner = Scanner(self.policy, ScanOptions())
        result = scanner.scan(cancel_checker=lambda: True)
        # 取消时不应有结果
        self.assertEqual(result.items, [])


if __name__ == "__main__":
    unittest.main()
