from flask import Flask, render_template, jsonify
import requests
from datetime import datetime
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

ALPHA_VANTAGE_KEY = os.getenv('ALPHA_VANTAGE_KEY', 'YLJHVUGL27NP73T0')

def get_crypto_price(symbol):
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return float(response.json()['price'])
    except:
        pass
    return None

def get_forex_price(from_currency, to_currency):
    try:
        url = f"https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_currency}&to_currency={to_currency}&apikey={ALPHA_VANTAGE_KEY}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            if 'Realtime Currency Exchange Rate' in data:
                return float(data['Realtime Currency Exchange Rate']['5. Exchange Rate'])
    except:
        pass
    return None

def get_commodity_price(symbol):
    try:
        url = f"https://api.metals.live/v1/spot/{symbol}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data[0]['price'] if data else None
    except:
        pass
    return None

def get_bist100():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/XU100.IS"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return float(data['chart']['result'][0]['meta']['regularMarketPrice'])
    except:
        pass
    return None

def get_economic_calendar():
    return {
        'fed_rate': {
            'current': 4.50,
            'next_meeting': '2025-03-19',
            'label': 'FED Faiz Kararı'
        },
        'nonfarm_payroll': {
            'value': '256K',
            'previous': '227K',
            'date': '2025-02-07',
            'label': 'Tarım Dışı İstihdam'
        },
        'unemployment': {
            'value': '4.1%',
            'previous': '4.2%',
            'date': '2025-02-07',
            'label': 'İşsizlik Oranı'
        },
        'inflation': {
            'value': '2.9%',
            'previous': '2.7%',
            'date': '2025-02-12',
            'label': 'Enflasyon (CPI)'
        }
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/prices')
def get_prices():
    prices = {
        'btc': get_crypto_price('BTC') or 104250.50,
        'gold': get_commodity_price('XAU') or 2785.40,
        'silver': get_commodity_price('XAG') or 30.25,
        'copper': get_commodity_price('COPPER') or 4.15,
        'usd_try': get_forex_price('USD', 'TRY') or 35.45,
        'eur_try': get_forex_price('EUR', 'TRY') or 36.82,
        'bist100': get_bist100() or 10245.67,
        'timestamp': datetime.now().isoformat()
    }
    return jsonify(prices)

@app.route('/api/calendar')
def get_calendar():
    return jsonify(get_economic_calendar())

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
