import sys
import json
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# 模拟浏览器 User-Agent 以避免 403 错误
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def normalize_symbol(symbol):
    """
    统一格式化交易对名称。
    支持：BTCUS -> BTCUSDT, BTC-USD -> BTC-USD, ETH/USDT -> ETHUSDT
    """
    s = symbol.upper().replace('/', '').replace('_', '')
    if '-' in s:
        # 如果自带连字符，保持原样处理
        return s
    
    # 按照约定：US 结尾默认为 USDT
    if s.endswith('US') and not s.endswith('BUS'): # 排除 BUSD 结尾的情况（虽然现在少了）
        s = s[:-2] + 'USDT'
    
    return s

def get_binance_price(symbol):
    # 格式: BTCUSDT
    clean_symbol = symbol.replace('-', '')
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={clean_symbol}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return float(data['price'])
    except:
        return None

def get_okx_price(symbol):
    # 格式: BTC-USDT
    if '-' not in symbol:
        # 尝试拆分，假设最后 4 位是 Quote (USDT)
        if symbol.endswith('USDT'):
            symbol = f"{symbol[:-4]}-{symbol[-4:]}"
        else:
            # 默认假设最后 3 位
            symbol = f"{symbol[:-3]}-{symbol[-3:]}"
    
    url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        if data['code'] == '0' and data['data']:
            return float(data['data'][0]['last'])
    except:
        return None

def get_coinbase_price(symbol):
    # 格式: BTC-USD (Coinbase 常用 USD)
    # 如果用户请求 USDT，在 Coinbase 上通常需要查 USD
    clean_symbol = symbol.replace('USDT', 'USD')
    if '-' not in clean_symbol:
        clean_symbol = f"{clean_symbol[:-3]}-{clean_symbol[-3:]}"
        
    url = f"https://api.coinbase.com/v2/prices/{clean_symbol}/spot"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return float(data['data']['amount'])
    except:
        return None

def get_coingecko_price(symbol):
    # 映射表：简单映射常用币种
    mapping = {
        'BTC': 'bitcoin',
        'ETH': 'ethereum',
        'SOL': 'solana',
        'BNB': 'binancecoin',
        'XRP': 'ripple',
        'ADA': 'cardano',
        'DOGE': 'dogecoin',
        'DOT': 'polkadot'
    }
    
    # 提取 Base 币种
    base = symbol.split('-')[0] if '-' in symbol else symbol
    if base.endswith('USDT'): base = base[:-4]
    elif base.endswith('USD'): base = base[:-3]
    
    coin_id = mapping.get(base)
    if not coin_id:
        return None
        
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {'ids': coin_id, 'vs_currencies': 'usd'}
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        return float(data[coin_id]['usd'])
    except:
        return None

def run(args):
    input_symbol = args.get('symbol', 'BTCUSDT')
    symbol = normalize_symbol(input_symbol)
    
    results = {}
    tasks = {
        'Binance': lambda: get_binance_price(symbol),
        'OKX': lambda: get_okx_price(symbol),
        'Coinbase': lambda: get_coinbase_price(symbol),
        'CoinGecko': lambda: get_coingecko_price(symbol)
    }
    
    with ThreadPoolExecutor(max_workers=4) as executor:
        future_to_exchange = {executor.submit(fn): name for name, fn in tasks.items()}
        for future in as_completed(future_to_exchange):
            name = future_to_exchange[future]
            try:
                price = future.result()
                if price:
                    results[name] = price
            except:
                pass

    if not results:
        print(json.dumps({"error": f"无法获取 {input_symbol} 的价格数据。"}))
        return

    valid_prices = list(results.values())
    avg_price = sum(valid_prices) / len(valid_prices)
    
    output = {
        "symbol": symbol,
        "average_price": round(avg_price, 2),
        "exchanges": results,
        "status": "success"
    }
    print(json.dumps(output, ensure_ascii=False))

if __name__ == "__main__":
    if len(sys.argv) > 1:
        try:
            args = json.loads(sys.argv[1])
            run(args)
        except:
            # 兼容直接传入字符串的情况
            run({"symbol": sys.argv[1]})
    else:
        # 默认测试
        run({"symbol": "BTCUSDT"})
