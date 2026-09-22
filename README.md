# local-readonly-mcp

一个面向 ChatGPT、Cursor、Claude Code 等 MCP Host 的**薄型只读本地文件系统 MCP Server**。

它只负责提供安全、受控、有界的文件读取与搜索能力。**文件选择、检索策略、调用顺序以及上下文管理由 MCP Host 负责。**

```text
ChatGPT / MCP Host
├─ reasoning
├─ planning
├─ tool selection
└─ context management
        │
        ▼
local-readonly-mcp
├─ list
├─ stat
├─ search
└─ read
        │
        ▼
Local Filesystem
```

## 设计原则

- **Thin MCP**：不在 MCP 内实现 Agent、代码理解或任务规划
- **Read only**：没有 write / edit / delete / rename / copy / mkdir / shell
- **Explicit roots**：只能访问本地配置中明确允许的目录
- **Bounded output**：每次工具调用的返回量都有上限
- **Host-controlled continuation**：MCP 返回 `has_more` 和下一位置，由 MCP Host 决定是否继续
- **Offset pagination**：目录和搜索使用直观的 `offset / limit`
- **Private paths**：模型只看到 root alias 和相对路径，不看到本机绝对目录
- **Secret filtering**：默认阻止常见密钥和凭证文件
- **No recursive link traversal**：递归 list/search 不进入 symlink/junction
- **Local HTTP by default**：Streamable HTTP 默认只允许 loopback

## MCP Tools

```text
list_roots()

list_directory(
    root=None,
    path="",
    recursive=False,
    max_depth=2,
    offset=0,
    limit=100
)

stat_path(
    path,
    root=None
)

read_text_file(
    path,
    root=None,
    start_line=1,
    end_line=300
)

search_files(
    pattern,
    root=None,
    path="",
    offset=0,
    limit=100
)

search_text(
    query,
    root=None,
    path="",
    file_glob="*",
    offset=0,
    limit=50
)

reload_config()
```

## 分页与续读

目录和搜索统一使用 `offset / limit`：

```text
search_text(
    query="OpenAI",
    offset=0,
    limit=50
)
```

返回：

```json
{
  "offset": 0,
  "limit": 50,
  "returned": 50,
  "has_more": true,
  "next_offset": 50,
  "results": []
}
```

如果 Host 还需要结果，再从 `next_offset` 继续。

文件读取使用行号：

```text
read_text_file(
    path="src/main.py",
    start_line=1,
    end_line=300
)
```

如果后面还有内容：

```json
{
  "start_line": 1,
  "end_line": 300,
  "has_more": true,
  "next_start_line": 301,
  "content": "..."
}
```

如果请求起始行已经超过 EOF：

```json
{
  "start_line": 1000,
  "end_line": null,
  "has_more": false,
  "next_start_line": null,
  "eof_reached": true,
  "start_beyond_eof": true,
  "total_lines": 123,
  "content": ""
}
```

当本次读取实际到达 EOF 时会返回 `total_lines`；未扫描到 EOF 时该字段为 `null`。

## 上下文控制

这个 MCP 不尝试获取或管理 ChatGPT 的剩余上下文长度。它只保证**单次工具返回有界**。

默认：

```json
{
  "max_output_chars": 65536
}
```

各工具默认：

```text
list_directory   limit=100
search_files     limit=100
search_text      limit=50
read_text_file   1-300 行
```

文件始终保留在本地。模型需要时可以再次调用 MCP，而不是把整个项目一次性复制进对话上下文。

## 安装

要求：

```text
Python >= 3.10
mcp[cli] >= 2.0, < 3
```

本项目使用 MCP Python SDK v2 的 `MCPServer` API。安装旧版 MCP SDK 会导致导入或运行失败。

### Windows PowerShell

```powershell
git clone https://github.com/KunCheung/local-readonly-mcp.git
cd local-readonly-mcp
.\setup.ps1
```

### macOS / Linux

```bash
git clone https://github.com/KunCheung/local-readonly-mcp.git
cd local-readonly-mcp
bash ./setup.sh
```

安装脚本会创建虚拟环境、安装依赖，并在本地不存在 `config.json` 时从 `config.example.json` 创建一份。

`config.json` 已加入 `.gitignore`。

## 配置可读目录

Windows 示例：

```json
{
  "default_root": "project",
  "max_read_bytes": 2097152,
  "max_search_file_bytes": 10485760,
  "max_output_chars": 65536,
  "allow_sensitive_files": false,
  "deny_patterns": [],
  "allow_patterns": [],
  "roots": {
    "project": "D:/Code/project"
  }
}
```

macOS / Linux 示例：

