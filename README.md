# claude-quickstart-web

下载即用的 Claude 快速启动资源包。

## 一条命令运行

在仓库目录执行：

```bash
bash run.sh
```

运行后会自动打开本地页面：`http://127.0.0.1:8765`

## 资源包内容

- `claude_quickstart_web.py`：本地一键启动页面
- `quick_start_claude_code.sh`：VPN/TUN/节点切换与 Claude 启动脚本
- `run.sh`：一条命令启动入口
- `IMG_0221.HEIC`
- `IMG_0222.HEIC`

## 说明

- 本项目是 macOS 场景脚本（使用 `networksetup`、`scutil`、`osascript`）。
- `quick_start_claude_code.sh` 依赖命令：`curl`、`jq`、`rg`、`networksetup`、`scutil`、`osascript`。
- 仓库已包含运行所需脚本文件，点击 GitHub 的 `Code` 下载后即可本地执行 `bash run.sh`。
