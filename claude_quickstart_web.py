#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional

HOST = "127.0.0.1"
PORT = 8765
SCRIPT_PATH = Path(__file__).resolve().with_name("quick_start_claude_code.sh")
MAX_LOG_LINES = 600
ALLOWED_LAUNCH_MODES = {"terminal", "web", "desktop"}

state_lock = threading.Lock()
state = {
    "running": False,
    "exit_code": None,
    "logs": [],
    "started_at": None,
    "start_nonce": secrets.token_urlsafe(18),
}
proc_ref: Optional[subprocess.Popen[str]] = None


def can_connect(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def reconcile_state() -> None:
    global proc_ref
    with state_lock:
        if state["running"] and proc_ref is not None:
            rc = proc_ref.poll()
            if rc is not None:
                state["running"] = False
                state["exit_code"] = rc
                state["logs"].append(f"[{time.strftime('%H:%M:%S')}] 后台状态已同步，退出码: {rc}")
                proc_ref = None


def push_log(line: str) -> None:
    line = line.rstrip("\n")
    with state_lock:
        if line.startswith("["):
            state["logs"].append(line)
        else:
            ts = time.strftime("%H:%M:%S")
            state["logs"].append(f"[{ts}] {line}")
        if len(state["logs"]) > MAX_LOG_LINES:
            state["logs"] = state["logs"][-MAX_LOG_LINES:]


def snapshot() -> dict:
    reconcile_state()
    with state_lock:
        return {
            "running": state["running"],
            "exit_code": state["exit_code"],
            "logs": list(state["logs"]),
            "started_at": state["started_at"],
            "start_nonce": state["start_nonce"],
        }


def start_job(start_nonce: str, launch_mode: str) -> tuple[bool, str]:
    global proc_ref
    reconcile_state()
    with state_lock:
        if state["running"]:
            return False, "任务正在运行中，请稍候。"
        if not start_nonce or start_nonce != state["start_nonce"]:
            return False, "启动令牌无效，请点击页面按钮重新确认启动。"
        if launch_mode not in ALLOWED_LAUNCH_MODES:
            return False, "无效的启动模式。"
        if not SCRIPT_PATH.exists():
            return False, f"未找到脚本: {SCRIPT_PATH}"

        state["running"] = True
        state["exit_code"] = None
        state["logs"] = []
        state["started_at"] = int(time.time())
        state["start_nonce"] = secrets.token_urlsafe(18)

    push_log(f"开始执行: {SCRIPT_PATH.name}")

    def worker() -> None:
        global proc_ref
        exit_code = -1
        try:
            run_env = os.environ.copy()
            run_env.pop("NO_CLAUDE", None)
            run_env["CLAUDE_LAUNCH_MODE"] = launch_mode
            proc = subprocess.Popen(
                [str(SCRIPT_PATH)],
                cwd=str(SCRIPT_PATH.parent),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                env=run_env,
            )
            proc_ref = proc
            if proc.stdout is not None:
                for line in proc.stdout:
                    push_log(line)
            exit_code = proc.wait()
        except Exception as exc:  # noqa: BLE001
            push_log(f"启动失败: {exc}")
            exit_code = -1
        finally:
            with state_lock:
                state["running"] = False
                state["exit_code"] = exit_code
            push_log(f"执行结束，退出码: {exit_code}")
            proc_ref = None

    threading.Thread(target=worker, daemon=True).start()
    return True, "已启动。"


HTML_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Claude 快速启动器</title>
  <style>
    :root {
      --bg-1: #f0f8ff;
      --bg-2: #fff7ed;
      --ink: #102a43;
      --ink-soft: #486581;
      --accent: #0f766e;
      --accent-2: #ea580c;
      --panel: #ffffffcc;
      --ok: #0a7f34;
      --warn: #b45309;
      --err: #b42318;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: "IBM Plex Sans", "Noto Sans SC", "PingFang SC", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 10% 0%, #dbeafe 0%, transparent 45%),
        radial-gradient(circle at 95% 85%, #ffedd5 0%, transparent 40%),
        linear-gradient(140deg, var(--bg-1), var(--bg-2));
      display: grid;
      place-items: center;
      padding: 24px;
    }
    .card {
      width: min(900px, 100%);
      background: var(--panel);
      backdrop-filter: blur(8px);
      border: 1px solid #ffffff;
      border-radius: 18px;
      box-shadow: 0 18px 45px rgba(16, 42, 67, 0.15);
      padding: 24px;
    }
    h1 {
      margin: 0 0 8px;
      letter-spacing: 0.3px;
      font-size: clamp(1.35rem, 2.5vw, 2rem);
    }
    .desc {
      color: var(--ink-soft);
      margin-bottom: 18px;
    }
    .row {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      margin-bottom: 14px;
    }
    button {
      border: 0;
      border-radius: 12px;
      padding: 12px 18px;
      font-size: 15px;
      font-weight: 700;
      background: linear-gradient(135deg, var(--accent), #0891b2);
      color: #fff;
      cursor: pointer;
      transition: transform .08s ease, filter .2s ease;
    }
    button:hover { filter: brightness(1.05); }
    button:active { transform: translateY(1px) scale(.995); }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .status {
      padding: 8px 10px;
      border-radius: 10px;
      font-weight: 700;
      background: #ecfeff;
      color: #155e75;
    }
    .status.ok { color: var(--ok); background: #ecfdf3; }
    .status.warn { color: var(--warn); background: #fffbeb; }
    .status.err { color: var(--err); background: #fef2f2; }
    .hint {
      color: var(--ink-soft);
      font-size: 13px;
      margin-bottom: 10px;
    }
    .modes {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-bottom: 12px;
    }
    .mode {
      display: inline-flex;
      gap: 6px;
      align-items: center;
      padding: 8px 10px;
      border-radius: 10px;
      background: #eff6ff;
      border: 1px solid #dbeafe;
      color: #1e3a8a;
      font-size: 14px;
      font-weight: 600;
      user-select: none;
    }
    .mode input { margin: 0; }
    pre {
      margin: 0;
      width: 100%;
      min-height: 280px;
      max-height: 52vh;
      overflow: auto;
      border-radius: 12px;
      background: #0b1728;
      color: #d1e7ff;
      padding: 14px;
      font-family: "JetBrains Mono", "SF Mono", Menlo, Consolas, monospace;
      font-size: 12.5px;
      line-height: 1.5;
      border: 1px solid #1e293b;
    }
    .footer {
      margin-top: 10px;
      color: var(--ink-soft);
      font-size: 12px;
    }
    @media (max-width: 640px) {
      .card { padding: 16px; border-radius: 14px; }
      pre { min-height: 220px; }
    }
  </style>
</head>
<body>
  <section class="card">
    <h1>Claude 一键启动页</h1>
    <div class="desc">顺序：打开 VPN → TUN + 华盛顿节点 + 全局模式 → IP111 校验 → 启动 Claude。</div>
    <div class="row">
      <button id="startBtn">一键启动</button>
      <span id="status" class="status">待命</span>
    </div>
    <div class="modes">
      <label class="mode"><input type="radio" name="launchMode" value="terminal" checked /> 启动终端版</label>
      <label class="mode"><input type="radio" name="launchMode" value="web" /> 启动网站版</label>
      <label class="mode"><input type="radio" name="launchMode" value="desktop" /> 启动桌面版</label>
    </div>
    <div class="hint">当前动作：<code id="modeHint">claude --dangerously-skip-permissions</code></div>
    <pre id="logBox">准备就绪，点击“一键启动”。</pre>
    <div class="footer">本页面只监听本机地址 127.0.0.1。请保持启动器终端窗口开启；关闭后服务会停止。</div>
  </section>

  <script>
    const startBtn = document.getElementById("startBtn");
    const statusEl = document.getElementById("status");
    const logBox = document.getElementById("logBox");
    const modeHint = document.getElementById("modeHint");
    let failedPolls = 0;
    let currentStartNonce = "";

    function selectedMode() {
      return (document.querySelector("input[name='launchMode']:checked") || {}).value || "terminal";
    }

    function updateModeHint() {
      const mode = selectedMode();
      if (mode === "terminal") {
        modeHint.textContent = "claude --dangerously-skip-permissions";
      } else if (mode === "web") {
        modeHint.textContent = "打开 https://claude.ai/new";
      } else {
        modeHint.textContent = "打开 Claude 桌面应用";
      }
    }

    function setStatus(text, cls) {
      statusEl.textContent = text;
      statusEl.className = "status " + (cls || "");
    }

    function setLogs(lines) {
      logBox.textContent = (lines && lines.length) ? lines.join("\\n") : "暂无日志";
      logBox.scrollTop = logBox.scrollHeight;
    }

    async function refresh() {
      try {
        const resp = await fetch("/api/state", { cache: "no-store" });
        if (!resp.ok) throw new Error("bad status");
        const data = await resp.json();
        failedPolls = 0;
        currentStartNonce = data.start_nonce || "";
        setLogs(data.logs || []);

        if (data.running) {
          setStatus("运行中", "warn");
          startBtn.disabled = true;
        } else if (typeof data.exit_code === "number") {
          if (data.exit_code === 0) {
            setStatus("上次执行成功", "ok");
          } else {
            setStatus("上次执行失败", "err");
          }
          startBtn.disabled = false;
        } else {
          setStatus("待命", "");
          startBtn.disabled = false;
        }
      } catch (e) {
        failedPolls += 1;
        startBtn.disabled = false;
      }
    }

    startBtn.addEventListener("click", async () => {
      const mode = selectedMode();
      startBtn.disabled = true;
      setStatus("正在启动...", "warn");
      try {
        const resp = await fetch("/api/start", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ start_nonce: currentStartNonce, launch_mode: mode })
        });
        const data = await resp.json();
        if (!resp.ok || !data.ok) {
          setStatus(data.message || "启动失败", "err");
          startBtn.disabled = false;
          return;
        }
        setStatus("运行中", "warn");
      } catch (e) {
        setStatus("请求失败", "err");
        startBtn.disabled = false;
      }
      await refresh();
    });

    document.querySelectorAll("input[name='launchMode']").forEach((el) => {
      el.addEventListener("change", updateModeHint);
    });

    setInterval(refresh, 1000);
    updateModeHint();
    refresh();
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _write_json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, code: int, payload: str) -> None:
        body = payload.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/" or self.path.startswith("/?"):
            self._write_html(200, HTML_PAGE)
            return
        if self.path == "/api/state":
            self._write_json(200, snapshot())
            return
        self._write_json(404, {"ok": False, "message": "Not Found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/start":
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            try:
                payload = json.loads(raw.decode("utf-8"))
            except Exception:
                payload = {}
            start_nonce = str(payload.get("start_nonce", ""))
            launch_mode = str(payload.get("launch_mode", "terminal"))
            ok, message = start_job(start_nonce, launch_mode)
            code = 200 if ok else 409
            self._write_json(code, {"ok": ok, "message": message})
            return
        self._write_json(404, {"ok": False, "message": "Not Found"})

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> None:
    if not SCRIPT_PATH.exists():
        print(f"未找到脚本: {SCRIPT_PATH}")
        print("请先确认 quick_start_claude_code.sh 在同目录。")
        raise SystemExit(1)

    url = f"http://{HOST}:{PORT}"
    if can_connect(HOST, PORT):
        print(f"检测到启动页已运行，直接打开: {url}")
        webbrowser.open(url)
        return

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Claude 启动页已就绪: {url}")
    print("按 Ctrl+C 停止服务。")

    auto_open = os.environ.get("CLAUDE_QUICKSTART_AUTO_OPEN", "1") == "1"
    if auto_open:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
