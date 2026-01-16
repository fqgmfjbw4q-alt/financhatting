import os
import yfinance as yf
from flask import Flask, jsonify, send_from_directory, request, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder='.', template_folder='.')

# GÜVENLİK: Belirlediğin '342Mstf3422' anahtarı sistemde tanımlı değilse varsayılan olarak kullanılır
app.secret_key = os.environ.get('SECRET_KEY', '342Mstf3422')

# GÜVENLİK: financhatting.com ve yerel test ortamı için erişim izinleri
CORS(app, supports_credentials=True, resources={
    r"/api/*": {
        "origins": ["https://financhatting.com", "https://www.financhatting.com", "http://localhost:5000"],
        "methods": ["GET", "POST", "OPTIONS", "PUT", "DELETE"],
        "allow_headers": ["Content-Type"],
        "supports_credentials": True
    }
})

# Veritabanı ve Oturum Güvenliği
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

db = SQLAlchemy(app)

# --- MODELLER (Aynen korundu) ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(500), default='')
    avatar = db.Column(db.String(10), default='👤')
    profile_image = db.Column(db.Text, default=None)
    joined_date = db.Column(db.DateTime, default=datetime.now)
    total_posts = db.Column(db.Integer, default=0)
    total_comments = db.Column(db.Integer, default=0)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    likes = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(80))
    avatar = db.Column(db.String(10), default='👤')
    comment_count = db.Column(db.Integer, default=0)
    rating_sum = db.Column(db.Integer, default=0)
    rating_count = db.Column(db.Integer, default=0)

class PostComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(80))
    avatar = db.Column(db.String(10), default='👤')
    rating_sum = db.Column(db.Integer, default=0)
    rating_count = db.Column(db.Integer, default=0)

class AssetComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_symbol = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(80))
    avatar = db.Column(db.String(10), default='👤')
    rating_sum = db.Column(db.Integer, default=0)
    rating_count = db.Column(db.Integer, default=0)

with app.app_context():
    db.create_all()

# --- EKONOMİK VERİ VE API ---
@app.route('/api/market-data')
def get_market_data():
    try:
        symbols = ["GC=F", "USDTRY=X", "BTC-USD", "ETH-USD"]
        data = yf.download(symbols, period="1d", interval="1m", progress=False, auto_adjust=True)
        last_row = data['Close'].ffill().iloc[-1]
        usd, ons, btc, eth = float(last_row['USDTRY=X']), float(last_row['GC=F']), float(last_row['BTC-USD']), float(last_row['ETH-USD'])
        gram = (ons / 31.1035) * usd
        return jsonify({
            'gold_ons': {'name': 'Altın Ons', 'value': f"${ons:,.2f}"},
            'gold_gram': {'name': 'Gram Altın', 'value': f"{gram:,.2f} ₺"},
            'usdtry': {'name': 'Dolar/TL', 'value': f"{usd:,.2f} ₺"},
            'bitcoin': {'name': 'Bitcoin', 'value': f"${btc:,.0f}"},
            'ethereum': {'name': 'Ethereum', 'value': f"${eth:,.2f}"}
        })
    except:
        return jsonify({'error': 'Veri çekilemedi'}), 500

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Bu kullanıcı adı dolu'}), 400
    user = User(full_name=data.get('full_name', 'FinanChatting Üyesi'), username=data['username'], password=generate_password_hash(data['password']))
    db.session.add(user); db.session.commit()
    return jsonify({'success': True})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    u = User.query.filter_by(username=data['username']).first()
    if u and check_password_hash(u.password, data['password']):
        session['user_id'], session['username'] = u.id, u.username
        return jsonify({'username': u.username, 'avatar': u.avatar})
    return jsonify({'error': 'Giriş hatalı'}), 401

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    # Render için port ayarı
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
