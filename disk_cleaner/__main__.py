"""支持 ``python -m disk_cleaner`` 启动方式。"""

from .app import main

if __name__ == "__main__":
    raise SystemExit(main())
