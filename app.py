import os
import yfinance as yf
from flask import Flask, jsonify, send_from_directory, request, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder='.', template_folder='.')
app.secret_key = os.environ.get('SECRET_KEY', 'finans_gold_master_2026_super_secret_key_123456')

# CORS - Railway için tüm origin'lere izin
CORS(app, supports_credentials=True, resources={
    r"/api/*": {
        "origins": ["*"],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type"],
        "supports_credentials": True
    }
})

basedir = os.path.abspath(os.path.dirname(__file__))
# Railway için geçici klasör kullan
db_path = '/tmp/database.db' if os.environ.get('RAILWAY_ENVIRONMENT') else os.path.join(basedir, 'database.db')
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
    profile_image = db.Column(db.Text, default=None)  # Base64 encoded image
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

# Veritabanını başlat
with app.app_context():
    try:
        db.create_all()
        print("✅ Veritabanı hazır!")
    except Exception as e:
        print(f"⚠️ Veritabanı hatası (normal olabilir): {e}")

# Health check endpoints for Railway
@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'service': 'finans-network-master'}), 200

@app.route('/api/ping')
def ping():
    return jsonify({'message': 'pong', 'timestamp': datetime.now().isoformat()}), 200

# --- SEMBOL HARITALAMA ---
SYMBOL_MAP = {
    'gold_ons': 'GC=F',
    'gold_gram': 'GC=F',
    'usdtry': 'USDTRY=X',
    'bitcoin': 'BTC-USD',
    'ethereum': 'ETH-USD'
}

# --- EKONOMİK TAKVİM VE MAKRO VERİLER ---
@app.route('/api/economic-calendar')
def get_economic_calendar():
    try:
        print("📅 Ekonomik takvim istendi...")
        # Bu veriler gerçek API'lerden çekilebilir, şimdilik güncel tahminler
        calendar = {
            'fed_rate': {
                'name': 'FED Faiz Oranı',
                'current': '4.25% - 4.50%',
                'next_meeting': '29 Ocak 2025',
                'icon': '🏦',
                'color': '#10b981',
                'description': 'Federal Reserve Para Politikası Toplantısı'
            },
            'tcmb_rate': {
                'name': 'TCMB Faiz Oranı',
                'current': '47.50%',
                'next_meeting': '23 Ocak 2025',
                'icon': '🇹🇷',
                'color': '#ef4444',
                'description': 'Türkiye Cumhuriyet Merkez Bankası PPK Toplantısı'
            },
            'us_inflation': {
                'name': 'ABD Enflasyon (CPI)',
                'current': '2.7% (Aralık)',
                'next_release': '12 Şubat 2025',
                'icon': '📊',
                'color': '#f59e0b',
                'description': 'Tüketici Fiyat Endeksi - Ocak Verisi'
            },
            'us_jobs': {
                'name': 'ABD İstihdam Verisi',
                'current': '256K (Aralık)',
                'next_release': '7 Şubat 2025',
                'icon': '👔',
                'color': '#8b5cf6',
                'description': 'Tarım Dışı İstihdam (NFP) - Ocak Verisi'
            },
            'tr_inflation': {
                'name': 'Türkiye Enflasyon',
                'current': '44.38% (Aralık)',
                'next_release': '3 Şubat 2025',
                'icon': '📈',
                'color': '#ec4899',
                'description': 'TÜFE Yıllık - Ocak Verisi'
            },
            'ecb_rate': {
                'name': 'ECB Faiz Oranı',
                'current': '3.15%',
                'next_meeting': '30 Ocak 2025',
                'icon': '🇪🇺',
                'color': '#06b6d4',
                'description': 'Avrupa Merkez Bankası Para Politikası Kararı'
            }
        }
        print("✅ Ekonomik takvim başarılı!")
        return jsonify(calendar)
    except Exception as e:
        print(f"❌ Ekonomik takvim hatası: {e}")
        return jsonify({})

