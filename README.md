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
- **Host-controlled continuation**：MCP 返回 `has_more` 和下一位置，由 ChatGPT 决定是否继续调用
- **No cursor pagination**：目录和搜索统一使用直观的 `offset / limit`
- **Private paths**：模型只看到 root alias 和相对路径，不看到本机绝对目录
- **Secret filtering**：默认阻止常见密钥和凭证文件
- **Local HTTP by default**：Streamable HTTP 默认只允许 loopback

## MCP Tools

核心读取接口：

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
```

另有管理接口：

```text
reload_config()
```

## 分页与续读

目录和搜索统一使用 `offset / limit`，不使用 cursor。

例如：

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

如果 ChatGPT 需要更多结果，再调用：

```text
search_text(
    query="OpenAI",
    offset=50,
    limit=50
)
```

文件读取使用行号，不使用 offset：

```text
read_text_file(
    path="src/main.py",
    start_line=1,
    end_line=300
)
```

如果仍有内容，返回：

```json
{
  "start_line": 1,
  "end_line": 300,
  "has_more": true,
  "next_start_line": 301,
  "content": "..."
}
```

是否继续读取由 MCP Host 决定。

## 上下文控制

这个 MCP 不尝试获取或管理 ChatGPT 的剩余上下文长度。

它只保证**单次工具返回有界**，避免一次调用把整个项目或大量文件内容塞入模型上下文。

默认：

```json
{
  "max_output_chars": 65536
}
```

另外各工具有默认数量限制：

```text
list_directory   limit=100
search_files     limit=100
search_text      limit=50
read_text_file   1-300 行
```

文件始终保留在本地。如果模型后续需要某段内容，可以再次调用 MCP 读取，而不是依赖此前把整个项目放进对话上下文。

## 安装

要求 Python 3.10+。

```powershell
git clone https://github.com/KunCheung/local-readonly-mcp.git
cd local-readonly-mcp
.\setup.ps1
```

`setup.ps1` 会创建虚拟环境、安装依赖，并在本地不存在 `config.json` 时从 `config.example.json` 创建一份。

`config.json` 已加入 `.gitignore`，不会被默认提交到 Git。

## 配置可读目录

修改本地 `config.json`：

```json
{
  "default_root": "tmp",
  "max_read_bytes": 2097152,
  "max_search_file_bytes": 10485760,
  "max_output_chars": 65536,
  "allow_sensitive_files": false,
  "deny_patterns": [],
  "allow_patterns": [
    ".env.example",
    "**/.env.example"
  ],
  "roots": {
    "tmp": "D:/tmp",
    "project": "D:/Code/project"
  }
}
```

调用时使用 alias，而不是绝对路径：

```text
root="project"
path="src/main.py"
```

不传 `root` 时使用 `default_root`。

修改配置后可以重启 MCP，或者调用：

```text
reload_config()
```

### 单个 root 单独配置

```json
{
  "roots": {
    "project": {
      "path": "D:/Code/project",
      "max_search_file_bytes": 52428800,
      "deny_patterns": [
        "**/secrets/**"
      ]
    }
  }
}
```

## 敏感文件策略

默认阻止常见秘密文件，例如：

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

如果某个 root 确实需要读取敏感文件，可以显式设置：

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

不建议对大范围目录开启该选项。

## 启动

### stdio

```powershell
.\.venv\Scripts\python.exe .\server.py --config .\config.json
```

MCP Host 配置示例：

```json
{
  "mcpServers": {
    "local-readonly": {
      "command": "D:/path/to/local-readonly-mcp/.venv/Scripts/python.exe",
      "args": [
        "D:/path/to/local-readonly-mcp/server.py",
        "--config",
        "D:/path/to/local-readonly-mcp/config.json"
      ]
    }
  }
}
```

### Streamable HTTP

```powershell
.\start_http.ps1
```

默认端点：

```text
http://127.0.0.1:8000/mcp
```

默认拒绝绑定 `0.0.0.0` 或局域网 IP。只有明确配置了认证和网络访问控制时才使用：

```text
--allow-remote
```

## 文件与编码

`read_text_file` 按行范围读取，并限制单次返回量。底层支持：

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

模型看到的是：

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

> 这是应用层访问控制。如果需要更强隔离，建议让 MCP Server 使用一个对授权目录只有读取权限的独立 Windows 用户运行。

## 测试

安装开发依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

运行：

```powershell
pytest
```

GitHub Actions 在 Windows 上测试 Python 3.10 和 3.12。

覆盖重点包括：

- 路径穿越与跨 root 访问
- 敏感文件过滤
- 绝对路径隐藏
- UTF-16 文本
- `offset / limit` 分页
- 分页连续性、无重复
- `has_more / next_offset`
- `has_more / next_start_line`
- 单次输出上限
- loopback HTTP 保护

## 为什么没有 Shell

即使把 Shell 描述成“只读”，重定向、子进程、命令参数以及某些工具本身仍可能产生副作用。

因此项目只提供目的明确的文件系统读取能力，不提供任意命令执行。

## License

MIT
