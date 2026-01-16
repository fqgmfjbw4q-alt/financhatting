import os
import logging
from datetime import datetime, timedelta

import yfinance as yf
from flask import Flask, jsonify, send_from_directory, request, session
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=".", static_url_path="")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# --- Production cookie/session settings ---
is_prod = os.environ.get("FLASK_ENV") == "production"
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=is_prod,      # prod/https -> True
    SESSION_COOKIE_SAMESITE="Lax",      # same-origin SPA için iyi
    PERMANENT_SESSION_LIFETIME=timedelta(days=1),
)

# --- CORS ---
CORS(
    app,
    resources={r"/api/*": {"origins": "*"}},
    supports_credentials=True,
    allow_headers=["Content-Type"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
)

# --- DB ---
DATABASE_URL = os.environ.get("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL:
    app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(basedir, 'database.db')}"

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}

db = SQLAlchemy(app)

# --- MODELS ---
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(100))
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password = db.Column(db.String(200), nullable=False)
    bio = db.Column(db.String(500), default="")
    avatar = db.Column(db.String(10), default="👤")
    profile_image = db.Column(db.Text)
    joined_date = db.Column(db.DateTime, default=datetime.utcnow)
    total_posts = db.Column(db.Integer, default=0)
    total_comments = db.Column(db.Integer, default=0)


class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    likes = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    username = db.Column(db.String(80))
    avatar = db.Column(db.String(10), default="👤")
    comment_count = db.Column(db.Integer, default=0)
    rating_sum = db.Column(db.Integer, default=0)
    rating_count = db.Column(db.Integer, default=0)


class PostComment(db.Model):
    __tablename__ = "post_comments"
    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("posts.id"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    username = db.Column(db.String(80))
    avatar = db.Column(db.String(10), default="👤")
    rating_sum = db.Column(db.Integer, default=0)
    rating_count = db.Column(db.Integer, default=0)


class AssetComment(db.Model):
    __tablename__ = "asset_comments"
    id = db.Column(db.Integer, primary_key=True)
    asset_symbol = db.Column(db.String(50), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    username = db.Column(db.String(80))
    avatar = db.Column(db.String(10), default="👤")
    rating_sum = db.Column(db.Integer, default=0)
    rating_count = db.Column(db.Integer, default=0)


_db_inited = False

@app.before_request
def init_db_once():
    global _db_inited
    if _db_inited:
        return
    try:
        db.create_all()
        _db_inited = True
        logger.info("✅ DB ready")
    except Exception as e:
        logger.error(f"❌ DB init error: {e}")


# --- SYMBOL MAP ---
SYMBOL_MAP = {
    "gold_ons": "GC=F",
    "gold_gram": "GC=F",
    "usdtry": "USDTRY=X",
    "bitcoin": "BTC-USD",
    "ethereum": "ETH-USD",
}

# --- STATIC ---
@app.get("/")
def index():
    return send_from_directory(".", "index.html")

@app.get("/<path:path>")
def serve_static(path):
    full_path = os.path.join(os.path.dirname(__file__), path)
    if os.path.isfile(full_path):
        return send_from_directory(".", path)
    return send_from_directory(".", "index.html")

# --- HEALTH ---
@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "time": datetime.utcnow().isoformat()})

