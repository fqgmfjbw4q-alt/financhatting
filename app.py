import os
import yfinance as yf
from flask import Flask, render_template, jsonify
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

def get_price(symbol):
    try:
        ticker = yf.Ticker(symbol)
        # 1 günlük geçmiş veriden en sonuncuyu alıyoruz
        data = ticker.history(period="1d")
        if not data.empty:
            return float(data['Close'].iloc[-1])
    except Exception as e:
        print(f"Hata ({symbol}): {e}")
    return None

def get_economic_calendar():
    return {
        'fed_rate': {
            'current': 4.50,
            'next_meeting': '2026-03-19',
            'label': 'FED Faiz Kararı'
        },
        'nonfarm_payroll': {
            'value': '210K',
            'previous': '227K',
            'date': '2026-02-06',
            'label': 'Tarım Dışı İstihdam'
        },
        'unemployment': {
            'value': '4.1%',
            'previous': '4.2%',
            'date': '2026-02-06',
            'label': 'İşsizlik Oranı'
        },
        'inflation': {
            'value': '3.1%',
            'previous': '2.9%',
            'date': '2026-02-12',
            'label': 'Enflasyon (CPI)'
        }
    }

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/prices')
def get_prices():
    prices = {
        'btc': get_price('BTC-USD'),
        'gold': get_price('GC=F'),
        'silver': get_price('SI=F'),
        'copper': get_price('HG=F'),
        'usd_try': get_price('USDTRY=X'),
        'eur_try': get_price('EURTRY=X'),
        'bist100': get_price('XU100.IS'),
        'timestamp': datetime.now().isoformat()
    }
    return jsonify(prices)

@app.route('/api/calendar')
def get_calendar():
    return jsonify(get_economic_calendar())

if __name__ == '__main__':
    # Railway'de çalışması için 8080 portunu varsayılan yapıyoruz
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
