import os
import sys

def main():
    print("--- 物理沙箱安全审计报告 ---")
    
    # 1. 检查当前工作目录
    print(f"当前工作目录: {os.getcwd()}")
    
    # 2. 检查目录可见性
    print("\n容器内 /app 目录内容:")
    try:
        print(os.listdir("/app"))
    except Exception as e:
        print(f"无法读取 /app: {e}")

    # 3. 尝试寻找宿主机敏感文件 (应该找不到)
    print("\n尝试访问宿主机 .env 文件:")
    if os.path.exists("/app/.env") or os.path.exists("../.env"):
        print("警告：发现了 .env 文件！沙箱可能存在漏洞。")
    else:
        print("安全：未发现 .env 文件。")

    # 4. 检查网络连通性
    print("\n网络连通性测试:")
    import subprocess
    try:
        res = subprocess.run(["ping", "-c", "1", "google.com"], capture_output=True, timeout=5)
        if res.returncode == 0:
            print("网络：已连通")
        else:
            print("网络：不可达")
    except:
        print("网络测试工具缺失")

if __name__ == "__main__":
    main()
