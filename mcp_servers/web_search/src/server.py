import os
from tavily import TavilyClient
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("web_search")

@mcp.tool()
def tavily_search(query: str, max_results: int = 5) -> str:
    """【通用搜索/最后手段】仅当没有其他专门工具（如加密货币工具、文件工具）可以处理请求时，才使用此工具。"""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "错误: 未在环境变量中配置 TAVILY_API_KEY。"
    
    try:
        tavily = TavilyClient(api_key=api_key)
        response = tavily.search(query=query, search_depth="advanced", max_results=max_results)
        
        results = []
        for i, res in enumerate(response.get("results", [])):
            results.append(f"[{i+1}] {res['title']}\n    URL: {res['url']}\n    内容: {res['content'][:200]}...")
            
        return "\n\n".join(results)
    except Exception as e:
        return f"搜索失败: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