# --- ECONOMIC CALENDAR (static) ---
@app.get("/api/economic-calendar")
def economic_calendar():
    cal = {
        "fed_rate": {
            "name": "FED Faiz Oranı",
            "current": "4.25% - 4.50%",
            "next_meeting": "29 Ocak 2025",
            "icon": "🏦",
            "color": "#10b981",
            "description": "Federal Reserve Para Politikası Toplantısı",
        },
        "tcmb_rate": {
            "name": "TCMB Faiz Oranı",
            "current": "47.50%",
            "next_meeting": "23 Ocak 2025",
            "icon": "🇹🇷",
            "color": "#ef4444",
            "description": "TCMB PPK Toplantısı",
        },
        "us_inflation": {
            "name": "ABD Enflasyon (CPI)",
            "current": "2.7% (Aralık)",
            "next_release": "12 Şubat 2025",
            "icon": "📊",
            "color": "#f59e0b",
            "description": "TÜFE - Ocak Verisi",
        },
        "us_jobs": {
            "name": "ABD İstihdam Verisi",
            "current": "256K (Aralık)",
            "next_release": "7 Şubat 2025",
            "icon": "👔",
            "color": "#8b5cf6",
            "description": "Tarım Dışı İstihdam (NFP) - Ocak",
        },
        "tr_inflation": {
            "name": "Türkiye Enflasyon",
            "current": "44.38% (Aralık)",
            "next_release": "3 Şubat 2025",
            "icon": "📈",
            "color": "#ec4899",
            "description": "TÜFE Yıllık - Ocak",
        },
        "ecb_rate": {
            "name": "ECB Faiz Oranı",
            "current": "3.15%",
            "next_meeting": "30 Ocak 2025",
            "icon": "🇪🇺",
            "color": "#06b6d4",
            "description": "ECB Para Politikası Kararı",
        },
    }
    return jsonify(cal)

# --- AUTH ---
@app.post("/api/register")
def register():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    full_name = data.get("full_name") or "İsimsiz Kullanıcı"

    if not username or not password:
        return jsonify({"error": "Kullanıcı adı ve şifre gerekli"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Bu kullanıcı adı alınmış"}), 400

    import random
    avatars = ["👤", "😎", "🚀", "💎", "🎯", "⚡", "🔥", "🌟", "💰", "🦁"]

    user = User(
        full_name=full_name,
        username=username,
        password=generate_password_hash(password),
        avatar=random.choice(avatars),
    )
    db.session.add(user)
    db.session.commit()
    return jsonify({"success": True})


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Kullanıcı adı ve şifre gerekli"}), 400

    user = User.query.filter_by(username=username).first()
    if user and check_password_hash(user.password, password):
        session.permanent = True
        session["user_id"] = user.id
        session["username"] = user.username
        session["avatar"] = user.avatar
        return jsonify({"username": user.username, "avatar": user.avatar})

    return jsonify({"error": "Kullanıcı adı veya şifre hatalı"}), 401


@app.get("/api/check-session")
def check_session():
    if "user_id" in session:
        return jsonify(
            {
                "logged_in": True,
                "username": session.get("username"),
                "avatar": session.get("avatar", "👤"),
            }
        )
    return jsonify({"logged_in": False})


@app.post("/api/logout")
def logout():
    session.clear()
    return jsonify({"success": True})

# --- PROFILE ---
@app.get("/api/profile/<username>")
def profile(username):
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "Kullanıcı bulunamadı"}), 404

    posts = Post.query.filter_by(user_id=user.id).order_by(Post.timestamp.desc()).all()

    return jsonify(
        {
            "username": user.username,
            "full_name": user.full_name,
            "bio": user.bio,
            "avatar": user.avatar,
            "profile_image": user.profile_image,
            "joined_date": user.joined_date.strftime("%Y-%m-%d"),
            "total_posts": user.total_posts,
            "total_comments": user.total_comments,
            "posts": [
                {
                    "id": p.id,
                    "content": p.content,
                    "timestamp": p.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "likes": p.likes,
                    "comment_count": p.comment_count,
                    "avatar": p.avatar,
                    "rating_avg": round(p.rating_sum / p.rating_count, 1) if p.rating_count else 0,
                    "rating_count": p.rating_count or 0,
                }
                for p in posts
            ],
        }
    )


