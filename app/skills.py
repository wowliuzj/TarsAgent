import os
import sys
import json
import subprocess
from app.logger import logger

def execute_skill_module(skill_name, args):
    """
    执行一个技能模块。
    支持两种模式：
    1. 逻辑隔离：宿主机 Python 直接运行 (适用于审计过的技能)
    2. 物理隔离：Docker 容器运行 (适用于第三方或 Tars 自生成的技能)
    """
    # 获取技能目录
    project_root = os.getcwd()
    skill_path = os.path.join(project_root, "app/skills", skill_name)
    
    # 尝试多种路径查找 skill.json
    manifest_candidates = [
        os.path.join(skill_path, "manifests", "skill.json"),
        os.path.join(skill_path, "skill.json")
    ]
    
    manifest_path = None
    for candidate in manifest_candidates:
        if os.path.exists(candidate):
            manifest_path = candidate
            break

    if not manifest_path:
        return f"错误: 技能 {skill_name} 缺少配置文件 (skill.json)"

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    runtime = manifest.get("runtime", "python")
    main_script = manifest.get("main", "main.py")
    use_sandbox = manifest.get("sandbox", False)
    
    args_json = json.dumps(args)

    if use_sandbox:
        return execute_skill_in_docker(skill_name, skill_path, runtime, main_script, args_json)
    else:
        # 宿主机直接执行
        full_entry_path = os.path.join(skill_path, main_script)
        try:
            result = subprocess.run(
                [sys.executable, full_entry_path, args_json],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            return f"技能执行失败: {e.stderr}"

def execute_skill_in_docker(skill_name, skill_path, runtime, main_script, args_json):
    """
    在 Docker 容器中物理隔离运行技能
    """
    project_root = os.getcwd()
    
    # 挂载整个 skills 目录，这样技能内部可以通过相对路径访问 (虽然不推荐)
    # 更好的做法是只挂载当前技能目录
    skills_root = os.path.join(project_root, "app/skills")
    
    # 构建 Docker 命令
    docker_cmd = [
        "docker", "run", "--rm",
        "-v", f"{skills_root}:/app/skills",
        "-w", f"/app/skills/{skill_name}"
    ]

    # --- 代理透传与自动转换 ---
    proxy_vars = ["HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", 
                  "http_proxy", "https_proxy", "all_proxy", "no_proxy"]
    
    docker_cmd.extend(["--add-host", "host.docker.internal:host-gateway"])

    for var in proxy_vars:
        val = os.getenv(var)
        if val:
            val = val.replace("127.0.0.1", "host.docker.internal").replace("localhost", "host.docker.internal")
            docker_cmd.extend(["-e", f"{var}={val}"])
    
    # 镜像选择
    image = "python:3.10-slim"
    if runtime == "node":
        image = "node:18-slim"
    
    docker_cmd.append(image)

    # --- 构造容器内执行指令 (支持自动安装依赖) ---
    if runtime == "python":
        # 检查是否有 requirements.txt
        inner_cmd = f"python {main_script} '{args_json}'"
        if os.path.exists(os.path.join(skill_path, "requirements.txt")):
            logger.info(f"检测到 {skill_name} 依赖，正在沙箱中安装...")
            inner_cmd = f"pip install --no-cache-dir -r requirements.txt && {inner_cmd}"
        
        docker_cmd.extend(["sh", "-c", inner_cmd])
    else:
        # 其他 runtime (如 node)
        docker_cmd.extend([runtime, main_script, args_json])

    try:
        logger.info(f"正在启动沙箱执行技能: {skill_name}")
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout
    except subprocess.CalledProcessError as e:
        return f"沙箱执行失败 (Exit {e.returncode}): {e.stderr or e.stdout}"

def load_dynamic_skills():
    """
    扫描 app/skills 目录，加载所有技能的元数据，用于工具定义。
    """
    project_root = os.getcwd()
    skills_dir = os.path.join(project_root, "app/skills")
    tools = []
    
    if not os.path.exists(skills_dir):
        logger.warning(f"技能目录不存在: {skills_dir}")
        return tools

    for skill_name in os.listdir(skills_dir):
        skill_path = os.path.join(skills_dir, skill_name)
        if not os.path.isdir(skill_path):
            continue
            
        # 尝试多种路径查找 skill.json
        manifest_candidates = [
            os.path.join(skill_path, "manifests", "skill.json"),
            os.path.join(skill_path, "skill.json")
        ]
        
        manifest_path = None
        for candidate in manifest_candidates:
            if os.path.exists(candidate):
                manifest_path = candidate
                break
        
        if manifest_path:
            try:
                with open(manifest_path, "r", encoding="utf-8") as f:
                    manifest = json.load(f)
                
                # 转换为 OpenAI 工具格式
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": manifest.get("name", skill_name),
                        "description": f"[Tier 2] {manifest.get('description', '')}",
                        "parameters": manifest.get("parameters", {
                            "type": "object",
                            "properties": {},
                            "required": []
                        })
                    }
                }
                tools.append(tool_def)
                logger.info(f"成功加载技能定义: {skill_name}")
            except Exception as e:
                logger.error(f"加载技能 {skill_name} 定义失败: {str(e)}")
                
    return tools

# 导出动态加载的技能工具列表
DYNAMIC_SKILL_TOOLS = load_dynamic_skills()
