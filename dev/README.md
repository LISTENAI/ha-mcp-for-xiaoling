# 本地 Home Assistant 开发环境

本文档用于在 Windows + WSL2 环境中启动和停止本项目的 Home Assistant 测试实例。整个流程使用 WSL 中的 Python，不使用 Docker。

## 环境信息

| 项目 | 值 |
| --- | --- |
| WSL 发行版 | `Ubuntu` |
| Home Assistant | `2026.8.3` |
| HA Python 环境 | `~/.venvs/ha-xiaoling` |
| 项目目录 | `/mnt/d/project/ha-mcp-for-xiaoling` |
| HA 配置目录 | `/mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config` |
| Home Assistant | `http://localhost:8123` |
| Mock 小聆 API | `http://127.0.0.1:8124` |

Home Assistant 当前不支持直接使用 Windows Python 启动，需要通过 WSL 运行。

## 一次性准备

### 安装 WSL Ubuntu

如果本机还没有 WSL Ubuntu，在管理员 PowerShell 中执行：

```powershell
wsl --install -d Ubuntu
```

安装完成后重启 Windows，并确认发行版可用：

```powershell
wsl -l -v
```

### 创建 Home Assistant Python 环境

本项目使用 `uv` 管理 WSL 中的 Python。先确认 `uv` 可用：

```bash
wsl -d Ubuntu -- bash -lc 'uv --version'
```

如果没有安装 `uv`，在 WSL 中执行：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

然后重新打开 WSL 终端。

创建虚拟环境并安装 Home Assistant：

```bash
wsl -d Ubuntu -- bash -lc 'mkdir -p "$HOME/.venvs" && uv venv --python 3.14 "$HOME/.venvs/ha-xiaoling" && uv pip install --python "$HOME/.venvs/ha-xiaoling/bin/python" homeassistant'
```

检查安装结果：

```bash
wsl -d Ubuntu -- bash -lc '"$HOME/.venvs/ha-xiaoling/bin/hass" --version'
```

### 准备 HA 配置目录和自定义集成链接

HA 只会扫描配置目录下的 `custom_components`。本项目使用符号链接，让 HA 直接读取仓库中的代码：

```bash
wsl -d Ubuntu -- bash -lc 'mkdir -p /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config && rm -rf /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config/custom_components && ln -s /mnt/d/project/ha-mcp-for-xiaoling/custom_components /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config/custom_components'
```

检查链接：

```bash
wsl -d Ubuntu -- bash -lc 'test -f /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config/custom_components/xiaoling_mcp/manifest.json && echo integration-visible'
```

配置文件 `dev/ha-config/configuration.yaml` 应包含：

```yaml
default_config:

logger:
  default: info
  logs:
    custom_components.xiaoling_mcp: debug
```

## 本地 Mock API

真实环境默认连接 `https://staging-api.listenai.com`。只有在需要离线验证配对表单时，才把 `custom_components/xiaoling_mcp/const.py` 临时改为：

```python
XIAOLING_API_BASE = "http://127.0.0.1:8124"
```

`dev/mock_xiaoling_api.py` 模拟配对交换和 Connector WebSocket：

```text
POST /external/mcp/auth/exchange
GET  /v1/mcp/connector
```

Mock 支持以下测试配对码：

| 配对码 | 设备名 | 设备 ID | Connector ID |
| --- | --- | --- | --- |
| `ABC123` | 客厅小聆 | `device-001` | `connector-001` |
| `XYZ789` | 卧室小聆 | `device-002` | `connector-002` |

对接真实小程序时，把 `XIAOLING_API_BASE` 改回 `https://staging-api.listenai.com`。

## 启动服务

推荐使用两个终端前台启动。前台运行时可以直接看到日志，停止时按 `Ctrl+C`。

### 终端一：启动 Mock API

在 Windows PowerShell 中执行：

```powershell
wsl -d Ubuntu -- bash -lc '"$HOME/.venvs/ha-xiaoling/bin/python" /mnt/d/project/ha-mcp-for-xiaoling/dev/mock_xiaoling_api.py'
```

看到以下输出表示启动成功：

```text
Mock Xiaoling API listening on http://127.0.0.1:8124
```

### 终端二：启动 Home Assistant

```powershell
wsl -d Ubuntu -- bash -lc '"$HOME/.venvs/ha-xiaoling/bin/hass" -c /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config --log-rotate-days 0'
```

看到日志出现 `Now listening on port 8123` 后，打开：

```text
http://localhost:8123
```

也可以直接打开集成页面：

```text
http://localhost:8123/config/integrations
```

首次启动需要先完成 Home Assistant 用户初始化。

## 验证集成流程

1. 搜索并添加“小聆 MCP”。首次添加时不输入配对码，也不会连接 MCP Server。
2. 打开“小聆 MCP”服务，点击“添加设备”。
3. 使用小程序生成的配对码，或在 Mock 模式下输入 `ABC123`。
4. 检查日志或 Mock API 收到：

   ```text
   POST /external/mcp/auth/exchange
   ```

5. 确认设备出现在列表中，并且该设备开始连接 `/v1/mcp/connector`。
6. 再添加另一台设备，确认它使用独立的 Connector WebSocket。
7. 测试设备重命名、禁用、重新加载和删除。删除设备时应关闭该设备的 WebSocket，而不是卸载整个集成。
8. 重启 Home Assistant，确认已配对设备会各自重连 MCP Connector。

