"""清理模块单元测试。

为避免真实回收站副作用，使用 monkeypatch 替换 ``move_to_recycle_bin``。
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from disk_cleaner.core import cleaner as cleaner_module  # noqa: E402
from disk_cleaner.core.cleaner import Cleaner  # noqa: E402
from disk_cleaner.core.safety import SafetyPolicy  # noqa: E402


class CleanerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self.policy = SafetyPolicy(safe_roots=(self.root,), blocked_roots=())
        self.deleted: list[str] = []

        def fake_recycle(p):
            self.deleted.append(str(p))
            os.remove(p)

        self._patch = mock.patch.object(
            cleaner_module, "move_to_recycle_bin", side_effect=fake_recycle
        )
        self._patch.start()

    def tearDown(self) -> None:
        self._patch.stop()
        self._tmp.cleanup()

    def _make_file(self, name: str, size: int = 100, age_hours: int = 48) -> Path:
        path = self.root / name
        path.write_bytes(b"x" * size)
        old = time.time() - age_hours * 3600
        os.utime(path, (old, old))
        return path

    def test_clean_safe_files(self):
        f1 = self._make_file("a.tmp")
        f2 = self._make_file("b.tmp", size=200)
        cleaner = Cleaner(self.policy)
        report = cleaner.clean([f1, f2])
        self.assertEqual(report.succeeded_count, 2)
        self.assertEqual(report.freed_bytes, 300)
        self.assertEqual(report.failed, [])
        self.assertEqual(len(self.deleted), 2)

    def test_clean_rejects_unsafe_path(self):
        # 构造一个白名单外的临时文件
        with tempfile.NamedTemporaryFile(delete=False) as f:
            outside = Path(f.name)
        try:
            cleaner = Cleaner(self.policy)
            report = cleaner.clean([outside])
            self.assertEqual(report.succeeded_count, 0)
            self.assertEqual(len(report.skipped_unsafe), 1)
            # 文件应仍然存在 - 双重保险有效
            self.assertTrue(outside.exists())
        finally:
            try:
                outside.unlink()
            except OSError:
                pass

    def test_clean_collects_failures(self):
        f1 = self._make_file("a.tmp")

        def boom(_p):
            raise cleaner_module.RecycleBinError("simulated")

        with mock.patch.object(cleaner_module, "move_to_recycle_bin", side_effect=boom):
            cleaner = Cleaner(self.policy)
            report = cleaner.clean([f1])
        self.assertEqual(report.succeeded_count, 0)
        self.assertEqual(len(report.failed), 1)
        self.assertIn("simulated", report.failed[0].reason)

    def test_cancel_stops_processing(self):
        f1 = self._make_file("a.tmp")
        f2 = self._make_file("b.tmp")
        cleaner = Cleaner(self.policy)

        # 第一次调用就要求取消，应该一个都不删
        report = cleaner.clean([f1, f2], cancel_checker=lambda: True)
        self.assertEqual(report.succeeded_count, 0)


if __name__ == "__main__":
    unittest.main()
