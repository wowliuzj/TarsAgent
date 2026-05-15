# Tars 技能开发规范 (v1.0)

所有由 Tars 自动生成或人工编写的新技能必须遵循以下标准。

## 1. 目录结构
每个技能必须拥有独立的文件夹，路径为 `app/skills/<skill_name>/`。

```text
app/skills/<skill_name>/
├── manifests/
│   └── skill.json      # 核心元数据与配置
├── src/
│   └── executor.py     # 业务逻辑执行器 (入口)
├── requirements.txt    # (可选) 依赖库列表
└── README.md           # (可选) 技能说明文档
```

## 2. 配置文件 (manifests/skill.json)
必须包含以下字段：
- `name`: 技能名称（必须与目录名一致）。
- `runtime`: 目前仅支持 `python`。
- `main`: 执行入口路径，统一固定为 `src/executor.py`。
- `sandbox`: 布尔值。新生成的、未经审计的、需要联网的技能必须设为 `true`。
- `parameters`: 定义输入参数的 JSON Schema。

**示例：**
```json
{
  "name": "my_new_skill",
  "version": "1.0.0",
  "description": "技能描述",
  "runtime": "python",
  "main": "src/executor.py",
  "sandbox": true,
  "parameters": {
    "type": "object",
    "properties": {
      "query": { "type": "string" }
    }
  }
}
```

## 3. 编写执行器 (src/executor.py)
- **参数读取**：通过 `sys.argv[1]` 获取 JSON 字符串并解析。
- **输出规范**：结果必须打印到 `stdout`，Tars 会捕获这些输出。
- **鲁棒性**：必须包含基本的 try-except 错误处理。

**模板代码：**
```python
import sys
import json

def run(args):
    # 业务逻辑
    print(f"执行结果: {args.get('query')}")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        args = json.loads(sys.argv[1])
        run(args)
```

## 4. 依赖管理
- 如果使用了非标准库（如 `requests`, `pandas`），必须在 `requirements.txt` 中列出。
- Tars 的沙箱环境会自动安装这些依赖。

## 5. 安全原则
- 禁止在沙箱外运行未经验证的代码。
- 严禁在技能代码中硬编码敏感信息（如 API Key），应引导用户配置环境变量。
