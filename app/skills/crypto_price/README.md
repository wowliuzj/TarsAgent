# Crypto Price Skill

该技能可以从多个主流交易所获取加密货币的实时价格对，并计算平均价。

## 支持交易所
- Binance
- OKX
- Coinbase
- CoinGecko (常用币种)

## 参数
- `symbol`: 交易对名称。
  - 支持 `BTCUS`, `BTCUSDT`, `BTC-USD`, `ETH/USDT` 等格式。
  - `US` 结尾会自动识别为 `USDT`。

## 输出格式
返回 JSON，包含各交易所价格及平均价。
