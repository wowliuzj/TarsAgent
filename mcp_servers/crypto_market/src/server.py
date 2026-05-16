import sys
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from mcp.server.fastmcp import FastMCP

# 初始化 FastMCP
mcp = FastMCP("crypto_market")

# 模拟浏览器 User-Agent
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def normalize_symbol(symbol):
    s = symbol.upper().replace('/', '').replace('_', '')
    if '-' in s: return s
    if s.endswith('US') and not s.endswith('BUS'):
        s = s[:-2] + 'USDT'
    return s

def get_binance_price(symbol):
    clean_symbol = symbol.replace('-', '')
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={clean_symbol}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        return float(resp.json()['price'])
    except: return None

def get_okx_price(symbol):
    if '-' not in symbol:
        symbol = f"{symbol[:-4]}-{symbol[-4:]}" if symbol.endswith('USDT') else f"{symbol[:-3]}-{symbol[-3:]}"
    url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        data = resp.json()
        if data['code'] == '0' and data['data']: return float(data['data'][0]['last'])
    except: return None

@mcp.tool()
def get_crypto_price(symbol: str) -> str:
    """【加密货币专家】获取主流交易所（如 Binance, OKX）的最新行情。支持聚合报价，是查询 BTC, ETH, USDT 等币种实时价格的唯一权威工具。"""
    symbol = normalize_symbol(symbol)
    tasks = {
        'Binance': lambda: get_binance_price(symbol),
        'OKX': lambda: get_okx_price(symbol)
    }
    
    results = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_to_exchange = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(future_to_exchange):
            name = future_to_exchange[future]
            try:
                price = future.result()
                if price: results[name] = price
            except: pass

    if not results:
        return f"无法获取 {symbol} 的报价。"

    avg = sum(results.values()) / len(results)
    return f"交易对: {symbol}\n平均价: {avg:,.2f}\n详情: {json.dumps(results)}"

if __name__ == "__main__":
    mcp.run(transport="stdio")
