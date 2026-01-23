from flask import Flask, render_template, jsonify
import requests
from datetime import datetime, timedelta
import os
from flask_cors import CORS

app = Flask(**name**)
CORS(app)

# API Anahtarları - Railway environment variables’dan alınacak

ALPHA_VANTAGE_KEY = os.getenv(‘ALPHA_VANTAGE_KEY’, ‘YLJHVUGL27NP73T0’)

def get_crypto_price(symbol):
“”“Cryptocurrency fiyatlarını al”””
try:
url = f”https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT”
response = requests.get(url, timeout=5)
if response.status_code == 200:
data = response.json()
return float(data[‘price’])
except:
pass
return None

def get_forex_price(from_currency, to_currency):
“”“Döviz kurlarını al”””
try:
url = f”https://www.alphavantage.co/query?function=CURRENCY_EXCHANGE_RATE&from_currency={from_currency}&to_currency={to_currency}&apikey={ALPHA_VANTAGE_KEY}”
response = requests.get(url, timeout=5)
if response.status_code == 200:
data = response.json()
if ‘Realtime Currency Exchange Rate’ in data:
return float(data[‘Realtime Currency Exchange Rate’][‘5. Exchange Rate’])
except:
pass
return None

def get_commodity_price(symbol):
“”“Emtia fiyatlarını al (Altın, Gümüş, Bakır)”””
try:
# Metals API kullanımı
url = f”https://api.metals.live/v1/spot/{symbol}”
response = requests.get(url, timeout=5)
if response.status_code == 200:
data = response.json()
return data[0][‘price’] if data else None
except:
pass

```
# Alternatif olarak Alpha Vantage
try:
    commodity_symbols = {
        'XAU': 'GOLD',
        'XAG': 'SILVER',
        'COPPER': 'COPPER'
    }
    if symbol in commodity_symbols:
        url = f"https://www.alphavantage.co/query?function=COMMODITY&symbol={commodity_symbols[symbol]}&interval=daily&apikey={ALPHA_VANTAGE_KEY}"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return float(data['data'][0]['value']) if 'data' in data and data['data'] else None
except:
    pass
return None
```

def get_bist100():
“”“BIST 100 endeksini al”””
try:
# Yahoo Finance API
url = “https://query1.finance.yahoo.com/v8/finance/chart/XU100.IS”
response = requests.get(url, timeout=5)
if response.status_code == 200:
data = response.json()
price = data[‘chart’][‘result’][0][‘meta’][‘regularMarketPrice’]
return float(price)
except:
pass
return None

def get_economic_calendar():
“”“Ekonomik takvim verilerini hazırla”””
calendar = {
‘fed_rate’: {
‘current’: 4.50,  # Güncel FED faiz oranı
‘next_meeting’: ‘2025-03-19’,
‘label’: ‘FED Faiz Kararı’
},
‘nonfarm_payroll’: {
‘value’: ‘256K’,
‘previous’: ‘227K’,
‘date’: ‘2025-02-07’,
‘label’: ‘Tarım Dışı İstihdam’
},
‘unemployment’: {
‘value’: ‘4.1%’,
‘previous’: ‘4.2%’,
‘date’: ‘2025-02-07’,
‘label’: ‘İşsizlik Oranı’
},
‘inflation’: {
‘value’: ‘2.9%’,
‘previous’: ‘2.7%’,
‘date’: ‘2025-02-12’,
‘label’: ‘Enflasyon (CPI)’
}
}
return calendar

@app.route(’/’)
def index():
return render_template(‘index.html’)

@app.route(’/api/prices’)
def get_prices():
“”“Tüm fiyat verilerini topla”””
prices = {
‘btc’: get_crypto_price(‘BTC’),
‘gold’: get_commodity_price(‘XAU’),
‘silver’: get_commodity_price(‘XAG’),
‘copper’: get_commodity_price(‘COPPER’),
‘usd_try’: get_forex_price(‘USD’, ‘TRY’),
‘eur_try’: get_forex_price(‘EUR’, ‘TRY’),
‘bist100’: get_bist100(),
‘timestamp’: datetime.now().isoformat()
}

```
# Fallback değerler (API başarısız olursa)
if prices['btc'] is None:
    prices['btc'] = 104250.50
if prices['usd_try'] is None:
    prices['usd_try'] = 35.45
if prices['eur_try'] is None:
    prices['eur_try'] = 36.82
if prices['bist100'] is None:
    prices['bist100'] = 10245.67
if prices['gold'] is None:
    prices['gold'] = 2785.40
if prices['silver'] is None:
    prices['silver'] = 30.25
if prices['copper'] is None:
    prices['copper'] = 4.15

return jsonify(prices)
```

@app.route(’/api/calendar’)
def get_calendar():
“”“Ekonomik takvim verilerini döndür”””
calendar = get_economic_calendar()
return jsonify(calendar)

if **name** == ‘**main**’:
port = int(os.environ.get(‘PORT’, 5000))
app.run(host=‘0.0.0.0’, port=port, debug=False)