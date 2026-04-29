"""主窗口：整合磁盘概览、扫描、结果展示、清理流程。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.cleaner import CleanReport
from ..core.disk_info import DiskUsage, get_disk_usage
from ..core.safety import SafetyPolicy
from ..core.scanner import RiskLevel, ScanItem, ScanOptions, ScanResult
from ..utils.logger import get_log_dir, get_logger
from ..utils.size_formatter import format_size
from .workers import CleanWorker, ScanWorker


_RISK_COLORS = {
    RiskLevel.LOW: QColor("#e8f5e9"),
    RiskLevel.MEDIUM: QColor("#fff8e1"),
    RiskLevel.HIGH: QColor("#fff3e0"),
    RiskLevel.FORBIDDEN: QColor("#ffebee"),
}


class MainWindow(QMainWindow):
    """主窗口。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("C 盘空间清理工具")
        self.resize(1080, 720)

        self._policy = SafetyPolicy.build_default()
        self._logger = get_logger()
        self._scan_thread: QThread | None = None
        self._scan_worker: ScanWorker | None = None
        self._clean_thread: QThread | None = None
        self._clean_worker: CleanWorker | None = None
        self._scan_items: list[ScanItem] = []

        self._build_ui()
        self._refresh_disk_overview()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        layout.addWidget(self._build_overview_panel())
        layout.addWidget(self._build_options_panel())
        layout.addWidget(self._build_progress_panel())
        layout.addWidget(self._build_result_table(), stretch=1)
        layout.addWidget(self._build_action_bar())

        self.setCentralWidget(central)
        self._build_menu()

    def _build_menu(self) -> None:
        menubar = self.menuBar()
        help_menu = menubar.addMenu("帮助")

        open_log_action = QAction("打开日志目录", self)
        open_log_action.triggered.connect(self._open_log_dir)
        help_menu.addAction(open_log_action)

        about_action = QAction("关于", self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_overview_panel(self) -> QWidget:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout(frame)

        self._lbl_total = QLabel("总容量: -")
        self._lbl_used = QLabel("已使用: -")
        self._lbl_free = QLabel("可用: -")
        self._lbl_percent = QLabel("使用率: -")
        for lbl in (self._lbl_total, self._lbl_used, self._lbl_free, self._lbl_percent):
            lbl.setStyleSheet("font-size: 14px; padding: 4px 12px;")
            layout.addWidget(lbl)

        self._disk_bar = QProgressBar()
        self._disk_bar.setRange(0, 100)
        self._disk_bar.setFormat("%p%")
        layout.addWidget(self._disk_bar, stretch=1)

        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self._refresh_disk_overview)
        layout.addWidget(refresh_btn)
        return frame

    def _build_options_panel(self) -> QWidget:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        self._chk_user_temp = QCheckBox("用户临时目录 (%TEMP%)")
        self._chk_user_temp.setChecked(True)
        self._chk_win_temp = QCheckBox(r"Windows 临时目录 (C:\Windows\Temp)")
        self._chk_win_temp.setChecked(True)

        layout.addWidget(self._chk_user_temp)
        layout.addWidget(self._chk_win_temp)
        layout.addStretch(1)

        self._btn_scan = QPushButton("开始扫描")
        self._btn_scan.setMinimumWidth(120)
        self._btn_scan.clicked.connect(self._on_scan_clicked)
        layout.addWidget(self._btn_scan)

        self._btn_cancel_scan = QPushButton("取消扫描")
        self._btn_cancel_scan.setEnabled(False)
        self._btn_cancel_scan.clicked.connect(self._on_cancel_scan)
        layout.addWidget(self._btn_cancel_scan)

        return frame

    def _build_progress_panel(self) -> QWidget:
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 0)  # 默认显示忙状态
        self._progress_bar.hide()
        return self._progress_bar

    def _build_result_table(self) -> QWidget:
        wrap = QFrame()
        outer = QVBoxLayout(wrap)
        outer.setContentsMargins(0, 0, 0, 0)

        head = QHBoxLayout()
        self._lbl_summary = QLabel("尚未扫描")
        self._lbl_summary.setStyleSheet("font-size: 13px; padding: 4px;")
        head.addWidget(self._lbl_summary)
        head.addStretch(1)

        self._btn_select_low = QPushButton("仅勾选低风险")
        self._btn_select_low.clicked.connect(lambda: self._set_all_checked(low_only=True))
        head.addWidget(self._btn_select_low)

        self._btn_select_all = QPushButton("全选")
        self._btn_select_all.clicked.connect(lambda: self._set_all_checked(low_only=False))
        head.addWidget(self._btn_select_all)

        self._btn_select_none = QPushButton("全不选")
        self._btn_select_none.clicked.connect(self._clear_all_checked)
        head.addWidget(self._btn_select_none)
        outer.addLayout(head)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["", "路径", "大小", "分类", "风险"])
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.itemDoubleClicked.connect(self._on_row_double_clicked)
        outer.addWidget(self._table)
        return wrap

    def _build_action_bar(self) -> QWidget:
        frame = QFrame()
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        self._lbl_status = QLabel("就绪")
        layout.addWidget(self._lbl_status)
        layout.addStretch(1)

        self._btn_open_dir = QPushButton("打开所选文件目录")
        self._btn_open_dir.clicked.connect(self._open_selected_dir)
        layout.addWidget(self._btn_open_dir)

        self._btn_clean = QPushButton("清理勾选项")
        self._btn_clean.setEnabled(False)
        self._btn_clean.setStyleSheet(
            "background-color: #1976d2; color: white; padding: 6px 16px;"
        )
        self._btn_clean.clicked.connect(self._on_clean_clicked)
        layout.addWidget(self._btn_clean)

        return frame

    # ------------------------------------------------------------------
    # 磁盘概览
    # ------------------------------------------------------------------
    def _refresh_disk_overview(self) -> None:
        usage: DiskUsage = get_disk_usage("C:\\")
        self._lbl_total.setText(f"总容量: {format_size(usage.total)}")
        self._lbl_used.setText(f"已使用: {format_size(usage.used)}")
        self._lbl_free.setText(f"可用: {format_size(usage.free)}")
        self._lbl_percent.setText(f"使用率: {usage.percent:.1f}%")
        self._disk_bar.setRange(0, 100)
        self._disk_bar.setValue(int(usage.percent))

    # ------------------------------------------------------------------
    # 扫描流程
    # ------------------------------------------------------------------
    def _on_scan_clicked(self) -> None:
        if self._scan_thread is not None:
            return
        if not (self._chk_user_temp.isChecked() or self._chk_win_temp.isChecked()):
            QMessageBox.warning(self, "提示", "请至少勾选一项扫描范围")
            return

        options = ScanOptions(
            scan_user_temp=self._chk_user_temp.isChecked(),
            scan_windows_temp=self._chk_win_temp.isChecked(),
        )

        self._table.setRowCount(0)
        self._scan_items = []
        self._lbl_summary.setText("正在扫描...")
        self._set_busy(True, scanning=True)
        self._progress_bar.setRange(0, 0)
        self._progress_bar.show()

        self._scan_worker = ScanWorker(self._policy, options)
        self._scan_thread = QThread(self)
        self._scan_worker.moveToThread(self._scan_thread)
        self._scan_thread.started.connect(self._scan_worker.run)
        self._scan_worker.progress.connect(self._on_scan_progress)
        self._scan_worker.finished.connect(self._on_scan_finished)
        self._scan_worker.failed.connect(self._on_scan_failed)
        self._scan_worker.finished.connect(self._scan_thread.quit)
        self._scan_worker.failed.connect(self._scan_thread.quit)
        self._scan_thread.finished.connect(self._cleanup_scan_thread)
        self._scan_thread.start()

    def _on_cancel_scan(self) -> None:
        if self._scan_worker is not None:
            self._scan_worker.cancel()
            self._lbl_status.setText("正在取消扫描...")

    def _on_scan_progress(self, count: int, current: str) -> None:
        self._lbl_status.setText(f"已扫描 {count} 个文件: {self._shorten(current)}")

    def _on_scan_finished(self, result: ScanResult) -> None:
        self._scan_items = result.items
        self._populate_table(result.items)
        elapsed = max(0.0, result.finished_at - result.started_at)
        self._lbl_summary.setText(
            f"命中 {len(result.items)} 个文件 / 跳过 {result.skipped_files} 个 / "
            f"可释放 {format_size(result.releasable_size)} / "
            f"低风险 {format_size(result.low_risk_size)} / 耗时 {elapsed:.1f}s"
        )
        self._lbl_status.setText("扫描完成")
        self._progress_bar.hide()
        self._set_busy(False, scanning=True)
        self._btn_clean.setEnabled(bool(result.items))

    def _on_scan_failed(self, msg: str) -> None:
        self._progress_bar.hide()
        self._set_busy(False, scanning=True)
        self._lbl_status.setText("扫描失败")
        QMessageBox.critical(self, "扫描失败", msg)

    def _cleanup_scan_thread(self) -> None:
        if self._scan_thread is not None:
            self._scan_thread.deleteLater()
        self._scan_thread = None
        self._scan_worker = None

    # ------------------------------------------------------------------
    # 表格相关
    # ------------------------------------------------------------------
    def _populate_table(self, items: list[ScanItem]) -> None:
        self._table.setRowCount(len(items))
        for row, item in enumerate(items):
            chk_item = QTableWidgetItem()
            chk_item.setFlags(
                Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable
            )
            chk_item.setCheckState(
                Qt.Checked if item.selected_by_default else Qt.Unchecked
            )
            self._table.setItem(row, 0, chk_item)

            path_item = QTableWidgetItem(str(item.path))
            path_item.setData(Qt.UserRole, str(item.path))
            self._table.setItem(row, 1, path_item)
            self._table.setItem(row, 2, QTableWidgetItem(format_size(item.size)))
            self._table.setItem(row, 3, QTableWidgetItem(item.category.value))
            self._table.setItem(row, 4, QTableWidgetItem(item.risk.value))

            color = _RISK_COLORS.get(item.risk)
            if color is not None:
                for col in range(self._table.columnCount()):
                    cell = self._table.item(row, col)
                    if cell is not None:
                        cell.setBackground(color)

    def _set_all_checked(self, *, low_only: bool) -> None:
        for row, item in enumerate(self._scan_items):
            cell = self._table.item(row, 0)
            if cell is None:
                continue
            if low_only:
                cell.setCheckState(
                    Qt.Checked if item.risk == RiskLevel.LOW else Qt.Unchecked
                )
            else:
                cell.setCheckState(Qt.Checked)

    def _clear_all_checked(self) -> None:
        for row in range(self._table.rowCount()):
            cell = self._table.item(row, 0)
            if cell is not None:
                cell.setCheckState(Qt.Unchecked)

    def _checked_paths(self) -> list[Path]:
        result: list[Path] = []
        for row, item in enumerate(self._scan_items):
            cell = self._table.item(row, 0)
            if cell is not None and cell.checkState() == Qt.Checked:
                result.append(item.path)
        return result

    def _on_row_double_clicked(self, _item) -> None:
        self._open_selected_dir()

    def _open_selected_dir(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        if row < 0 or row >= len(self._scan_items):
            return
        path = self._scan_items[row].path
        self._open_in_explorer(path.parent)

    def _open_in_explorer(self, directory: Path) -> None:
        try:
            if sys.platform == "win32":
                os.startfile(str(directory))  # type: ignore[attr-defined]
            else:
                subprocess.Popen(["xdg-open", str(directory)])
        except OSError as exc:
            QMessageBox.warning(self, "无法打开目录", str(exc))

    # ------------------------------------------------------------------
    # 清理流程
    # ------------------------------------------------------------------
    def _on_clean_clicked(self) -> None:
        paths = self._checked_paths()
        if not paths:
            QMessageBox.information(self, "提示", "请先勾选要清理的文件")
            return

        total_size = 0
        for row, item in enumerate(self._scan_items):
            cell = self._table.item(row, 0)
            if cell is not None and cell.checkState() == Qt.Checked:
                total_size += item.size

        msg = (
            f"即将清理 {len(paths):,} 个文件，预计释放 {format_size(total_size)} 空间。\n\n"
            "默认会将文件移动到 Windows 回收站，可在回收站中恢复。\n\n"
            "提醒：\n"
            "• 已通过白名单 + 黑名单双重校验\n"
            "• 系统目录、个人文件不会被清理\n"
            "• 失败的文件会保留并展示原因\n\n"
            "是否继续？"
        )
        reply = QMessageBox.question(
            self,
            "确认清理",
            msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self._lbl_status.setText("正在清理...")
        self._progress_bar.setRange(0, len(paths))
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._set_busy(True, scanning=False)

        self._clean_worker = CleanWorker(self._policy, paths)
        self._clean_thread = QThread(self)
        self._clean_worker.moveToThread(self._clean_thread)
        self._clean_thread.started.connect(self._clean_worker.run)
        self._clean_worker.progress.connect(self._on_clean_progress)
        self._clean_worker.finished.connect(self._on_clean_finished)
        self._clean_worker.failed.connect(self._on_clean_failed)
        self._clean_worker.finished.connect(self._clean_thread.quit)
        self._clean_worker.failed.connect(self._clean_thread.quit)
        self._clean_thread.finished.connect(self._cleanup_clean_thread)
        self._clean_thread.start()

    def _on_clean_progress(self, idx: int, total: int, current: str, freed: int) -> None:
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(idx)
        self._lbl_status.setText(
            f"清理中 {idx}/{total}, 已释放 {format_size(freed)}: {self._shorten(current)}"
        )

    def _on_clean_finished(self, report: CleanReport) -> None:
        self._progress_bar.hide()
        self._set_busy(False, scanning=False)
        self._lbl_status.setText("清理完成")
        self._show_report_dialog(report)
        self._refresh_disk_overview()

    def _on_clean_failed(self, msg: str) -> None:
        self._progress_bar.hide()
        self._set_busy(False, scanning=False)
        QMessageBox.critical(self, "清理失败", msg)

    def _cleanup_clean_thread(self) -> None:
        if self._clean_thread is not None:
            self._clean_thread.deleteLater()
        self._clean_thread = None
        self._clean_worker = None

    def _show_report_dialog(self, report: CleanReport) -> None:
        elapsed = max(0.0, report.finished_at - report.started_at)
        lines = [
            f"实际释放空间: {format_size(report.freed_bytes)}",
            f"成功清理: {report.succeeded_count} 个文件",
            f"失败: {len(report.failed)} 个文件",
            f"安全校验跳过: {len(report.skipped_unsafe)} 个",
            f"耗时: {elapsed:.1f}s",
        ]
        if report.failed:
            lines.append("")
            lines.append("失败示例:")
            for f in report.failed[:10]:
                lines.append(f"  - {f.path}: {f.reason}")
            if len(report.failed) > 10:
                lines.append(f"  ... 共 {len(report.failed)} 项, 详见日志")

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Information)
        box.setWindowTitle("清理完成")
        box.setText("\n".join(lines))
        view_log_btn = box.addButton("查看日志", QMessageBox.ActionRole)
        box.addButton("确定", QMessageBox.AcceptRole)
        box.exec()
        if box.clickedButton() is view_log_btn:
            self._open_log_dir()

    # ------------------------------------------------------------------
    # 通用辅助
    # ------------------------------------------------------------------
    def _set_busy(self, busy: bool, *, scanning: bool) -> None:
        self._btn_scan.setEnabled(not busy)
        self._btn_clean.setEnabled(not busy and bool(self._scan_items))
        self._btn_cancel_scan.setEnabled(busy and scanning)
        self._chk_user_temp.setEnabled(not busy)
        self._chk_win_temp.setEnabled(not busy)

    def _open_log_dir(self) -> None:
        log_dir = get_log_dir()
        self._open_in_explorer(log_dir)

    def _show_about(self) -> None:
        QMessageBox.information(
            self,
            "关于",
            "C 盘空间清理工具\n\n"
            "安全优先：白名单 + 黑名单双重校验\n"
            "默认仅清理临时目录，移动到回收站可恢复\n"
            "系统目录、Program Files、个人文件永远不会被删除",
        )

    @staticmethod
    def _shorten(text: str, limit: int = 80) -> str:
        if len(text) <= limit:
            return text
        return "..." + text[-(limit - 3):]


__all__ = ["MainWindow"]
