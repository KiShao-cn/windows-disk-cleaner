"""安全模块单元测试 - 这是项目最关键的测试集。

任何测试失败都意味着安全边界被破坏，必须立即修复。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from disk_cleaner.core.safety import (  # noqa: E402
    SafetyPolicy,
    is_safe_to_delete,
)


class SafetyTestCase(unittest.TestCase):
    """安全校验测试。"""

    def setUp(self) -> None:
        # 构造一个临时目录作为白名单
        self._tmp = tempfile.TemporaryDirectory()
        self.safe_root = Path(self._tmp.name).resolve()
        self.policy = SafetyPolicy(
            safe_roots=(self.safe_root,),
            blocked_roots=(
                Path(r"C:\Windows\System32"),
                Path(r"C:\Program Files"),
            ),
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    # ------------------------------------------------------------------
    # 正常情况
    # ------------------------------------------------------------------
    def test_file_inside_whitelist_is_safe(self):
        target = self.safe_root / "a.tmp"
        target.write_text("x")
        self.assertTrue(is_safe_to_delete(target, self.policy))

    def test_file_in_subdir_of_whitelist_is_safe(self):
        sub = self.safe_root / "sub" / "deep"
        sub.mkdir(parents=True)
        target = sub / "b.log"
        target.write_text("x")
        self.assertTrue(is_safe_to_delete(target, self.policy))

    # ------------------------------------------------------------------
    # 黑名单一票否决
    # ------------------------------------------------------------------
    def test_system_path_is_blocked(self):
        blocked = Path(r"C:\Windows\System32\drivers\etc\hosts")
        self.assertFalse(is_safe_to_delete(blocked, self.policy))

    def test_program_files_is_blocked(self):
        blocked = Path(r"C:\Program Files\some_app\app.exe")
        self.assertFalse(is_safe_to_delete(blocked, self.policy))

    def test_blocked_takes_precedence_over_whitelist(self):
        # 同时配置：白名单包含一个目录，黑名单也包含其子目录
        sub = self.safe_root / "sensitive"
        sub.mkdir()
        target = sub / "x.tmp"
        target.write_text("x")
        policy = SafetyPolicy(
            safe_roots=(self.safe_root,),
            blocked_roots=(sub,),
        )
        self.assertFalse(is_safe_to_delete(target, policy))

    # ------------------------------------------------------------------
    # 白名单外
    # ------------------------------------------------------------------
    def test_path_outside_whitelist_is_rejected(self):
        outside = Path(tempfile.gettempdir()) / "dc_outside.tmp"
        outside.write_text("x")
        try:
            policy = SafetyPolicy(
                safe_roots=(self.safe_root,),
                blocked_roots=(),
            )
            self.assertFalse(is_safe_to_delete(outside, policy))
        finally:
            try:
                outside.unlink()
            except OSError:
                pass

    def test_whitelist_root_itself_cannot_be_deleted(self):
        # 不允许删除白名单根目录本身，仅允许其内部文件
        self.assertFalse(is_safe_to_delete(self.safe_root, self.policy))

    # ------------------------------------------------------------------
    # 路径穿越
    # ------------------------------------------------------------------
    def test_path_traversal_is_rejected(self):
        # 制造一个看似在白名单内、实际指向外部的路径
        evil = self.safe_root / ".." / "evil.tmp"
        # 即使没有真实文件也要求被拒绝
        self.assertFalse(is_safe_to_delete(evil, self.policy))

    # ------------------------------------------------------------------
    # 默认策略
    # ------------------------------------------------------------------
    def test_default_policy_blocks_system_paths(self):
        policy = SafetyPolicy.build_default()
        self.assertFalse(
            is_safe_to_delete(r"C:\Windows\System32\drivers\etc\hosts", policy)
        )

    def test_default_policy_blocks_user_documents(self):
        user_profile = os.environ.get("USERPROFILE")
        if not user_profile:
            self.skipTest("No USERPROFILE in env")
        policy = SafetyPolicy.build_default()
        self.assertFalse(
            is_safe_to_delete(Path(user_profile) / "Documents" / "x.txt", policy)
        )
        self.assertFalse(
            is_safe_to_delete(Path(user_profile) / "Desktop" / "x.txt", policy)
        )
        self.assertFalse(
            is_safe_to_delete(Path(user_profile) / "Downloads" / "x.txt", policy)
        )

    def test_default_policy_allows_user_temp(self):
        policy = SafetyPolicy.build_default()
        temp = os.environ.get("TEMP")
        if not temp:
            self.skipTest("No TEMP in env")
        candidate = Path(temp) / "diskcleaner_test_dummy.tmp"
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text("x")
        try:
            self.assertTrue(is_safe_to_delete(candidate, policy))
        finally:
            try:
                candidate.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
