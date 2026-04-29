# C盘空间清理工具 - Cursor 开发要求与约束文档

## 1. 项目目标

开发一个 Windows 桌面端 C 盘空间清理工具，帮助用户安全扫描、展示并清理 C 盘中可删除的临时文件、缓存文件、日志文件和回收站内容。

核心原则：

- 安全优先，严禁误删系统关键文件、用户个人文件和程序核心文件。
- 默认只扫描，不自动删除。
- 所有删除操作必须经过用户确认。
- 删除前必须展示文件类型、路径、大小和风险等级。
- 支持白名单和黑名单机制。
- 支持日志记录和清理历史追踪。

---

## 2. 技术建议

### 2.1 推荐技术栈

优先选择以下方案之一：

#### 方案 A：Python 桌面工具

- Python 3.10+
- PySide6 或 PyQt6
- pathlib / os / shutil
- send2trash，用于安全删除到回收站
- psutil，用于磁盘信息统计
- logging，用于日志记录

#### 方案 B：Electron 桌面工具

- Electron
- React / Vue
- Node.js fs 模块
- Windows Shell API 或 PowerShell 辅助脚本

如果没有特殊要求，优先使用 **Python + PySide6** 实现。

---

## 3. 核心功能要求

### 3.1 磁盘空间概览

工具启动后展示：

- C 盘总容量
- 已使用空间
- 可用空间
- 使用率百分比
- 建议清理空间预估值

展示形式：

- 数字卡片
- 进度条
- 简单图表，可选

---

### 3.2 扫描功能

支持扫描以下安全区域：

#### 用户临时目录

```text
%TEMP%
%TMP%
C:\Users\<当前用户>\AppData\Local\Temp
```

#### Windows 临时目录

```text
C:\Windows\Temp
```

注意：

- 需要管理员权限时，应提示用户。
- 无权限访问的文件跳过，不报错中断。

#### 浏览器缓存，可选

可扫描但默认不删除：

```text
Chrome Cache
Edge Cache
Firefox Cache
```

#### 系统日志，可选

只允许扫描常见日志文件：

```text
*.log
*.tmp
*.dmp
*.bak
```

限制：

- 仅扫描明确安全路径下的日志文件。
- 不允许全盘递归扫描所有 `.log` 文件。

#### 回收站

支持统计回收站占用空间。

删除回收站内容前必须二次确认。

---

### 3.3 文件分类

扫描结果需要按类型分类：

| 分类 | 说明 | 默认是否可选 |
|---|---|---|
| 临时文件 | temp/tmp/cache 等 | 是 |
| 日志文件 | log 文件 | 是 |
| 崩溃转储 | dmp 文件 | 是 |
| 浏览器缓存 | Chrome/Edge/Firefox 缓存 | 否 |
| 回收站 | Windows 回收站 | 否 |
| 大文件提示 | 仅展示，不删除 | 否 |

---

### 3.4 大文件分析

支持扫描 C 盘下的大文件，但必须遵守：

- 只展示，不默认清理。
- 不自动删除。
- 用户需要手动打开文件所在目录后自行处理。
- 默认阈值：500MB。
- 可配置阈值：100MB、500MB、1GB、2GB。

禁止自动删除以下目录下的大文件：

```text
C:\Windows
C:\Program Files
C:\Program Files (x86)
C:\ProgramData
C:\Users\<用户>\Documents
C:\Users\<用户>\Desktop
C:\Users\<用户>\Pictures
C:\Users\<用户>\Videos
C:\Users\<用户>\Downloads
```

---

## 4. 删除机制要求

### 4.1 默认删除方式

默认使用安全删除：

- 优先移动到回收站。
- 不允许直接永久删除，除非用户在设置中明确开启。
- 永久删除必须弹窗二次确认。

推荐使用：

```python
send2trash
```

---

### 4.2 删除前确认

用户点击“清理”后必须展示确认弹窗：

弹窗内容包括：

- 即将删除的文件数量
- 预计释放空间
- 文件分类
- 是否移动到回收站
- 风险提示

示例：

```text
即将清理 1,253 个文件，预计释放 2.4GB 空间。
默认会将文件移动到回收站。
是否继续？
```

---

### 4.3 删除失败处理

删除失败时：

- 不得中断整个任务。
- 记录失败路径和原因。
- 在清理完成后展示失败列表。
- 常见失败原因包括：
  - 文件正在使用
  - 无权限
  - 路径不存在
  - 文件被系统保护