```json
{
  "default_root": "project",
  "roots": {
    "project": "/home/user/code/project"
  }
}
```

调用工具时使用 alias：

```text
root="project"
path="src/main.py"
```

不传 `root` 时使用 `default_root`。

修改配置后可以重启 MCP，或者调用：

```text
reload_config()
```

## 敏感文件策略

默认阻止：

```text
.env
.env.*
*.pem
*.key
id_rsa
id_ed25519
credentials.json
service-account*.json
.ssh/
.aws/
.npmrc
.pypirc
.netrc
```

以下模板文件默认允许：

```text
.env.example
.env.sample
.env.template
```

### 推荐：精确放行

如果只需要读取某一种默认敏感文件，优先使用 `allow_patterns`，不要关闭整套过滤。

例如仅允许读取 `.env`：

```json
{
  "roots": {
    "project": {
      "path": "D:/Code/project",
      "allow_patterns": [
        ".env",
        "*/.env"
      ]
    }
  }
}
```

`allow_patterns` 是**追加式**的：root 级配置会叠加全局配置和内置的 `.env.example/.sample/.template` 例外。

这种配置只会放行匹配的 `.env`，`*.pem`、`id_rsa`、`credentials.json` 等仍然保持阻止。

### 全量关闭默认敏感文件过滤

仅在确实需要时：

```json
{
  "roots": {
    "special": {
      "path": "D:/special",
      "allow_sensitive_files": true
    }
  }
}
```

`allow_sensitive_files=true` 会关闭该 root 的**整套内置 deny patterns**，只保留你显式配置的 `deny_patterns`。不建议对大范围目录开启。

## Symlink / Junction 策略

递归目录遍历和搜索采用保守策略：

> **永远不进入 symlink / junction / Windows reparse-point 目录，即使目标仍位于授权 root 内。**

这是有意的安全边界，不是“校验通过后继续递归”。

因此：

- `list_directory(recursive=true)`
- `search_files`
- `search_text`

都会在结果中返回：

```json
{
  "skipped_links": 1
}
```

表示本次调用因链接边界跳过了多少条目，提醒 Host 搜索结果可能不是物理文件树的完整展开。

显式读取一个路径时仍会执行 `resolve(strict=True)` 和 root 边界检查：解析后越过 root 的路径会被拒绝。

Windows junction/reparse-point 检测兼容 Python 3.10/3.11，不依赖只有 Python 3.12+ 才提供的 `Path.is_junction()`。

## 启动

### stdio

Windows：

```powershell
.\.venv\Scripts\python.exe .\server.py --config .\config.json
```

macOS / Linux：

```bash
./.venv/bin/python ./server.py --config ./config.json
```

### Streamable HTTP

Windows：

```powershell
.\start_http.ps1
```

macOS / Linux：

```bash
bash ./start_http.sh
```

默认：

```text
http://127.0.0.1:8000/mcp
```

默认拒绝绑定 `0.0.0.0` 或局域网 IP。只有明确配置认证和网络访问控制时才使用：

```text
--allow-remote
```

## 文件与编码

`read_text_file` 支持：

```text
UTF-8
UTF-8 BOM
GB18030
UTF-16 BOM
UTF-32 BOM
```

读取结果使用紧凑行号格式：

```text
120 | ...
121 | ...
122 | ...
```

## 隐私边界

模型看到：

```text
root="project"
path="src/main.py"
```

不会通过 MCP 工具得到：

```text
D:/Code/project
C:/Users/...
```

真实路径只存在于本机 MCP Server 进程中。

> 这是应用层访问控制。如果需要更强隔离，建议让 MCP Server 使用一个对授权目录只有读取权限的独立 OS 用户运行。

## 测试

```bash
python -m pip install -e ".[dev]"
python -m pytest
```

GitHub Actions 覆盖：

```text
Windows / Ubuntu / macOS
Python 3.10 / 3.12
```

测试包括：

- 路径穿越与跨 root 访问
- 默认敏感文件过滤
- 精确 `allow_patterns` 放行
- 绝对路径隐藏
- UTF-16 文本
- `offset / limit` 分页
- EOF / 行号越界语义
- symlink 跳过与 `skipped_links`
- Python 3.10/3.11 reparse-point fallback
- 单次输出上限
- loopback HTTP 保护
- `WorkspaceError` 经 MCP SDK 转换为 tool error result

## 为什么没有 Shell

即使把 Shell 描述成“只读”，重定向、子进程、命令参数以及某些工具本身仍可能产生副作用。

因此项目只提供目的明确的文件系统读取能力，不提供任意命令执行。

## License

MIT