@app.post("/api/profile/update")
def profile_update():
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    data = request.get_json(silent=True) or {}
    user = User.query.get(session["user_id"])

    try:
        if "bio" in data:
            user.bio = data.get("bio") or ""

        if data.get("remove_image"):
            user.profile_image = None

        if "profile_image" in data and data["profile_image"]:
            user.profile_image = data["profile_image"]
            user.avatar = ""

        if "avatar" in data and data["avatar"] is not None:
            user.avatar = data["avatar"]
            session["avatar"] = user.avatar

        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"❌ profile update: {e}")
        db.session.rollback()
        return jsonify({"error": "Profil güncellenemedi"}), 500

# --- MARKET DATA ---
@app.get("/api/market-data")
def market_data():
    try:
        symbols = ["GC=F", "USDTRY=X", "BTC-USD", "ETH-USD"]
        data = yf.download(symbols, period="1d", interval="1m", progress=False, auto_adjust=True)
        last_row = data["Close"].ffill().iloc[-1]

        usd_val = float(last_row["USDTRY=X"])
        ons_val = float(last_row["GC=F"])
        btc_val = float(last_row["BTC-USD"])
        eth_val = float(last_row["ETH-USD"])

        gram_gold = (ons_val / 31.1035) * usd_val

        return jsonify(
            {
                "gold_ons": {"name": "Altın Ons", "value": f"${ons_val:,.2f}", "logo": "🟡"},
                "gold_gram": {"name": "Gram Altın", "value": f"{gram_gold:,.2f} ₺", "logo": "🟨"},
                "usdtry": {"name": "Dolar/TL", "value": f"{usd_val:,.2f} ₺", "logo": "💲"},
                "bitcoin": {"name": "Bitcoin", "value": f"${btc_val:,.0f}", "logo": "🟠"},
                "ethereum": {"name": "Ethereum", "value": f"${eth_val:,.2f}", "logo": "🔵"},
            }
        )
    except Exception as e:
        logger.error(f"❌ market-data: {e}")
        return jsonify({"error": "Veri alınamadı"}), 500

# --- CANDLESTICK ---
@app.get("/api/candlestick/<symbol>")
def candlestick(symbol):
    try:
        period_type = request.args.get("period", "daily")
        yahoo_symbol = SYMBOL_MAP.get(symbol, "BTC-USD")

        period_config = {
            "daily": ("1y", "1d"),
            "weekly": ("3y", "1wk"),
            "monthly": ("5y", "1mo"),
        }
        period, interval = period_config.get(period_type, ("1y", "1d"))

        ticker = yf.Ticker(yahoo_symbol)
        hist = ticker.history(period=period, interval=interval)

        if hist.empty:
            return jsonify({"error": "Veri bulunamadı"}), 404

        if symbol == "gold_gram":
            try:
                usd_data = yf.download("USDTRY=X", period="1d", interval="1m", progress=False)
                usd_rate = float(usd_data["Close"].ffill().iloc[-1])
                hist[["Open", "High", "Low", "Close"]] = (
                    hist[["Open", "High", "Low", "Close"]].div(31.1035).mul(usd_rate)
                )
            except:
                pass

        out = []
        for idx, row in hist.iterrows():
            out.append(
                {
                    "time": idx.strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]) if "Volume" in row and row["Volume"] == row["Volume"] else 0,
                }
            )

        return jsonify({"symbol": symbol, "period": period_type, "data": out})
    except Exception as e:
        logger.error(f"❌ candlestick: {e}")
        return jsonify({"error": "Grafik verisi alınamadı"}), 500

# --- FEED / POSTS ---
@app.get("/api/feed")
def feed():
    try:
        posts = Post.query.order_by(Post.timestamp.desc()).limit(60).all()
        return jsonify(
            [
                {
                    "id": p.id,
                    "user": p.username,
                    "avatar": p.avatar,
                    "content": p.content,
                    "likes": p.likes,
                    "comment_count": p.comment_count,
                    "timestamp": p.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "rating_avg": round(p.rating_sum / p.rating_count, 1) if p.rating_count else 0,
                    "rating_count": p.rating_count or 0,
                }
                for p in posts
            ]
        )
    except Exception as e:
        logger.error(f"❌ feed: {e}")
        return jsonify([])