---

## 5. 严格禁止行为

Cursor 必须遵守以下约束。

### 5.1 禁止删除系统关键目录

严禁删除、移动、修改以下目录中的任何文件：

```text
C:\Windows\System32
C:\Windows\SysWOW64
C:\Windows\WinSxS
C:\Windows\Boot
C:\Windows\Fonts
C:\Windows\Installer
C:\Program Files
C:\Program Files (x86)
C:\ProgramData\Microsoft
```

---

### 5.2 禁止删除用户个人文件

严禁自动删除以下目录中的文件：

```text
Desktop
Documents
Pictures
Videos
Music
Downloads
OneDrive
iCloudDrive
Google Drive
Dropbox
```

这些目录只能用于“大文件展示”，不能自动清理。

---

### 5.3 禁止危险操作

严禁实现以下功能：

- 全盘无差别递归删除。
- 根据文件后缀全盘删除。
- 自动删除用户文件。
- 自动清理注册表。
- 修改系统启动项。
- 删除 Windows 更新组件。
- 删除驱动文件。
- 删除 Program Files 下的软件文件。
- 删除未知目录中的文件。
- 静默清理。
- 后台自动清理。
- 启动后自动删除。
- 绕过权限删除文件。
- 使用 `del /f /s /q C:\*` 等危险命令。
- 使用 `rmdir /s /q` 删除不受控目录。
- 关闭杀毒软件或系统保护。
- 修改系统权限 ACL。

---

## 6. 路径白名单机制

所有可清理路径必须来自白名单。

示例白名单：

```python
SAFE_CLEAN_PATHS = [
    "%TEMP%",
    "%TMP%",
    "C:\\Users\\<USER>\\AppData\\Local\\Temp",
    "C:\\Windows\\Temp",
]
```

要求：

- 程序启动时解析真实路径。
- 删除前必须验证目标文件是否位于白名单目录内。
- 使用 `Path.resolve()` 处理真实路径。
- 防止路径穿越。
- 防止符号链接误删。

---

## 7. 文件过滤规则

### 7.1 可清理文件规则

只允许清理满足以下条件的文件：

- 位于白名单目录内。
- 文件不是系统隐藏核心文件。
- 文件最后修改时间距离当前时间超过 24 小时。
- 文件未被其他进程占用。
- 文件路径不在黑名单中。

---

### 7.2 默认跳过规则

跳过以下文件：

- 最近 24 小时修改过的文件。
- 正在使用的文件。
- 无权限访问的文件。
- 符号链接指向白名单外部的文件。
- 系统保护文件。
- 文件名或路径异常的文件。

---

## 8. 风险等级设计

扫描结果需要标记风险等级：

| 风险等级 | 含义 | 示例 |
|---|---|---|
| 低风险 | 可安全清理 | Temp 目录下超过 24 小时的 tmp 文件 |
| 中风险 | 建议用户确认 | 浏览器缓存、日志文件 |
| 高风险 | 只展示，不允许一键删除 | 大文件、用户目录文件 |
| 禁止 | 绝不删除 | 系统目录、程序目录、个人文件 |

默认只勾选低风险项目。

---

## 9. UI 页面要求

### 9.1 首页

包含：

- C 盘空间概览
- 一键扫描按钮
- 扫描范围选择
- 最近一次清理记录

---

### 9.2 扫描结果页

包含：

- 可释放空间总计
- 文件分类统计
- 文件列表
- 风险等级
- 是否默认勾选
- 清理按钮
- 打开文件所在目录按钮

---

### 9.3 清理进度页

包含：

- 当前处理文件
- 处理进度
- 已清理空间
- 成功数量
- 失败数量
- 取消按钮

---

### 9.4 清理完成页

包含：

- 实际释放空间
- 成功清理数量
- 失败文件数量
- 失败原因列表
- 查看日志按钮

---

## 10. 配置项要求

支持配置文件，例如：

```json
{
  "scan_recent_file_hours": 24,
  "large_file_threshold_mb": 500,
  "delete_mode": "recycle_bin",
  "enable_browser_cache_scan": false,
  "enable_windows_temp_scan": true,
  "enable_large_file_scan": true
}
```

配置说明：

- `delete_mode` 默认只能是 `recycle_bin`。
- 不允许默认启用永久删除。
- 用户开启永久删除时必须有风险提示。

---

## 11. 日志要求

需要记录：