# --- CANLI MARKET DATA ---
@app.route('/api/market-data')
def get_market_data():
    try:
        print("📊 Market data istendi...")
        symbols = ["GC=F", "USDTRY=X", "BTC-USD", "ETH-USD"]
        data = yf.download(symbols, period="1d", interval="1m", progress=False, auto_adjust=True)
        
        last_row = data['Close'].ffill().iloc[-1]
        
        usd_val = float(last_row['USDTRY=X'])
        ons_val = float(last_row['GC=F'])
        btc_val = float(last_row['BTC-USD'])
        eth_val = float(last_row['ETH-USD'])
        
        gram_gold = (ons_val / 31.1035) * usd_val
        
        result = {
            'gold_ons': {'name': 'Altın Ons', 'value': f"${ons_val:,.2f}", 'logo': '🟡'},
            'gold_gram': {'name': 'Gram Altın', 'value': f"{gram_gold:,.2f} ₺", 'logo': '🟨'},
            'usdtry': {'name': 'Dolar/TL', 'value': f"{usd_val:,.2f} ₺", 'logo': '💲'},
            'bitcoin': {'name': 'Bitcoin', 'value': f"${btc_val:,.0f}", 'logo': '🟠'},
            'ethereum': {'name': 'Ethereum', 'value': f"${eth_val:,.2f}", 'logo': '🔵'}
        }
        print("✅ Market data başarılı!")
        return jsonify(result)
    except Exception as e:
        print(f"❌ Market data hatası: {e}")
        return jsonify({
            'gold_ons': {'name': 'Altın Ons', 'value': "$2,652.10", 'logo': '🟡'},
            'gold_gram': {'name': 'Gram Altın', 'value': "6,226.40 ₺", 'logo': '🟨'},
            'usdtry': {'name': 'Dolar/TL', 'value': "35.80 ₺", 'logo': '💲'},
            'bitcoin': {'name': 'Bitcoin', 'value': "$95,800", 'logo': '🟠'},
            'ethereum': {'name': 'Ethereum', 'value': "$3,250", 'logo': '🔵'}
        })

# --- CANDLESTICK GRAFİK VERİSİ ---
@app.route('/api/candlestick/<symbol>')
def get_candlestick(symbol):
    try:
        print(f"📈 Candlestick istendi: {symbol}")
        period_type = request.args.get('period', 'daily')
        yahoo_symbol = SYMBOL_MAP.get(symbol, 'BTC-USD')
        
        if period_type == 'daily':
            period = "1y"  # 1 yıl günlük
            interval = "1d"
        elif period_type == 'weekly':
            period = "3y"  # 3 yıl haftalık
            interval = "1wk"
        else:  # monthly
            period = "5y"  # 5 yıl aylık
            interval = "1mo"
        
        ticker = yf.Ticker(yahoo_symbol)
        hist = ticker.history(period=period, interval=interval)
        
        if hist.empty:
            return jsonify({'error': 'Veri bulunamadı'}), 404
        
        if symbol == 'gold_gram':
            try:
                usd_data = yf.download("USDTRY=X", period="1d", interval="1m", progress=False)
                usd_rate = float(usd_data['Close'].ffill().iloc[-1])
                hist['Open'] = (hist['Open'] / 31.1035) * usd_rate
                hist['High'] = (hist['High'] / 31.1035) * usd_rate
                hist['Low'] = (hist['Low'] / 31.1035) * usd_rate
                hist['Close'] = (hist['Close'] / 31.1035) * usd_rate
            except:
                pass
        
        candlestick_data = []
        for index, row in hist.iterrows():
            candlestick_data.append({
                'time': index.strftime('%Y-%m-%d'),
                'open': round(float(row['Open']), 2),
                'high': round(float(row['High']), 2),
                'low': round(float(row['Low']), 2),
                'close': round(float(row['Close']), 2),
                'volume': int(row['Volume']) if 'Volume' in row else 0
            })
        
        print(f"✅ Candlestick başarılı: {len(candlestick_data)} veri")
        return jsonify({
            'symbol': symbol,
            'period': period_type,
            'data': candlestick_data
        })
        
    except Exception as e:
        print(f"❌ Candlestick hatası: {e}")
        return jsonify({'error': str(e)}), 500