@app.post("/api/post")
def add_post():
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "İçerik boş olamaz"}), 400

    try:
        post = Post(
            content=content,
            user_id=session["user_id"],
            username=session["username"],
            avatar=session.get("avatar", "👤"),
        )
        db.session.add(post)

        user = User.query.get(session["user_id"])
        user.total_posts += 1

        db.session.commit()
        return jsonify({"success": True, "post_id": post.id})
    except Exception as e:
        logger.error(f"❌ add_post: {e}")
        db.session.rollback()
        return jsonify({"error": "Gönderi eklenemedi"}), 500


@app.put("/api/post/<int:post_id>")
def edit_post(post_id):
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"error": "İçerik boş olamaz"}), 400

    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Gönderi bulunamadı"}), 404
    if post.user_id != session["user_id"]:
        return jsonify({"error": "Yetkiniz yok"}), 403

    post.content = content
    db.session.commit()
    return jsonify({"success": True})


@app.delete("/api/post/<int:post_id>")
def delete_post(post_id):
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Gönderi bulunamadı"}), 404
    if post.user_id != session["user_id"]:
        return jsonify({"error": "Yetkiniz yok"}), 403

    try:
        PostComment.query.filter_by(post_id=post_id).delete()
        db.session.delete(post)

        user = User.query.get(session["user_id"])
        user.total_posts = max(0, user.total_posts - 1)

        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"❌ delete_post: {e}")
        db.session.rollback()
        return jsonify({"error": "Silinemedi"}), 500


@app.post("/api/rate-post")
def rate_post():
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    data = request.get_json(silent=True) or {}
    post = Post.query.get(data.get("post_id"))
    rating = int(data.get("rating") or 0)
    if not post:
        return jsonify({"error": "Gönderi bulunamadı"}), 404
    if rating < 1 or rating > 5:
        return jsonify({"error": "Geçersiz oy"}), 400

    post.rating_sum += rating
    post.rating_count += 1
    db.session.commit()
    return jsonify({"success": True})

# --- POST COMMENTS ---
@app.get("/api/post-comments/<int:post_id>")
def get_post_comments(post_id):
    try:
        comments = PostComment.query.filter_by(post_id=post_id).order_by(PostComment.timestamp.desc()).all()
        return jsonify(
            [
                {
                    "id": c.id,
                    "username": c.username,
                    "avatar": c.avatar,
                    "content": c.content,
                    "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "rating_avg": round(c.rating_sum / c.rating_count, 1) if c.rating_count else 0,
                    "rating_count": c.rating_count or 0,
                }
                for c in comments
            ]
        )
    except Exception as e:
        logger.error(f"❌ get_post_comments: {e}")
        return jsonify([])


@app.post("/api/post-comment")
def add_post_comment():
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    data = request.get_json(silent=True) or {}
    post_id = int(data.get("post_id") or 0)
    content = (data.get("content") or "").strip()
    if not post_id or not content:
        return jsonify({"error": "Eksik veri"}), 400

    post = Post.query.get(post_id)
    if not post:
        return jsonify({"error": "Gönderi bulunamadı"}), 404

    try:
        c = PostComment(
            post_id=post_id,
            content=content,
            user_id=session["user_id"],
            username=session["username"],
            avatar=session.get("avatar", "👤"),
        )
        db.session.add(c)

        post.comment_count += 1
        user = User.query.get(session["user_id"])
        user.total_comments += 1

        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"❌ add_post_comment: {e}")
        db.session.rollback()
        return jsonify({"error": "Yorum eklenemedi"}), 500


