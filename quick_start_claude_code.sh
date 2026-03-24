#!/usr/bin/env bash
set -euo pipefail

CTRL_URL="${CLASH_CTRL_URL:-http://127.0.0.1:9090}"
WORKDIR="${CLAUDE_WORKDIR:-$(pwd)}"
NO_CLAUDE="${NO_CLAUDE:-0}"
CLAUDE_LAUNCH_MODE="${CLAUDE_LAUNCH_MODE:-terminal}"

log() {
  printf '[%s] %s\n' "$(date '+%H:%M:%S')" "$*"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少依赖命令: $1" >&2
    exit 1
  fi
}

for cmd in curl jq rg networksetup scutil osascript; do
  need_cmd "$cmd"
done

api_get() {
  curl -fsS "$CTRL_URL/$1"
}

api_patch() {
  local path="$1"
  local body="$2"
  curl -fsS -X PATCH "$CTRL_URL/$path" \
    -H 'Content-Type: application/json' \
    -d "$body" >/dev/null
}

api_put() {
  local path="$1"
  local body="$2"
  curl -fsS -X PUT "$CTRL_URL/$path" \
    -H 'Content-Type: application/json' \
    -d "$body" >/dev/null
}

ensure_clash_running() {
  if curl -fsS "$CTRL_URL/version" >/dev/null 2>&1; then
    return 0
  fi

  log "未检测到 Clash 控制接口，尝试启动 ClashX Meta..."
  open -gj -b com.metacubex.ClashX.meta >/dev/null 2>&1 || true
  open -gj -a "ClashX Meta" >/dev/null 2>&1 || true

  for _ in $(seq 1 20); do
    sleep 1
    if curl -fsS "$CTRL_URL/version" >/dev/null 2>&1; then
      return 0
    fi
  done

  echo "无法连接 Clash 控制接口: $CTRL_URL" >&2
  exit 1
}

fetch_ip111_us() {
  local raw
  raw="$(curl -fsS --max-time 6 "https://us.ip111.cn/ip.php" \
    -H 'User-Agent: Mozilla/5.0' \
    -H 'Referer: https://ip111.cn/' \
    || true)"

  if [[ -z "$raw" ]]; then
    echo "(获取失败)"
    return 0
  fi

  printf '%s' "$raw" \
    | sed -E 's/<[^>]+>/ /g' \
    | tr -s ' ' \
    | sed 's/^ *//; s/ *$//' \
    | tr -d '\r\n'
}

urlencode() {
  printf '%s' "$1" | jq -sRr @uri
}

find_target_node() {
  local keys node
  keys="$(api_get proxies | jq -r '.proxies | keys[]')"

  node="$(printf '%s\n' "$keys" | rg -m1 'S1.*(US|美国.*华盛顿|华盛顿)' || true)"
  if [[ -z "$node" ]]; then
    node="$(printf '%s\n' "$keys" | rg -m1 'S1' || true)"
  fi

  printf '%s' "$node"
}

switch_group_if_supported() {
  local group="$1"
  local node="$2"
  local group_uri
  group_uri="$(urlencode "$group")"

  if ! api_get proxies | jq -e --arg g "$group" '.proxies[$g] != null' >/dev/null; then
    return 0
  fi

  if ! api_get "proxies/$group_uri" | jq -e --arg n "$node" '.all | index($n) != null' >/dev/null; then
    return 0
  fi

  api_put "proxies/$group_uri" "{\"name\":\"$node\"}"
  log "已切换 [$group] -> $node"
}

enable_vpn_proxy() {
  local proxy_dump
  proxy_dump="$(scutil --proxy 2>/dev/null || true)"
  if printf '%s' "$proxy_dump" | rg -q 'HTTPEnable : 1' \
    && printf '%s' "$proxy_dump" | rg -q 'HTTPProxy : 127\.0\.0\.1' \
    && printf '%s' "$proxy_dump" | rg -q 'HTTPPort : 7893' \
    && printf '%s' "$proxy_dump" | rg -q 'SOCKSEnable : 1' \
    && printf '%s' "$proxy_dump" | rg -q 'SOCKSProxy : 127\.0\.0\.1' \
    && printf '%s' "$proxy_dump" | rg -q 'SOCKSPort : 7893'; then
    log "系统代理已开启（127.0.0.1:7893）"
    return 0
  fi

  local iface services service
  iface="$(route -n get default 2>/dev/null | awk '/interface:/{print $2}')"

  if [[ -n "$iface" ]]; then
    services="$(
      networksetup -listnetworkserviceorder 2>/dev/null \
        | awk -v iface="$iface" '
            /^\([0-9]+\)/ {svc=$0; sub(/^\([0-9]+\) /, "", svc)}
            /Device: / {
              dev=$0
              sub(/^.*Device: /, "", dev)
              sub(/\).*/, "", dev)
              if (dev==iface) print svc
            }
          '
    )"
  else
    services=""
  fi

  if [[ -z "$services" ]]; then
    services="$(networksetup -listallnetworkservices | tail -n +2 | sed '/^\*/d')"
  fi

  while IFS= read -r service; do
    [[ -z "$service" ]] && continue
    networksetup -setwebproxy "$service" 127.0.0.1 7893 off >/dev/null 2>&1 || true
    networksetup -setsecurewebproxy "$service" 127.0.0.1 7893 off >/dev/null 2>&1 || true
    networksetup -setsocksfirewallproxy "$service" 127.0.0.1 7893 off >/dev/null 2>&1 || true
  done <<< "$services"

  log "已尝试开启系统代理（127.0.0.1:7893）"
}

