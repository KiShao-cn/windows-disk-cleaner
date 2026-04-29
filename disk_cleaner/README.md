# C 盘空间清理工具 (DiskCleaner)

一个面向 Windows 的 **安全优先** C 盘空间清理工具，基于 Python + PySide6 构建。

> ⚠️ 设计目标：**宁可少删，不可错删**。系统目录、`Program Files`、用户个人文件（桌面/文档/下载等）**永远不会**被本工具删除。

---

## 项目简介

- 仅扫描经过审计的"安全白名单"目录（用户 Temp、Windows Temp）。
- 删除文件 **默认移动到 Windows 回收站**，可在回收站中恢复；不提供"永久删除"。
- 删除前 **双重安全校验**（白名单 + 黑名单），并要求用户在弹窗中确认。
- 全过程后台线程执行，不卡死 UI；支持中途取消。
- 所有扫描/清理行为写入日志，方便事后审计。

---

## 安装方式

要求 Python 3.10+ 和 Windows 10/11。

```bash
cd disk_cleaner
pip install -r requirements.txt
```

## 运行方式

在项目根目录（`cp_tools`）执行：

```bash
python -m disk_cleaner
```

或：

```bash
cd disk_cleaner
python app.py
```

如需清理 `C:\Windows\Temp` 中无权限的文件，请在 PowerShell 中右键 **以管理员身份运行**。本工具 **不会** 主动请求或绕过提权。

---

## 支持的清理范围（MVP 版本）

| 范围 | 默认勾选 | 说明 |
|---|---|---|
| `%TEMP%` / `%LOCALAPPDATA%\Temp` | 是 | 用户临时文件 |
| `C:\Windows\Temp` | 是 | 系统临时文件，可能需管理员权限 |
| `*.log` / `*.tmp` / `*.dmp` / `*.bak`（仅在白名单目录内） | 否（中风险） | 仅扫描，需用户手动勾选 |

> **不会** 全盘搜索 `*.log` 或任何后缀。所有文件都必须位于白名单目录之内。

---

## 安全说明

### 白名单（仅扫描这些目录）

- `%TEMP%`
- `%TMP%`
- `%LOCALAPPDATA%\Temp`
- `C:\Windows\Temp`

### 黑名单（永远不会清理）

下列目录**绝对禁止**删除任何文件，即使误传入也会被双重校验拦截：

- 系统目录：
  - `C:\Windows\System32`
  - `C:\Windows\SysWOW64`
  - `C:\Windows\WinSxS`
  - `C:\Windows\Boot`
  - `C:\Windows\Fonts`
  - `C:\Windows\Installer`
- 程序目录：
  - `C:\Program Files`
  - `C:\Program Files (x86)`
  - `C:\ProgramData\Microsoft`
- 用户个人文件目录：
  - `Desktop` / `Documents` / `Pictures` / `Videos` / `Music`
  - `Downloads` / `OneDrive` / `iCloudDrive` / `Google Drive` / `Dropbox`
  - `Favorites` / `Contacts` / `Links` / `Saved Games` / `Searches`

### 安全机制

1. **路径白名单**：所有候选路径必须落在白名单根目录之内，否则丢弃。
2. **路径黑名单**：命中黑名单一律拒绝，**即使** 同时落在白名单内（一票否决）。
3. **路径规范化**：使用 `Path.resolve()` 解析真实路径，防止 `..` 路径穿越。
4. **拒绝符号链接**：扫描过程不跟随 symlink，避免被骗到白名单外。
5. **跳过近期文件**：默认跳过最近 24 小时内修改过的文件（避免误删正在使用的临时文件）。
6. **跳过权限错误**：无权限的文件直接跳过，**不会** 强制提权或修改 ACL。
7. **删除即回收站**：通过 `send2trash` 移动到回收站，**不调用** `os.remove`、`shutil.rmtree`、`del /f /s /q` 等危险接口。
8. **二次确认弹窗**：清理前展示文件数量、释放空间、风险提示，必须用户点击"是"才执行。
9. **失败不中断**：单个文件失败不影响其他文件，最终展示失败列表与原因。
10. **全过程日志**：日志位于 `%LOCALAPPDATA%\DiskCleaner\logs\disk_cleaner.log`。

详见 `core/safety.py` 顶部的安全边界注释。

---

## 不会清理的目录

参见上文 **黑名单** 一节。本工具 **不允许**：

- 全盘无差别递归删除
- 按后缀全盘删除（如 `*.log` 全盘搜索）
- 自动清理注册表
- 修改启动项 / 删除驱动 / 删除 Windows 更新组件
- 删除 `Program Files` 下的软件文件
- 静默 / 后台 / 启动后自动清理
- 绕过权限或修改系统 ACL

---

## 常见问题

**Q: 清理后能恢复吗？**
A: 默认进入回收站，可恢复；本工具不提供永久删除。

**Q: 为什么扫描出的文件比预期少？**
A: 默认跳过最近 24 小时修改过的文件、无权限文件、符号链接、系统保护文件，这是设计行为。

**Q: 提示"需要管理员权限"怎么办？**
A: 关闭程序，右键 PowerShell → 以管理员身份运行 → 重新启动本程序。本工具不会强制提权。

**Q: 浏览器缓存为什么没扫到？**
A: MVP 版本未启用浏览器缓存扫描；可在 `config/default_config.json` 中调整（仍需自行评估风险）。

---

## 风险提示

- 程序仅扫描临时目录，**理论上** 安全；但 Windows 上仍可能存在第三方软件把临时目录用作缓存的情况，建议清理前先关闭浏览器、IDE 等程序。
- 若管理员权限运行，`C:\Windows\Temp` 中的某些文件可能正被系统服务占用，删除会失败属于正常现象。
- 本项目以"安全优先"为最高准则，**严禁** 通过修改源码绕过安全校验扩大删除范围。

---

## 项目结构

```text
disk_cleaner/
├── app.py                   # 程序入口
├── __main__.py              # 支持 python -m disk_cleaner
├── requirements.txt
├── README.md
├── config/
│   └── default_config.json
├── core/
│   ├── safety.py            # 安全边界（最重要）
│   ├── scanner.py           # 扫描器
│   ├── cleaner.py           # 清理器
│   ├── recycle_bin.py       # send2trash 封装
│   └── disk_info.py         # 磁盘容量
├── ui/
│   ├── main_window.py       # 主窗口（PySide6）
│   └── workers.py           # 后台线程 Worker
├── utils/
│   ├── logger.py
│   ├── size_formatter.py
│   └── path_utils.py
└── tests/
    ├── test_safety.py       # 安全模块测试（最关键）
    ├── test_scanner.py
    └── test_cleaner.py
```

---

## 运行测试

```bash
cd ..
python -m unittest discover -s disk_cleaner/tests -v
```

当前 19 项测试全部通过。
