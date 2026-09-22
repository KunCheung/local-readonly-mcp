# local-readonly-mcp

一个面向 MCP Host 的**本地只读文件系统 MCP Server**。

目标很简单：让 ChatGPT / Cursor / Claude Code / 其他 MCP Host 能读取你明确授权的本地目录，但**不能写、改、删文件，也不能执行 Shell 命令**。

## Features

- 多个可配置只读根目录
- `list_directory`：查看目录
- `stat_path`：查看文件/目录信息
- `read_text_file`：按行读取文本文件
- `search_files`：按文件名/Glob 搜索
- `search_text`：递归搜索文本内容
- `list_roots`：查看当前授权目录
- `reload_config`：修改配置后重新加载
- 路径越界检查
- Symlink / Junction 解析后再次校验
- 无 write / edit / delete / rename / copy / mkdir / shell 工具

基于 MCP Python SDK v2。

## 1. 配置可读目录

编辑 `config.json`：

```json
{
  "default_root": "tmp",
  "max_read_bytes": 2097152,
  "max_search_file_bytes": 10485760,
  "roots": {
    "tmp": "D:/tmp"
  }
}
```

可以自由增加目录：

```json
{
  "default_root": "tmp",
  "roots": {
    "tmp": "D:/tmp",
    "project": "D:/Code/project",
    "docs": "E:/documents"
  }
}
```

`tmp`、`project`、`docs` 是给 MCP 使用的目录别名。

例如：

```text
root="project"
path="src/main.py"
```

如果调用工具时不传 `root`，使用 `default_root`。

修改 `config.json` 后可以重启服务，也可以调用：

```text
reload_config
```

## 2. 安装

要求 Python 3.10+。

Windows PowerShell：

```powershell
git clone https://github.com/KunCheung/local-readonly-mcp.git
cd local-readonly-mcp
.\setup.ps1
```

或者手动：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 3. MCP Inspector 测试

```powershell
.\.venv\Scripts\python.exe -m mcp dev server.py -- --config config.json
```

## 4. stdio 模式

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

## 5. Streamable HTTP 模式

```powershell
.\start_http.ps1
```

默认地址：

```text
http://127.0.0.1:8000/mcp
```

也可以直接运行：

```powershell
.\.venv\Scripts\python.exe .\server.py --transport streamable-http --host 127.0.0.1 --port 8000 --config .\config.json
```

默认只监听 loopback，不直接暴露到局域网。

## 6. 安全边界

假设：

```json
"tmp": "D:/tmp"
```

允许：

```text
D:/tmp/a.txt
D:/tmp/project/src/main.py
```

以下路径会被拒绝：

```text
../
D:/tmp/../Code
C:/Windows
```

除非目标目录本身被单独加入 `roots`。

> 这是应用层只读边界。若需要更强的安全隔离，建议让 MCP Server 使用一个对授权目录只有读取权限的 Windows 用户运行。

## 7. 读取限制

默认：

- 单次直接读取的文件最大 2 MiB
- 内容搜索时单个文件最大 10 MiB
- 单次 `read_text_file` 最多返回 2000 行
- 默认跳过 `.git`、`node_modules`、`.venv`、`dist`、`build`、`target` 等目录

可以在 `config.json` 全局调整，也可以为单个 root 单独配置：

```json
{
  "roots": {
    "logs": {
      "path": "D:/logs",
      "max_read_bytes": 4194304,
      "max_search_file_bytes": 20971520
    }
  }
}
```

## Why no shell?

即使把 Shell 描述为“只读”，重定向、子进程、命令参数以及某些工具本身仍可能产生副作用。

因此这个项目只提供目的明确的只读文件系统工具，不提供任意命令执行能力。
