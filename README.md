# 小聆 MCP for Home Assistant

通过小聆 AI 控制 Home Assistant 中的灯、开关、空调和其他设备。

## 使用前提

- 已安装并正常运行 Home Assistant
- 已安装 HACS

## 安装与绑定

### 1. 获取配对码

打开 **小聆 AI 小程序**，进入：

**设置 → 第三方服务绑定 → 个人 MCP 服务绑定**

复制页面中的配对码。配对码有效时间较短，请在获取后尽快完成绑定。

### 2. 安装插件

1. 打开 Home Assistant 中的 HACS，进入 **设置 → 设备与服务 → 添加集成**。
2. 搜索 `xiaoling` 或 `ha-mcp-for-xiaoling`。
3. 找到 **MCP Server for xiaoling**，点击安装。
4. 安装完成后重启 Home Assistant。

如果搜索不到插件，请先手动添加自定义仓库：

1. 打开 HACS，点击右上角 **⋮**，选择 **自定义仓库**。
2. 输入仓库地址：`https://github.com/LISTENAI/ha-mcp-for-xiaoling`。
3. 类型选择 **Integration**，点击 **添加**。
4. 返回 HACS，搜索 `xiaoling` 或 `ha-mcp-for-xiaoling`，然后安装插件。

### 3. 添加设备

在 **MCP Server for xiaoling** 插件中点击 **添加设备**，输入小聆 AI 小程序中的配对码并提交。

配对成功后，小聆 AI 即可通过 MCP 控制 Home Assistant 中已公开的设备。

如果提示配对码无效或已过期，请回到小聆 AI 小程序重新生成配对码后再试。
