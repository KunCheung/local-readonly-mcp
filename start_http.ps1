$ErrorActionPreference = "Stop"

.\.venv\Scripts\python.exe .\server.py --transport streamable-http --host 127.0.0.1 --port 8000