# --- KULLANICI KAYIT & GİRİŞ ---
@app.route('/api/register', methods=['POST', 'OPTIONS'])
def register():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.json
        print(f"📝 Kayıt denemesi: {data.get('username')}")
        
        if not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Kullanıcı adı ve şifre gerekli'}), 400
        
        if User.query.filter_by(username=data['username']).first():
            print(f"❌ Kullanıcı adı alınmış: {data['username']}")
            return jsonify({'error': 'Bu kullanıcı adı alınmış'}), 400
        
        avatars = ['👤', '😎', '🚀', '💎', '🎯', '⚡', '🔥', '🌟', '💰', '🦁']
        import random
        avatar = random.choice(avatars)
        
        user = User(
            full_name=data.get('full_name', 'İsimsiz Kullanıcı'),
            username=data['username'],
            password=generate_password_hash(data['password']),
            avatar=avatar
        )
        db.session.add(user)
        db.session.commit()
        
        print(f"✅ Kayıt başarılı: {data['username']}")
        return jsonify({'success': True, 'message': 'Kayıt başarılı!'})
    except Exception as e:
        print(f"❌ Kayıt hatası: {e}")
        db.session.rollback()
        return jsonify({'error': f'Kayıt hatası: {str(e)}'}), 500

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        data = request.json
        print(f"🔐 Giriş denemesi: {data.get('username')}")
        
        if not data.get('username') or not data.get('password'):
            return jsonify({'error': 'Kullanıcı adı ve şifre gerekli'}), 400
        
        u = User.query.filter_by(username=data['username']).first()
        
        if u and check_password_hash(u.password, data['password']):
            session['user_id'] = u.id
            session['username'] = u.username
            session['avatar'] = u.avatar
            print(f"✅ Giriş başarılı: {u.username}")
            return jsonify({'username': u.username, 'avatar': u.avatar})
        
        print(f"❌ Giriş başarısız: {data.get('username')}")
        return jsonify({'error': 'Kullanıcı adı veya şifre hatalı'}), 401
    except Exception as e:
        print(f"❌ Giriş hatası: {e}")
        return jsonify({'error': f'Giriş hatası: {str(e)}'}), 500

@app.route('/api/check-session')
def check_session():
    if 'username' in session:
        return jsonify({
            'logged_in': True,
            'username': session['username'],
            'avatar': session.get('avatar', '👤')
        })
    return jsonify({'logged_in': False})

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})