- 扫描开始时间
- 扫描结束时间
- 扫描路径
- 扫描文件数量
- 可释放空间
- 删除文件路径
- 删除结果
- 删除失败原因
- 用户确认时间

日志文件路径建议：

```text
C:\Users\<当前用户>\AppData\Local\DiskCleaner\logs
```

---

## 12. 异常处理要求

程序必须处理以下异常：

- PermissionError
- FileNotFoundError
- OSError
- 文件占用
- 路径过长
- 磁盘读取失败
- 回收站调用失败
- 管理员权限不足

所有异常都要：

- 记录日志。
- UI 友好提示。
- 不导致程序崩溃。

---

## 13. 权限要求

默认以普通用户权限运行。

如需清理 `C:\Windows\Temp`：

- 检测是否拥有权限。
- 无权限时提示“需要管理员权限”。
- 不强制提权。
- 不绕过权限。

---

## 14. 性能要求

- 扫描过程不能卡死 UI。
- 扫描和删除使用后台线程。
- 大目录扫描需要支持取消。
- 文件列表分页或虚拟滚动。
- 单次扫描超过 10 秒时显示进度。
- 跳过无权限目录，不重复尝试。

---

## 15. 安全校验伪代码

```python
def is_safe_to_delete(path: Path, safe_roots: list[Path], blocked_roots: list[Path]) -> bool:
    resolved = path.resolve()

    for blocked in blocked_roots:
        if resolved == blocked or blocked in resolved.parents:
            return False

    is_under_safe_root = any(
        resolved == root or root in resolved.parents
        for root in safe_roots
    )

    if not is_under_safe_root:
        return False

    if resolved.is_symlink():
        return False

    return True
```

删除前必须调用类似安全校验函数。

---

## 16. 推荐项目结构

```text
disk_cleaner/
├── app.py
├── requirements.txt
├── README.md
├── config/
│   └── default_config.json
├── core/
│   ├── scanner.py
│   ├── cleaner.py
│   ├── safety.py
│   ├── disk_info.py
│   └── recycle_bin.py
├── ui/
│   ├── main_window.py
│   ├── scan_result_view.py
│   └── settings_view.py
├── utils/
│   ├── logger.py
│   ├── size_formatter.py
│   └── path_utils.py
└── tests/
    ├── test_safety.py
    ├── test_scanner.py
    └── test_cleaner.py
```

---

## 17. Cursor 执行要求

Cursor 在生成代码时必须遵守：

1. 先生成项目结构。
2. 先实现安全校验模块 `safety.py`。
3. 再实现扫描模块。
4. 再实现清理模块。
5. 最后实现 UI。
6. 所有删除逻辑必须经过安全校验。
7. 所有删除操作必须默认移动到回收站。
8. 不允许生成危险命令行删除逻辑。
9. 每个核心模块必须包含基础单元测试。
10. 代码中必须写清楚安全边界注释。

---

## 18. MVP 版本范围

第一版只做以下功能：

- C 盘空间概览
- 扫描用户 Temp 目录
- 扫描 Windows Temp 目录
- 展示文件列表
- 默认只勾选低风险文件
- 移动到回收站清理
- 日志记录
- 清理完成统计

第一版暂不做：

- 注册表清理
- 系统更新清理
- 驱动清理
- 软件卸载
- 自动后台清理
- 浏览器深度清理
- 微信/QQ 专项清理

---

## 19. 验收标准

项目完成后必须满足：

- 程序可正常启动。
- 可显示 C 盘容量信息。
- 可扫描安全临时目录。
- 可展示扫描文件数量和大小。
- 清理前有确认弹窗。
- 删除默认进入回收站。
- 无权限文件不会导致程序崩溃。
- 系统目录和用户个人文件不会被删除。
- 清理结果有日志。
- 单元测试通过。
- README 中有运行说明和安全说明。

---

## 20. README 必须包含

README 至少包含：

- 项目简介
- 安装方式
- 运行方式
- 支持的清理范围
- 安全说明
- 不会清理的目录
- 常见问题
- 风险提示

---

## 21. 给 Cursor 的最终指令

请基于本需求文档开发一个 Windows C 盘空间清理工具。

必须优先保证安全性，不允许为了释放空间而扩大删除范围。

请先生成项目结构和核心安全模块，再逐步实现扫描、清理和 UI。

所有危险操作必须避免，所有删除操作必须经过用户确认和路径白名单校验。