@app.delete("/api/post-comment/<int:comment_id>")
def delete_post_comment(comment_id):
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    comment = PostComment.query.get(comment_id)
    if not comment:
        return jsonify({"error": "Yorum bulunamadı"}), 404
    if comment.user_id != session["user_id"]:
        return jsonify({"error": "Yetkiniz yok"}), 403

    try:
        post = Post.query.get(comment.post_id)
        if post:
            post.comment_count = max(0, post.comment_count - 1)

        user = User.query.get(session["user_id"])
        user.total_comments = max(0, user.total_comments - 1)

        db.session.delete(comment)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"❌ delete_post_comment: {e}")
        db.session.rollback()
        return jsonify({"error": "Silinemedi"}), 500


@app.post("/api/rate-post-comment")
def rate_post_comment():
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    data = request.get_json(silent=True) or {}
    comment = PostComment.query.get(data.get("comment_id"))
    rating = int(data.get("rating") or 0)
    if not comment:
        return jsonify({"error": "Yorum bulunamadı"}), 404
    if rating < 1 or rating > 5:
        return jsonify({"error": "Geçersiz oy"}), 400

    comment.rating_sum += rating
    comment.rating_count += 1
    db.session.commit()
    return jsonify({"success": True})

# --- ASSET COMMENTS ---
@app.get("/api/asset-comments/<symbol>")
def get_asset_comments(symbol):
    try:
        comments = AssetComment.query.filter_by(asset_symbol=symbol).order_by(AssetComment.timestamp.desc()).limit(60).all()
        return jsonify(
            [
                {
                    "id": c.id,
                    "username": c.username,
                    "avatar": c.avatar,
                    "content": c.content,
                    "timestamp": c.timestamp.strftime("%Y-%m-%d %H:%M"),
                    "rating_avg": round(c.rating_sum / c.rating_count, 1) if c.rating_count else 0,
                    "rating_count": c.rating_count or 0,
                }
                for c in comments
            ]
        )
    except Exception as e:
        logger.error(f"❌ get_asset_comments: {e}")
        return jsonify([])


@app.post("/api/asset-comment")
def add_asset_comment():
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    data = request.get_json(silent=True) or {}
    symbol = (data.get("symbol") or "").strip()
    content = (data.get("content") or "").strip()
    if not symbol or not content:
        return jsonify({"error": "Eksik veri"}), 400

    try:
        c = AssetComment(
            asset_symbol=symbol,
            content=content,
            user_id=session["user_id"],
            username=session["username"],
            avatar=session.get("avatar", "👤"),
        )
        db.session.add(c)

        user = User.query.get(session["user_id"])
        user.total_comments += 1

        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"❌ add_asset_comment: {e}")
        db.session.rollback()
        return jsonify({"error": "Yorum eklenemedi"}), 500


@app.delete("/api/asset-comment/<int:comment_id>")
def delete_asset_comment(comment_id):
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    comment = AssetComment.query.get(comment_id)
    if not comment:
        return jsonify({"error": "Yorum bulunamadı"}), 404
    if comment.user_id != session["user_id"]:
        return jsonify({"error": "Yetkiniz yok"}), 403

    try:
        user = User.query.get(session["user_id"])
        user.total_comments = max(0, user.total_comments - 1)

        db.session.delete(comment)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"❌ delete_asset_comment: {e}")
        db.session.rollback()
        return jsonify({"error": "Silinemedi"}), 500


@app.post("/api/rate-asset-comment")
def rate_asset_comment():
    if "user_id" not in session:
        return jsonify({"error": "Giriş yapmalısınız"}), 401

    data = request.get_json(silent=True) or {}
    comment = AssetComment.query.get(data.get("comment_id"))
    rating = int(data.get("rating") or 0)
    if not comment:
        return jsonify({"error": "Yorum bulunamadı"}), 404
    if rating < 1 or rating > 5:
        return jsonify({"error": "Geçersiz oy"}), 400

    comment.rating_sum += rating
    comment.rating_count += 1
    db.session.commit()
    return jsonify({"success": True})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = not is_prod
    logger.info(f"🚀 Starting on {port}")
    app.run(host="0.0.0.0", port=port, debug=debug)