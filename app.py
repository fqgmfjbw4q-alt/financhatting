from flask import Flask, render_template, jsonify, request, redirect, url_for
import yfinance as yf
from datetime import datetime

app = Flask(__name__)

# NOT: PostgreSQL bağlantı bilgilerini Railway üzerinden alınca buraya ekleyeceğiz.
# Şu an sistemin çökmemesi için iskelet yapıyı koruyorum.

def get_financial_data():
    symbols = {
        'btc': 'BTC-USD', 'gold': 'GC=F', 'silver': 'SI=F',
        'copper': 'HG=F', 'usd_try': 'USDTRY=X', 'eur_try': 'EURTRY=X',
        'bist100': '^XU100'
    }
    prices = {}
    try:
        for key, symbol in symbols.items():
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='1d')
            if not data.empty:
                prices[key] = data['Close'].iloc[-1]
            else:
                prices[key] = None
        
        # Gram Altın Hesabı (Önceki koddan korundu)
        if prices.get('gold') and prices.get('usd_try'):
            prices['gram_altin'] = (prices['gold'] / 31.1035) * prices['usd_try']
    except Exception as e:
        print(f"Veri çekme hatası: {e}")
    
    prices['timestamp'] = datetime.now().isoformat()
    return prices

# --- SOSYAL AĞ ROTALARI ---

@app.route('/')
def index():
    # Sayfa parametresi ile index.html içindeki bölümleri kontrol ediyoruz
    return render_template('index.html', page="markets")

@app.route('/feed')
def feed():
    return render_template('index.html', page="feed")

@app.route('/kesfet')
def kesfet():
    return render_template('index.html', page="explore")

@app.route('/@<username>')
def profile(username):
    # Twitter mantığı @username yapısı aktif edildi
    return render_template('index.html', page="profile", username=username)

@app.route('/api/prices')
def prices():
    return jsonify(get_financial_data())

@app.route('/api/calendar')
def calendar():
    # Ekonomik takvim verileri (Önceki koddan korundu)
    data = {
        "fed_rate": {"current": 4.50, "next_meeting": "2026-01-28"},
        "nonfarm_payroll": {"label": "Tarım Dışı İstihdam", "value": "215K", "previous": "190K", "date": "2026-02-06"},
        "unemployment": {"label": "İşsizlik Oranı", "value": "3.9%", "previous": "4.0%", "date": "2026-02-06"},
        "inflation": {"label": "TR Enflasyon (TÜFE)", "value": "44.2%", "previous": "45.1%", "date": "2026-02-03"}
    }
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