错误配对码可以使用 `BADCODE`，预期显示配对失败；重复输入同一设备，预期显示设备已经关联。

## 查看状态

### 查看 Home Assistant 是否运行

```powershell
wsl -d Ubuntu -- bash -lc 'curl -sS -o /dev/null -w "HA HTTP %{http_code}\n" http://127.0.0.1:8123/'
```

返回 `HA HTTP 200` 或 `HA HTTP 302` 表示 HTTP 服务已启动。

### 查看 Mock API 是否运行

```powershell
wsl -d Ubuntu -- bash -lc 'curl -sS -i -X POST http://127.0.0.1:8124/api/v1/connect -H "Content-Type: application/json" --data "{\"ha_mcp_endpoint\":\"http://homeassistant.local:8123/api/mcp\"}" | head'
```

正常情况下返回：

```text
HTTP/1.0 204 No Content
```

### 检查端口

```powershell
wsl -d Ubuntu -- bash -lc 'ss -ltnp | grep -E ":(8123|8124)" || true'
```

## 查看日志

HA 主日志：

```powershell
wsl -d Ubuntu -- bash -lc 'tail -f /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config/home-assistant.log'
```

仅查看当前集成日志：

```powershell
wsl -d Ubuntu -- bash -lc 'grep -i -E "xiaoling|custom_components" /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config/home-assistant.log | tail -50'
```

如果 HA 使用重定向方式启动，启动日志在：

```text
dev/homeassistant-wsl.log
```

如果 Mock API 使用重定向方式启动，日志在：

```text
dev/mock-api-wsl.log
```

## 停止服务

### 前台运行

在运行服务的终端分别按：

```text
Ctrl+C
```

先停止 Home Assistant，再停止 Mock API。

### 停止后台运行的 Home Assistant

如果 HA 是后台启动的，先读取 HA 锁文件中的 PID：

```bash
wsl -d Ubuntu -- bash -lc 'cat /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config/.ha_run.lock'
```

锁文件类似：

```json
{"pid": 153, "version": 1, "ha_version": "2026.8.3"}
```

使用实际 PID 停止：

```bash
wsl -d Ubuntu -- bash -lc 'kill 153'
```

确认进程已结束后，若锁文件仍存在可以删除：

```bash
wsl -d Ubuntu -- bash -lc 'rm -f /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config/.ha_run.lock'
```

不要在 Home Assistant 仍运行时删除锁文件，否则可能同时启动两个实例并损坏测试数据库。

### 停止后台运行的 Mock API

查找进程：

```powershell
wsl -d Ubuntu -- bash -lc 'ps -ef | grep mock_xiaoling_api | grep -v grep || true'
```

使用查到的 PID 停止：

```bash
wsl -d Ubuntu -- bash -lc 'kill <MOCK_PID>'
```

如果 Mock API 是从 Windows Python 启动的，可以在 PowerShell 中查看 `8124` 端口：

```powershell
netstat -ano | findstr :8124
```

然后停止对应进程：

```powershell
taskkill /PID <PID> /F
```

### 确认服务已停止

```powershell
wsl -d Ubuntu -- bash -lc 'ss -ltnp | grep -E ":(8123|8124)" || echo services-stopped'
```

## 重启 Home Assistant

前台运行时，在 HA 终端按 `Ctrl+C`，然后重新执行启动命令即可。

如果 HA 异常退出后留下锁文件：

```bash
wsl -d Ubuntu -- bash -lc 'if ! pgrep -f "/hass.*ha-config" >/dev/null; then rm -f /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config/.ha_run.lock; fi'
```

之后重新执行启动命令。

## 清空本地测试实例

以下操作会删除本地 Home Assistant 用户、配置项、设备和数据库，只在需要完全重置测试环境时执行。

1. 先停止 Home Assistant。
2. 执行：

```bash
wsl -d Ubuntu -- bash -lc 'rm -rf /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config && mkdir -p /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config && ln -s /mnt/d/project/ha-mcp-for-xiaoling/custom_components /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config/custom_components'
```

3. 重新创建 `dev/ha-config/configuration.yaml`：

```yaml
default_config:

logger:
  default: info
  logs:
    custom_components.xiaoling_mcp: debug
```

4. 重新启动 Home Assistant，并再次完成用户初始化。

## 集成搜索不到时

按以下顺序检查：

1. 确认符号链接存在：

   ```bash
   wsl -d Ubuntu -- bash -lc 'test -f /mnt/d/project/ha-mcp-for-xiaoling/dev/ha-config/custom_components/xiaoling_mcp/manifest.json && echo visible'
   ```

2. 确认 `manifest.json` 是合法 JSON。
3. 重启 Home Assistant；新增自定义集成时不要只刷新浏览器。
4. 查看日志是否包含：

   ```text
   We found a custom integration xiaoling_mcp
   ```

5. 浏览器使用 `Ctrl+F5` 强制刷新。
6. 搜索名称使用：

   ```text
   小聆 MCP
   ```

## 相关文件

- 集成代码：`custom_components/xiaoling_mcp/`
- HA 配置：`dev/ha-config/`
- Mock API：`dev/mock_xiaoling_api.py`
- 本地调试日志：`dev/*.log`
