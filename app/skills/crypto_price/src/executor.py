import requests

def get_crypto_prices():
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {'ids': 'bitcoin,ethereum', 'vs_currencies': 'usd'}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
        print(f"Bitcoin (BTC): ${data['bitcoin']['usd']:,.2f}")
        print(f"Ethereum (ETH): ${data['ethereum']['usd']:,.2f}")
        return data
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    get_crypto_prices()