# --- PROFİL SİSTEMİ ---
@app.route('/api/profile/<username>')
def get_profile(username):
    try:
        user = User.query.filter_by(username=username).first()
        if not user:
            return jsonify({'error': 'Kullanıcı bulunamadı'}), 404
        
        posts = Post.query.filter_by(user_id=user.id).order_by(Post.timestamp.desc()).all()
        
        return jsonify({
            'username': user.username,
            'full_name': user.full_name,
            'bio': user.bio,
            'avatar': user.avatar,
            'profile_image': user.profile_image,
            'joined_date': user.joined_date.strftime('%Y-%m-%d'),
            'total_posts': user.total_posts,
            'total_comments': user.total_comments,
            'posts': [{
                'id': p.id,
                'content': p.content,
                'timestamp': p.timestamp.strftime('%Y-%m-%d %H:%M'),
                'likes': p.likes,
                'comment_count': p.comment_count,
                'avatar': p.avatar,
                'rating_avg': round(p.rating_sum / p.rating_count, 1) if (p.rating_count and p.rating_count > 0) else 0,
                'rating_count': p.rating_count if p.rating_count else 0
            } for p in posts]
        })
    except Exception as e:
        print(f"❌ Profil hatası: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        data = request.json
        user = User.query.get(session['user_id'])
        
        if 'bio' in data:
            user.bio = data['bio']
        if 'avatar' in data:
            user.avatar = data['avatar']
            session['avatar'] = data['avatar']
        if 'profile_image' in data:
            # Base64 image data
            user.profile_image = data['profile_image']
        if 'remove_image' in data and data['remove_image']:
            user.profile_image = None
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Profil güncelleme hatası: {e}")
        return jsonify({'error': str(e)}), 500

# --- GÖNDERI SİSTEMİ ---
@app.route('/api/post', methods=['POST', 'OPTIONS'])
def add_post():
    if request.method == 'OPTIONS':
        return '', 204
        
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        data = request.json
        print(f"📝 Yeni gönderi: {session['username']}")
        
        post = Post(
            content=data['content'],
            user_id=session['user_id'],
            username=session['username'],
            avatar=session.get('avatar', '👤')
        )
        db.session.add(post)
        
        user = User.query.get(session['user_id'])
        user.total_posts += 1
        
        db.session.commit()
        print(f"✅ Gönderi eklendi: ID {post.id}")
        return jsonify({'success': True, 'post_id': post.id})
    except Exception as e:
        print(f"❌ Post hatası: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/post/<int:post_id>', methods=['DELETE', 'OPTIONS'])
def delete_post(post_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        post = Post.query.get(post_id)
        if not post:
            return jsonify({'error': 'Gönderi bulunamadı'}), 404
        
        if post.user_id != session['user_id']:
            return jsonify({'error': 'Bu gönderiyi silme yetkiniz yok'}), 403
        
        # İlgili yorumları da sil
        PostComment.query.filter_by(post_id=post_id).delete()
        
        db.session.delete(post)
        
        user = User.query.get(session['user_id'])
        user.total_posts = max(0, user.total_posts - 1)
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Post silme hatası: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/post/<int:post_id>', methods=['PUT', 'OPTIONS'])
def edit_post(post_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        post = Post.query.get(post_id)
        if not post:
            return jsonify({'error': 'Gönderi bulunamadı'}), 404
        
        if post.user_id != session['user_id']:
            return jsonify({'error': 'Bu gönderiyi düzenleme yetkiniz yok'}), 403
        
        data = request.json
        post.content = data['content']
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Post düzenleme hatası: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/feed')
def get_feed():
    try:
        posts = Post.query.order_by(Post.timestamp.desc()).limit(50).all()
        return jsonify([{
            'id': p.id,
            'user': p.username,
            'avatar': p.avatar,
            'content': p.content,
            'likes': p.likes,
            'comment_count': p.comment_count,
            'timestamp': p.timestamp.strftime('%Y-%m-%d %H:%M'),
            'rating_avg': round(p.rating_sum / p.rating_count, 1) if (p.rating_count and p.rating_count > 0) else 0,
            'rating_count': p.rating_count if p.rating_count else 0
        } for p in posts])
    except Exception as e:
        print(f"❌ Feed hatası: {e}")
        return jsonify([])

# --- POST RATING SİSTEMİ ---
@app.route('/api/rate-post', methods=['POST', 'OPTIONS'])
def rate_post():
    if request.method == 'OPTIONS':
        return '', 204
        
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        data = request.json
        post = Post.query.get(data['post_id'])
        rating = int(data['rating'])
        
        if rating < 1 or rating > 5:
            return jsonify({'error': 'Geçersiz oy'}), 400
        
        post.rating_sum += rating
        post.rating_count += 1
        
        db.session.commit()
        
        avg = round(post.rating_sum / post.rating_count, 1)
        return jsonify({'success': True, 'rating_avg': avg, 'rating_count': post.rating_count})
    except Exception as e:
        print(f"❌ Post rating hatası: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# --- POST YORUM SİSTEMİ ---
@app.route('/api/post-comments/<int:post_id>')
def get_post_comments(post_id):
    try:
        comments = PostComment.query.filter_by(post_id=post_id).order_by(PostComment.timestamp.desc()).all()
        return jsonify([{
            'id': c.id,
            'username': c.username,
            'avatar': c.avatar,
            'content': c.content,
            'timestamp': c.timestamp.strftime('%Y-%m-%d %H:%M'),
            'rating_avg': round(c.rating_sum / c.rating_count, 1) if (c.rating_count and c.rating_count > 0) else 0,
            'rating_count': c.rating_count if c.rating_count else 0
        } for c in comments])
    except Exception as e:
        print(f"❌ Post yorum yükleme hatası: {e}")
        return jsonify([])

@app.route('/api/rate-post-comment', methods=['POST', 'OPTIONS'])
def rate_post_comment():
    if request.method == 'OPTIONS':
        return '', 204
        
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        data = request.json
        comment = PostComment.query.get(data['comment_id'])
        rating = int(data['rating'])
        
        if rating < 1 or rating > 5:
            return jsonify({'error': 'Geçersiz oy'}), 400
        
        comment.rating_sum += rating
        comment.rating_count += 1
        
        db.session.commit()
        
        avg = round(comment.rating_sum / comment.rating_count, 1)
        return jsonify({'success': True, 'rating_avg': avg, 'rating_count': comment.rating_count})
    except Exception as e:
        print(f"❌ Comment rating hatası: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/post-comment', methods=['POST', 'OPTIONS'])
def add_post_comment():
    if request.method == 'OPTIONS':
        return '', 204
        
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        data = request.json
        comment = PostComment(
            post_id=data['post_id'],
            content=data['content'],
            user_id=session['user_id'],
            username=session['username'],
            avatar=session.get('avatar', '👤')
        )
        db.session.add(comment)
        
        # Post yorum sayısını güncelle
        post = Post.query.get(data['post_id'])
        post.comment_count += 1
        
        # Kullanıcı istatistiklerini güncelle
        user = User.query.get(session['user_id'])
        user.total_comments += 1
        
        db.session.commit()
        print(f"✅ Post yorumu eklendi: Post #{data['post_id']}")
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Post yorum ekleme hatası: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/post-comment/<int:comment_id>', methods=['DELETE', 'OPTIONS'])
def delete_post_comment(comment_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        comment = PostComment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Yorum bulunamadı'}), 404
        
        if comment.user_id != session['user_id']:
            return jsonify({'error': 'Bu yorumu silme yetkiniz yok'}), 403
        
        post_id = comment.post_id
        
        db.session.delete(comment)
        
        post = Post.query.get(post_id)
        post.comment_count = max(0, post.comment_count - 1)
        
        user = User.query.get(session['user_id'])
        user.total_comments = max(0, user.total_comments - 1)
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Yorum silme hatası: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/asset-comment/<int:comment_id>', methods=['DELETE', 'OPTIONS'])
def delete_asset_comment(comment_id):
    if request.method == 'OPTIONS':
        return '', 204
        
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        comment = AssetComment.query.get(comment_id)
        if not comment:
            return jsonify({'error': 'Yorum bulunamadı'}), 404
        
        if comment.user_id != session['user_id']:
            return jsonify({'error': 'Bu yorumu silme yetkiniz yok'}), 403
        
        db.session.delete(comment)
        
        user = User.query.get(session['user_id'])
        user.total_comments = max(0, user.total_comments - 1)
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Varlık yorumu silme hatası: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

# --- VARLIK YORUM SİSTEMİ ---
@app.route('/api/asset-comments/<symbol>')
def get_asset_comments(symbol):
    try:
        comments = AssetComment.query.filter_by(asset_symbol=symbol).order_by(AssetComment.timestamp.desc()).limit(50).all()
        return jsonify([{
            'id': c.id,
            'username': c.username,
            'avatar': c.avatar,
            'content': c.content,
            'timestamp': c.timestamp.strftime('%Y-%m-%d %H:%M'),
            'rating_avg': round(c.rating_sum / c.rating_count, 1) if (c.rating_count and c.rating_count > 0) else 0,
            'rating_count': c.rating_count if c.rating_count else 0
        } for c in comments])
    except Exception as e:
        print(f"❌ Yorum yükleme hatası: {e}")
        return jsonify([])

@app.route('/api/rate-asset-comment', methods=['POST', 'OPTIONS'])
def rate_asset_comment():
    if request.method == 'OPTIONS':
        return '', 204
        
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        data = request.json
        comment = AssetComment.query.get(data['comment_id'])
        rating = int(data['rating'])
        
        if rating < 1 or rating > 5:
            return jsonify({'error': 'Geçersiz oy'}), 400
        
        comment.rating_sum += rating
        comment.rating_count += 1
        
        db.session.commit()
        
        avg = round(comment.rating_sum / comment.rating_count, 1)
        return jsonify({'success': True, 'rating_avg': avg, 'rating_count': comment.rating_count})
    except Exception as e:
        print(f"❌ Comment rating hatası: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/api/asset-comment', methods=['POST', 'OPTIONS'])
def add_asset_comment():
    if request.method == 'OPTIONS':
        return '', 204
        
    if 'user_id' not in session:
        return jsonify({'error': 'Giriş yapmalısınız'}), 401
    
    try:
        data = request.json
        comment = AssetComment(
            asset_symbol=data['symbol'],
            content=data['content'],
            user_id=session['user_id'],
            username=session['username'],
            avatar=session.get('avatar', '👤')
        )
        db.session.add(comment)
        
        user = User.query.get(session['user_id'])
        user.total_comments += 1
        
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        print(f"❌ Yorum ekleme hatası: {e}")
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

if __name__ == '__main__':
    print("🚀 Flask sunucusu başlatılıyor...")
    port = int(os.environ.get('PORT', 5000))
    print(f"📍 Port: {port}")
    app.run(debug=False, port=port, host='0.0.0.0')
