# Tars MCP 开发指南 (MCP Development Guide)

Tars Agent 采用 Anthropic 的 **Model Context Protocol (MCP)** 作为其核心插件标准。所有的工具（Tools）都作为独立的 MCP Server 运行。

## 目录结构

```text
mcp_servers/
└── {server_name}/
    ├── manifests/
    │   └── server.json     # 服务元数据与运行配置
    ├── src/
    │   └── server.py       # 使用 FastMCP 编写的服务代码
    ├── requirements.txt    # 该 Server 的依赖
    └── README.md
```

## 快速开始：创建一个新 MCP Server

### 1. 编写 server.json
在 `manifests/` 目录下创建 `server.json`：

```json
{
  "name": "my_tool_server",
  "version": "1.0.0",
  "description": "我的自定义工具集",
  "runtime": {
    "type": "docker"  // 使用 "docker" 进行物理隔离，或 "native" 直接运行
  },
  "entrypoint": "python src/server.py"
}
```

### 2. 编写 server.py
使用 `mcp-python-sdk` 编写：

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("MyTool")

@mcp.tool()
def my_custom_tool(param1: str) -> str:
    """工具的描述词，模型会根据此描述决定是否调用。"""
    return f"执行结果: {param1}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
```

## 运行模式 (Runtime Types)

- **`native`**: 直接在 Tars 主环境中运行。适用于高性能或受信任的系统工具。
- **`docker`**: 在独立的 Docker 容器中运行。Tars 会自动挂载 Server 目录并执行。适用于需要物理隔离的第三方工具。

## 注意事项
- **不要使用 `print()` 进行调试**：MCP 通过 `stdout` 通信，普通的 `print` 会破坏协议。请使用 `logging` 或 `sys.stderr`。
- **异步支持**：Tars 核心是异步的，推荐在 MCP Server 中也使用 `async` 函数。
