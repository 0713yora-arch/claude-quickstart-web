#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "未找到 Python 3，请先安装后重试。" >&2
  exit 1
fi

if [[ ! -f "$ROOT_DIR/quick_start_claude_code.sh" ]]; then
  echo "缺少 quick_start_claude_code.sh，请确认仓库文件完整。" >&2
  exit 1
fi

chmod +x "$ROOT_DIR/quick_start_claude_code.sh" || true

echo "Claude 快速启动页即将启动：http://127.0.0.1:8765"
echo "按 Ctrl+C 可停止服务。"

exec env CLAUDE_QUICKSTART_AUTO_OPEN=1 "$PYTHON_BIN" "$ROOT_DIR/claude_quickstart_web.py"
