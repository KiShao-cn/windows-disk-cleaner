"""日志工具：统一记录扫描与清理的全过程。

日志默认写入 ``%LOCALAPPDATA%\\DiskCleaner\\logs`` 目录，
按日期切分文件，方便用户事后审计删除行为。
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOGGER_NAME = "disk_cleaner"
_DEFAULT_LOG_DIR_TEMPLATE = r"%LOCALAPPDATA%\DiskCleaner\logs"


def _resolve_log_dir(template: str | None = None) -> Path:
    """根据模板返回日志目录，必要时创建。"""
    template = template or _DEFAULT_LOG_DIR_TEMPLATE
    expanded = os.path.expandvars(template)
    if "%" in expanded:
        expanded = str(Path.home() / "DiskCleaner" / "logs")
    log_dir = Path(expanded)
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        log_dir = Path.home() / "DiskCleaner" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def get_logger(log_dir_template: str | None = None) -> logging.Logger:
    """返回全局共享的 logger，幂等。"""
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    log_dir = _resolve_log_dir(log_dir_template)
    log_path = log_dir / "disk_cleaner.log"

    try:
        file_handler = RotatingFileHandler(
            log_path, maxBytes=2 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
    except OSError:
        # 写文件失败时退化为仅控制台日志，确保程序不崩溃
        file_handler = None

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if file_handler is not None:
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.propagate = False
    return logger


def get_log_dir(log_dir_template: str | None = None) -> Path:
    """对外暴露日志目录路径，便于 UI 中"打开日志目录"。"""
    return _resolve_log_dir(log_dir_template)


__all__ = ["get_logger", "get_log_dir"]
