import logging
import os
from datetime import datetime

# 确保日志目录存在
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR, exist_ok=True)

# 动态生成带日期的日志文件名
today = datetime.now().strftime('%Y-%m-%d')
LOG_FILE = os.path.join(LOG_DIR, f"tars-{today}.log")

# 配置全局 logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(), # 启用控制台输出
    ]
)

# 显式禁止某些极其啰嗦的库输出到控制台
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("litellm").setLevel(logging.WARNING)
logging.getLogger("LiteLLM").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("mcp.server.lowlevel.server").setLevel(logging.WARNING)

# 针对 LiteLLM 的特殊静默设置
try:
    import litellm
    litellm.set_verbose = False
    litellm.suppress_debug_info = True
    # 彻底关闭它那个讨厌的 "Give Feedback" 提示
    litellm._disable_debugging_on_proxy = True
except ImportError:
    pass

logger = logging.getLogger("Tars")

def log_debug_html(query, html_content):
    """专门用于记录搜索抓取的 HTML 内容以供排查"""
    debug_file = os.path.join(LOG_DIR, f"debug_search_{datetime.now().strftime('%H%M%S')}.html")
    with open(debug_file, "w", encoding="utf-8") as f:
        f.write(f"<!-- Query: {query} -->\n")
        f.write(html_content)
    logger.info(f"搜索原始 HTML 已保存至: {debug_file}")
    return debug_file
