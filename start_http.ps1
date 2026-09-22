$ErrorActionPreference = "Stop"

$Config = if ($env:READONLY_MCP_CONFIG) { $env:READONLY_MCP_CONFIG } else { ".\config.json" }

.\.venv\Scripts\python.exe .\server.py `
  --config $Config `
  --transport streamable-http `
  --host 127.0.0.1 `
  --port 8000
