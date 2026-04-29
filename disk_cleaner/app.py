"""程序入口：启动 PySide6 主窗口。"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow
from .utils.logger import get_logger


def main() -> int:
    logger = get_logger()
    logger.info("应用启动")

    app = QApplication(sys.argv)
    app.setApplicationName("DiskCleaner")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
