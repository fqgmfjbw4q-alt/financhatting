import os
import yfinance as yf
from flask import Flask, jsonify, send_from_directory, request, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder='.', template_folder='.')
app.secret_key = os.environ.get('SECRET_KEY', 'finans_gold_master_2026_super_secret_key_123456')

# CORS - Railway ve Localhost uyumlu ayar
CORS(app, supports_credentials=True)

basedir = os.path.abspath(os.path.dirname(__file__))
# Railway'de verilerin silinmemesi için yerel dizini kullanıyoruz
db_path = os.path.join(basedir, 'database.db')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + db_path
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_HTTPONLY'] = True

db = SQLAlchemy(app)

# --- DATABASE MODELLERİ ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(500), default='')
    avatar = db.Column(db.String(10), default='👤')
    profile_image = db.Column(db.Text, default=None)
    joined_date = db.Column(db.DateTime, default=datetime.utcnow)
    total_posts = db.Column(db.Integer, default=0)
    total_comments = db.Column(db.Integer, default=0)

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
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
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(80))
    avatar = db.Column(db.String(10), default='👤')
    rating_sum = db.Column(db.Integer, default=0)
    rating_count = db.Column(db.Integer, default=0)

class AssetComment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    asset_symbol = db.Column(db.String(50), nullable=False)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    username = db.Column(db.String(80))
    avatar = db.Column(db.String(10), default='👤')
    rating_sum = db.Column(db.Integer, default=0)
    rating_count = db.Column(db.Integer, default=0)

with app.app_context():
    db.create_all()
    print("✅ Veritabanı ve Modeller Railway üzerinde hazır!")

# --- SEMBOL HARITALAMA ---
SYMBOL_MAP = {
    'gold_ons': 'GC=F',
    'gold_gram': 'GC=F',
    'usdtry': 'USDTRY=X',
    'bitcoin': 'BTC-USD',
    'ethereum': 'ETH-USD'
}

# --- ROUTES ---
@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/api/check-session')
def check_session():
    if 'username' in session:
        return jsonify({'logged_in': True, 'username': session['username'], 'avatar': session.get('avatar', '👤')})
    return jsonify({'logged_in': False})

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({'error': 'Bu kullanıcı adı alınmış'}), 400
    user = User(
        full_name=data.get('full_name', 'İsimsiz Kullanıcı'),
        username=data['username'],
        password=generate_password_hash(data['password'])
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    u = User.query.filter_by(username=data['username']).first()
    if u and check_password_hash(u.password, data['password']):
        session['user_id'] = u.id
        session['username'] = u.username
        session['avatar'] = u.avatar
        return jsonify({'username': u.username, 'avatar': u.avatar})
    return jsonify({'error': 'Hatalı giriş'}), 401

@app.route('/api/market-data')
def get_market_data():
    try:
        symbols = ["GC=F", "USDTRY=X", "BTC-USD", "ETH-USD"]
        data = yf.download(symbols, period="1d", interval="1m", progress=False, auto_adjust=True)
        last_row = data['Close'].ffill().iloc[-1]
        usd_val = float(last_row['USDTRY=X'])
        ons_val = float(last_row['GC=F'])
        gram_gold = (ons_val / 31.1035) * usd_val
        return jsonify({
            'gold_ons': {'name': 'Altın Ons', 'value': f"${ons_val:,.2f}", 'logo': '🟡'},
            'gold_gram': {'name': 'Gram Altın', 'value': f"{gram_gold:,.2f} ₺", 'logo': '🟨'},
            'usdtry': {'name': 'Dolar/TL', 'value': f"{usd_val:,.2f} ₺", 'logo': '💲'},
            'bitcoin': {'name': 'Bitcoin', 'value': f"${float(last_row['BTC-USD']):,.0f}", 'logo': '🟠'},
            'ethereum': {'name': 'Ethereum', 'value': f"${float(last_row['ETH-USD']):,.2f}", 'logo': '🔵'}
        })
    except:
        return jsonify({'error': 'Veri alınamadı'}), 500

@app.route('/api/feed')
def get_feed():
    posts = Post.query.order_by(Post.timestamp.desc()).limit(50).all()
    return jsonify([{
        'id': p.id, 'user': p.username, 'content': p.content, 'avatar': p.avatar,
        'timestamp': p.timestamp.strftime('%Y-%m-%d %H:%M'),
        'comment_count': p.comment_count
    } for p in posts])

@app.route('/api/post', methods=['POST'])
def add_post():
    if 'user_id' not in session: return jsonify({'error': 'Giriş gerekli'}), 401
    data = request.json
    post = Post(content=data['content'], user_id=session['user_id'], username=session['username'], avatar=session.get('avatar', '👤'))
    db.session.add(post)
    db.session.commit()
    return jsonify({'success': True})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

# Statik dosyalar için
@app.route('/<path:path>')
def static_files(path):
    return send_from_directory('.', path)

if __name__ == '__main__':
    # Railway için port ayarı
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
