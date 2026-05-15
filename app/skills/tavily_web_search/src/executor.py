import os
import sys
import json
from tavily import TavilyClient

def web_search(query: str, max_results: int = 5) -> str:
    """
    使用 Tavily API 进行专业、稳定的全网搜索。
    """
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return "错误: 未在环境变量中配置 TAVILY_API_KEY。请先在 .env 中设置。"
    
    try:
        tavily = TavilyClient(api_key=api_key)
        # search_depth="advanced" 可以获得更深度的分析结果
        # include_answer=True 会让 Tavily 尝试直接给出一个聚合后的答案
        response = tavily.search(
            query=query, 
            search_depth="advanced", 
            max_results=max_results,
            include_answer=True
        )
        
        results = []
        
        # 1. 如果 Tavily 已经生成了聚合答案，优先展示
        if response.get("answer"):
            results.append(f"[智能摘要] {response['answer']}\n")
            
        # 2. 列出具体的参考源
        for i, res in enumerate(response.get("results", [])):
            results.append(f"[{i+1}] {res['title']}\n    链接: {res['url']}\n    内容: {res['content'][:300]}...")
            
        if not results:
            return f"Tavily 未能找到关于 '{query}' 的搜索结果。"
            
        return f"--- Tavily AI Search Results for: {query} ---\n\n" + "\n\n".join(results)
        
    except Exception as e:
        return f"Tavily 搜索失败: {str(e)}"

if __name__ == "__main__":
    try:
        if len(sys.argv) > 1:
            args = json.loads(sys.argv[1])
            query = args.get("query")
            if not query:
                print("错误: 缺少 query 参数")
            else:
                print(web_search(query))
        else:
            print("错误: 未提供参数 JSON")
    except Exception as e:
        print(f"执行失败: {str(e)}")
