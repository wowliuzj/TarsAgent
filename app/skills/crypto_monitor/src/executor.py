import requests
import json
import sys

def get_price(symbol):
    url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        price = float(data['price'])
        return f"当前 {symbol} 价格为: ${price:,.2f}"
    except Exception as e:
        return f"抓取 {symbol} 失败: {str(e)}"

if __name__ == "__main__":
    # 从命令行读取 JSON 格式的参数
    try:
        if len(sys.argv) > 1:
            args = json.loads(sys.argv[1])
            symbol = args.get("symbol", "BTCUSDT")
            print(get_price(symbol))
        else:
            print("错误: 未提供参数")
    except Exception as e:
        print(f"解析参数失败: {str(e)}")
