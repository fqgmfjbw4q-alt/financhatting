from flask import Flask, render_template, jsonify, request, redirect, url_for
import yfinance as yf
from datetime import datetime

app = Flask(__name__)

# Sunucu çalıştığı sürece postları hafızada tutan gerçek liste
# PostgreSQL bağladığımızda bunlar kalıcı olacak
all_posts = [
    {
        "username": "mehmet",
        "content": "Financhatting Sosyal terminali resmen açıldı! Buraya analizlerinizi yazabilirsiniz.",
        "stars": 4.5,
        "votes": 12,
        "time": "1 sa. önce"
    }
]

def get_financial_data():
    symbols = {
        'btc': 'BTC-USD', 'gold': 'GC=F', 'silver': 'SI=F',
        'usd_try': 'USDTRY=X', 'eur_try': 'EURTRY=X', 'bist100': '^XU100'
    }
    prices = {}
    try:
        for key, symbol in symbols.items():
            ticker = yf.Ticker(symbol)
            data = ticker.history(period='1d')
            if not data.empty:
                prices[key] = data['Close'].iloc[-1]
        
        if prices.get('gold') and prices.get('usd_try'):
            prices['gram_altin'] = (prices['gold'] / 31.1035) * prices['usd_try']
    except Exception as e:
        print(f"Hata: {e}")
    prices['timestamp'] = datetime.now().isoformat()
    return prices

@app.route('/')
def index():
    return render_template('index.html', page="markets")

@app.route('/feed')
def feed():
    return render_template('index.html', page="feed", posts=all_posts)

@app.route('/kesfet')
def kesfet():
    # En çok oylananları üste çekmek için basit sıralama
    trending = sorted(all_posts, key=lambda x: x['votes'], reverse=True)
    return render_template('index.html', page="explore", posts=trending)

@app.route('/@<username>')
def profile(username):
    user_posts = [p for p in all_posts if p['username'] == username]
    return render_template('index.html', page="profile", username=username, posts=user_posts)

@app.route('/post', methods=['POST'])
def create_post():
    content = request.form.get('content')
    if content and len(content.strip()) > 0:
        new_post = {
            "username": "mehmet", # Giriş sistemi gelene kadar senin adınla paylaşır
            "content": content,
            "stars": 0,
            "votes": 0,
            "time": "Şimdi"
        }
        all_posts.insert(0, new_post) # Yeni postu en başa ekle
    return redirect(url_for('feed'))

@app.route('/api/prices')
def prices():
    return jsonify(get_financial_data())

@app.route('/api/calendar')
def calendar():
    data = {
        "fed_rate": {"current": 4.50},
        "inflation": {"value": "44.2%"}
    }
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True)