launch_claude() {
  if [[ "$NO_CLAUDE" == "1" ]]; then
    log "NO_CLAUDE=1，跳过启动 Claude Code"
    return 0
  fi

  case "$CLAUDE_LAUNCH_MODE" in
    terminal)
      local workdir_apple
      workdir_apple="${WORKDIR//\\/\\\\}"
      workdir_apple="${workdir_apple//\"/\\\"}"
      osascript >/dev/null <<APPLESCRIPT
set workdir to "$workdir_apple"
tell application "Terminal"
  activate
  if (count of windows) is 0 then
    do script "cd " & quoted form of workdir & " && claude --dangerously-skip-permissions"
  else
    do script "cd " & quoted form of workdir & " && claude --dangerously-skip-permissions" in front window
  end if
end tell
APPLESCRIPT
      log "已启动终端版 Claude Code"
      ;;
    web)
      if open -g "https://claude.ai/new" >/dev/null 2>&1 || open "https://claude.ai/new" >/dev/null 2>&1; then
        log "已启动网站版 Claude（https://claude.ai/new）"
      elif open -g "https://claude.ai/" >/dev/null 2>&1 || open "https://claude.ai/" >/dev/null 2>&1; then
        log "已启动网站版 Claude（https://claude.ai/）"
      else
        echo "无法打开网站版 Claude（https://claude.ai）" >&2
        exit 1
      fi
      ;;
    desktop)
      if open -g -a "Claude" >/dev/null 2>&1 || open -a "Claude" >/dev/null 2>&1; then
        log "已启动桌面版 Claude"
      elif [[ -d "/Applications/Claude.app" ]] && (open -g "/Applications/Claude.app" >/dev/null 2>&1 || open "/Applications/Claude.app" >/dev/null 2>&1); then
        log "已启动桌面版 Claude（/Applications/Claude.app）"
      else
        echo "未找到可启动的 Claude 桌面应用（Claude.app）。" >&2
        exit 1
      fi
      ;;
    *)
      echo "不支持的启动模式: ${CLAUDE_LAUNCH_MODE}（可选：terminal/web/desktop）" >&2
      exit 1
      ;;
  esac
}

ip111_test_ok() {
  local us us_ip
  us="$(fetch_ip111_us)"
  us_ip="$(printf '%s' "$us" | rg -o '[0-9]{1,3}(\.[0-9]{1,3}){3}' -m 1 || true)"

  [[ -z "$us" ]] && us="(获取失败)"

  log "ip111 校验: $us"

  [[ -n "$us_ip" ]]
}

main() {
  ensure_clash_running

  log "步骤 1/4: 先打开 VPN"
  enable_vpn_proxy

  log "步骤 2/4: 打开 TUN 模式，切换华盛顿节点，再打开全局模式"
  api_patch configs '{"tun":{"enable":true}}'

  local target_node
  target_node="$(find_target_node)"
  if [[ -z "$target_node" ]]; then
    echo "未找到可用的 S1 节点，无法继续。" >&2
    exit 1
  fi
  log "匹配到节点: $target_node"

  switch_group_if_supported "🟢 节点选择" "$target_node"
  switch_group_if_supported "GLOBAL" "$target_node"
  api_patch configs '{"mode":"global"}'

  log "步骤 3/4: 用 IP111 校验连接"
  if ! ip111_test_ok; then
    echo "IP111 测试未通过，已停止，不启动 Claude Code。" >&2
    exit 1
  fi

  log "步骤 4/4: 启动 Claude（模式: ${CLAUDE_LAUNCH_MODE}）"
  launch_claude
}

main "$@"
