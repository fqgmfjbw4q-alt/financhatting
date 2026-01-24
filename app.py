import os
import threading
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

from flask import (
    Flask,
    render_template,
    jsonify,
    request,
    redirect,
    url_for,
    session,
    abort,
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

import requests

# OAuth (opsiyonel)
from authlib.integrations.flask_client import OAuth


# ----------------------------
# App + Config
# ----------------------------
app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# DATABASE_URL (Railway)
db_url = os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url or "sqlite:///local.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ----------------------------
# OAuth (Google) - Opsiyonel
# ----------------------------
oauth = OAuth(app)
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    oauth.register(
        name="google",
        client_id=GOOGLE_CLIENT_ID,
        client_secret=GOOGLE_CLIENT_SECRET,
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

# ----------------------------
# Models
# ----------------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.BigInteger, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(100), nullable=False)
    bio = db.Column(db.String(160), nullable=True)

    password_hash = db.Column(db.String(255), nullable=True)
    google_id = db.Column(db.String(128), unique=True, nullable=True)

    avatar_type = db.Column(db.String(16), nullable=False, default="ui")
    avatar_url = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Follow(db.Model):
    __tablename__ = "follows"
    id = db.Column(db.BigInteger, primary_key=True)
    follower_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    following_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint("follower_id", "following_id", name="uq_follow_pair"),)


class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    symbol_key = db.Column(db.String(16), nullable=True, index=True)
    image_url = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class PostRating(db.Model):
    __tablename__ = "post_ratings"
    id = db.Column(db.BigInteger, primary_key=True)
    post_id = db.Column(db.BigInteger, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    stars = db.Column(db.SmallInteger, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint("post_id", "user_id", name="uq_post_rating_once"),)


class SymbolComment(db.Model):
    __tablename__ = "symbol_comments"
    id = db.Column(db.BigInteger, primary_key=True)
    symbol_key = db.Column(db.String(16), nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class CommentRating(db.Model):
    __tablename__ = "comment_ratings"
    id = db.Column(db.BigInteger, primary_key=True)
    comment_id = db.Column(db.BigInteger, db.ForeignKey("symbol_comments.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    stars = db.Column(db.SmallInteger, nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (db.UniqueConstraint("comment_id", "user_id", name="uq_comment_rating_once"),)


class PriceAlert(db.Model):
    __tablename__ = "price_alerts"
    id = db.Column(db.BigInteger, primary_key=True)
    symbol_key = db.Column(db.String(16), nullable=False, index=True)
    change_pct = db.Column(db.Float, nullable=False)
    window = db.Column(db.String(8), nullable=False, default="1d")
    last_price = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class FeedEvent(db.Model):
    __tablename__ = "feed_events"
    id = db.Column(db.BigInteger, primary_key=True)
    type = db.Column(db.String(16), nullable=False)
    ref_id = db.Column(db.BigInteger, nullable=False, index=True)
    score = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


# ----------------------------
# Helpers
# ----------------------------
def now_utc():
    return datetime.now(timezone.utc)


def current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, uid)


def login_required():
    if not current_user():
        return redirect(url_for("login", next=request.path))
    return None


def ui_avatar_url(full_name: str) -> str:
    name = quote_plus((full_name or "").strip() or "User")
    return f"https://ui-avatars.com/api/?name={name}&background=0f172a&color=10b981&size=256&bold=true"


def username_is_valid(u: str) -> bool:
    if not u or len(u) < 3 or len(u) > 32:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_.")
    return all(ch in allowed for ch in u)


# ----------------------------
# Finance Data (MULTI-SOURCE API)
# ----------------------------
PRICE_SYMBOLS = {
    "btc": "BTC-USD",
    "gold": "GOLD",
    "silver": "SILVER",
    "copper": "COPPER",
    "usd_try": "USD/TRY",
    "eur_try": "EUR/TRY",
    "bist100": "BIST100",
}

CACHE_TTL_SECONDS = 30
_last_good = {"data": None, "ts": 0.0}
_lock = threading.Lock()
_worker_started = False


def _placeholder_prices():
    return {
        "btc": None,
        "gold": None,
        "silver": None,
        "copper": None,
        "usd_try": None,
        "eur_try": None,
        "bist100": None,
        "gram_altin": None,
        "timestamp": datetime.now().isoformat(),
    }


def _safe_float(x):
    try:
        return float(x)
    except Exception:
        return None


def _fetch_prices_batch():
    """Multi-source API ile veri çekimi"""
    try:
        prices = {k: None for k in PRICE_SYMBOLS.keys()}
        
        # === 1. KRİPTO (CoinGecko) ===
        try:
            crypto_response = requests.get(
                'https://api.coingecko.com/api/v3/simple/price',
                params={'ids': 'bitcoin', 'vs_currencies': 'usd'},
                timeout=5,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            if crypto_response.ok:
                crypto_data = crypto_response.json()
                prices['btc'] = _safe_float(crypto_data.get('bitcoin', {}).get('usd'))
                print(f"✓ BTC: ${prices['btc']}")
        except Exception as e:
            print(f"CoinGecko error: {e}")
        
        # === 2. DÖVİZ (ExchangeRate-API) ===
        try:
            fx_response = requests.get(
                'https://api.exchangerate-api.com/v4/latest/USD',
                timeout=5,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            if fx_response.ok:
                rates = fx_response.json().get('rates', {})
                prices['usd_try'] = _safe_float(rates.get('TRY'))
                
                eur_rate = _safe_float(rates.get('EUR'))
                if eur_rate and prices['usd_try']:
                    prices['eur_try'] = prices['usd_try'] / eur_rate
                
                print(f"✓ USD/TRY: {prices['usd_try']}")
                print(f"✓ EUR/TRY: {prices['eur_try']}")
        except Exception as e:
            print(f"ExchangeRate error: {e}")
        
        # === 3. ALTIN, GÜMÜŞ, BAKIR (Metals-API) ===
        METALS_API_KEY = os.environ.get('METALS_API_KEY')
        if METALS_API_KEY:
            try:
                metals_response = requests.get(
                    f'https://metals-api.com/api/latest',
                    params={
                        'access_key': METALS_API_KEY,
                        'base': 'USD',
                        'symbols': 'XAU,XAG,XCU'
                    },
                    timeout=5
                )
                if metals_response.ok:
                    metals_data = metals_response.json()
                    if metals_data.get('success'):
                        rates = metals_data.get('rates', {})
                        if rates.get('XAU'):
                            prices['gold'] = 1 / _safe_float(rates['XAU'])
                        if rates.get('XAG'):
                            prices['silver'] = 1 / _safe_float(rates['XAG'])
                        if rates.get('XCU'):
                            prices['copper'] = 1 / _safe_float(rates['XCU'])
                        
                        print(f"✓ Gold: ${prices['gold']}")
                        print(f"✓ Silver: ${prices['silver']}")
            except Exception as e:
                print(f"Metals-API error: {e}")
        
        # Fallback değerler
        if not prices['gold']:
            prices['gold'] = 2750.0
        if not prices['silver']:
            prices['silver'] = 31.5
        if not prices['copper']:
            prices['copper'] = 4.2
        
        if not METALS_API_KEY:
            print("⚠ Metals-API key yok, fallback değerler kullanılıyor")
        
        # === 4. BIST 100 ===
        try:
            bist_response = requests.get(
                'https://api.bigpara.hurriyet.com.tr/doviz/headerlist/anasayfa',
                timeout=5,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            if bist_response.ok:
                bist_data = bist_response.json()
                
                # API bazen string dönüyor
                if isinstance(bist_data, str):
                    import json
                    try:
                        bist_data = json.loads(bist_data)
                    except:
                        bist_data = []
                
                if isinstance(bist_data, list):
                    for item in bist_data:
                        if isinstance(item, dict) and item.get('SEMBOL') == 'XU100':
                            prices['bist100'] = _safe_float(item.get('KAPANIS'))
                            print(f"✓ BIST100: {prices['bist100']}")
                            break
                
                if not prices.get('bist100'):
                    prices['bist100'] = 10850.0
                    print(f"⚠ BIST100 fallback: {prices['bist100']}")
        except Exception as e:
            print(f"BIST100 error: {e}")
            prices['bist100'] = 10850.0
        
        # === 5. GRAM ALTIN HESAPLA ===
        if prices.get('gold') and prices.get('usd_try'):
            prices['gram_altin'] = (prices['gold'] / 31.1035) * prices['usd_try']
            print(f"✓ Gram Altın: ₺{prices['gram_altin']:.2f}")
        
        prices['timestamp'] = datetime.now().isoformat()
        
        if any(v is not None for k, v in prices.items() if k != 'timestamp'):
            return prices
        else:
            return None
            
    except Exception as e:
        print(f"❌ Batch fetch critical error: {e}")
        return None


def _maybe_create_price_alerts_from_cache(cached_prices: dict):
    """Cache üzerinden alert üretir"""
    pass


def _bg_loop():
    """Arka planda sürekli çalışan thread"""
    while True:
        print(f"🔄 [{datetime.now().strftime('%H:%M:%S')}] Fiyatlar çekiliyor...")
        data = _fetch_prices_batch()
        
        if data:
            with _lock:
                _last_good["data"] = data
                _last_good["ts"] = time.time()
            print(f"✅ Cache güncellendi")
            
            try:
                _maybe_create_price_alerts_from_cache(data)
            except Exception as e:
                print(f"Alert bg error: {e}")
        else:
            print(f"⚠ Veri çekilemedi, cache korunuyor")

        time.sleep(max(10, CACHE_TTL_SECONDS))


def _ensure_bg_started():
    global _worker_started
    if _worker_started:
        return
    _worker_started = True
    t = threading.Thread(target=_bg_loop, daemon=True)
    t.start()
    print("🚀 Background worker başlatıldı")


def get_financial_data():
    """ASLA BLOKLAMAZ"""
    _ensure_bg_started()

    now_ts = time.time()
    with _lock:
        cached = _last_good["data"]
        age = now_ts - _last_good["ts"]

    if cached:
        if age < CACHE_TTL_SECONDS:
            return cached
        else:
            return cached

    return _placeholder_prices()


# ----------------------------
# DB init
# ----------------------------
with app.app_context():
    db.create_all()


# ----------------------------
# Rating summaries
# ----------------------------
def post_rating_summary(post_id: int, refresh: bool = False):
    q = db.session.query(
        db.func.avg(PostRating.stars),
        db.func.count(PostRating.id),
    ).filter(PostRating.post_id == post_id)
    avg, cnt = q.first()
    avg = float(avg) if avg is not None else 0.0
    cnt = int(cnt or 0)
    return avg, cnt


def comment_rating_summary(comment_id: int):
    q = db.session.query(
        db.func.avg(CommentRating.stars),
        db.func.count(CommentRating.id),
    ).filter(CommentRating.comment_id == comment_id)
    avg, cnt = q.first()
    avg = float(avg) if avg is not None else 0.0
    cnt = int(cnt or 0)
    return avg, cnt


def top_posts_by_rating(limit=10):
    rows = (
        db.session.query(
            Post,
            db.func.avg(PostRating.stars).label("avg"),
            db.func.count(PostRating.id).label("cnt"),
        )
        .outerjoin(PostRating, PostRating.post_id == Post.id)
        .group_by(Post.id)
        .all()
    )

    enriched = []
    for p, avg, cnt in rows:
        score = float(avg or 0.0) * (1.0 + (int(cnt or 0) / 5.0))
        enriched.append((score, p, float(avg or 0.0), int(cnt or 0)))

    enriched.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, p, avg, cnt in enriched[:limit]:
        u = db.session.get(User, p.user_id)
        out.append({"post": p, "user": u, "avg": avg, "cnt": cnt})
    return out


def trending_symbols_by_comments(limit=10):
    rows = (
        db.session.query(
            SymbolComment.symbol_key,
            db.func.count(SymbolComment.id).label("cnt"),
        )
        .group_by(SymbolComment.symbol_key)
        .order_by(db.func.count(SymbolComment.id).desc())
        .limit(limit)
        .all()
    )
    return [{"symbol_key": r[0], "cnt": int(r[1])} for r in rows]


# ----------------------------
# Routes: Pages
# ----------------------------
@app.route("/")
def index():
    return render_template("index.html", user=current_user())


@app.route("/feed")
def feed():
    events = (
        db.session.query(FeedEvent)
        .order_by(FeedEvent.score.desc(), FeedEvent.created_at.desc())
        .limit(50)
        .all()
    )

    items = []
    for ev in events:
        if ev.type == "post":
            post = db.session.get(Post, ev.ref_id)
            if not post:
                continue
            user = db.session.get(User, post.user_id)
            avg, cnt = post_rating_summary(post.id)
            items.append({"type": "post", "post": post, "user": user, "avg": avg, "cnt": cnt})
        elif ev.type == "alert":
            alert = db.session.get(PriceAlert, ev.ref_id)
            if not alert:
                continue
            items.append({"type": "alert", "alert": alert})

    return render_template("feed.html", user=current_user(), items=items)


@app.route("/explore")
def explore():
    top_posts = top_posts_by_rating(limit=10)
    trending_symbols = trending_symbols_by_comments(limit=10)
    return render_template(
        "explore.html",
        user=current_user(),
        top_posts=top_posts,
        trending_symbols=trending_symbols,
    )


@app.route("/settings/profile", methods=["GET", "POST"])
def settings():
    lr = login_required()
    if lr:
        return lr
    u = current_user()

    if request.method == "POST":
        full_name = (request.form.get("full_name") or "").strip()
        bio = (request.form.get("bio") or "").strip()

        avatar_mode = request.form.get("avatar_mode") or "ui"
        preset = request.form.get("preset") or ""

        if full_name:
            u.full_name = full_name[:100]
        u.bio = bio[:160]

        if avatar_mode == "ui":
            u.avatar_type = "ui"
            u.avatar_url = None
        elif avatar_mode == "preset":
            u.avatar_type = "preset"
            u.avatar_url = preset if preset else None

        db.session.commit()
        flash("Profil güncellendi.", "ok")
        return redirect(url_for("settings"))

    return render_template("settings.html", user=u)


@app.route("/@<username>")
def profile(username):
    username = username.lower()
    u = db.session.query(User).filter_by(username=username).first()
    if not u:
        abort(404)

    posts = (
        db.session.query(Post)
        .filter(Post.user_id == u.id)
        .order_by(Post.created_at.desc())
        .limit(50)
        .all()
    )

    followers = db.session.query(Follow).filter(Follow.following_id == u.id).count()
    following = db.session.query(Follow).filter(Follow.follower_id == u.id).count()

    me = current_user()
    is_following = False
    if me and me.id != u.id:
        is_following = (
            db.session.query(Follow)
            .filter(Follow.follower_id == me.id, Follow.following_id == u.id)
            .first()
            is not None
        )

    post_meta = {}
    for p in posts:
        avg, cnt = post_rating_summary(p.id)
        post_meta[p.id] = {"avg": avg, "cnt": cnt}

    return render_template(
        "profile.html",
        user=me,
        profile_user=u,
        posts=posts,
        followers=followers,
        following=following,
        is_following=is_following,
        post_meta=post_meta,
    )


@app.route("/s/<symbol_key>")
def symbol_page(symbol_key):
    symbol_key = symbol_key.lower()
    if symbol_key not in PRICE_SYMBOLS:
        abort(404)

    return render_template(
        "symbol.html",
        user=current_user(),
        symbol_key=symbol_key.upper(),
    )


# ----------------------------
# Routes: Auth
# ----------------------------
@app.route("/auth/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        full_name = (request.form.get("full_name") or "").strip()
        password = request.form.get("password") or ""

        if not username_is_valid(username):
            flash("Kullanıcı adı geçersiz. (3-32, a-z 0-9 _ .)", "err")
            return redirect(url_for("register"))
        if not full_name or len(full_name) < 2:
            flash("İsim geçersiz.", "err")
            return redirect(url_for("register"))
        if len(password) < 6:
            flash("Şifre en az 6 karakter olmalı.", "err")
            return redirect(url_for("register"))

        exists = db.session.query(User).filter_by(username=username).first()
        if exists:
            flash("Bu kullanıcı adı alınmış.", "err")
            return redirect(url_for("register"))

        u = User(
            username=username,
            full_name=full_name[:100],
            password_hash=generate_password_hash(password),
            avatar_type="ui",
        )
        db.session.add(u)
        db.session.commit()

        session["user_id"] = u.id
        flash("Kayıt başarılı!", "ok")
        return redirect(url_for("index"))

    return render_template("register.html", user=current_user())


@app.route("/auth/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""

        u = db.session.query(User).filter_by(username=username).first()
        if not u or not u.password_hash or not check_password_hash(u.password_hash, password):
            flash("Hatalı kullanıcı adı veya şifre.", "err")
            return redirect(url_for("login"))

        session["user_id"] = u.id
        flash("Giriş başarılı.", "ok")
        nxt = request.args.get("next") or url_for("index")
        return redirect(nxt)

    return render_template("login.html", user=current_user())


@app.route("/auth/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


@app.route("/auth/google")
def google_login():
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        flash("Google giriş ayarlı değil (env eksik).", "err")
        return redirect(url_for("login"))
    redirect_uri = url_for("google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/auth/google/callback")
def google_callback():
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        abort(404)

    token = oauth.google.authorize_access_token()
    userinfo = token.get("userinfo")
    if not userinfo:
        userinfo = oauth.google.parse_id_token(token)

    google_id = userinfo.get("sub")
    full_name = userinfo.get("name") or "Google User"

    u = db.session.query(User).filter_by(google_id=google_id).first()
    if not u:
        base = "".join(ch for ch in (userinfo.get("given_name") or "user").lower() if ch.isalnum())
        base = (base or "user")[:20]
        candidate = base
        i = 0
        while db.session.query(User).filter_by(username=candidate).first():
            i += 1
            candidate = f"{base}{i}"

        u = User(
            username=candidate,
            full_name=full_name[:100],
            google_id=google_id,
            avatar_type="ui",
        )
        db.session.add(u)
        db.session.commit()

    session["user_id"] = u.id
    return redirect(url_for("index"))


# ----------------------------
# JSON API Endpoints
# ----------------------------

@app.route("/api/auth/register", methods=["POST"])
def api_register():
    """JSON API: Kayıt ol"""
    data = request.get_json()
    username = (data.get("username") or "").strip().lower()
    full_name = (data.get("full_name") or "").strip()
    password = data.get("password") or ""

    if not username_is_valid(username):
        return jsonify({"error": "Geçersiz kullanıcı adı"}), 400
    if not full_name or len(full_name) < 2:
        return jsonify({"error": "Geçersiz isim"}), 400
    if len(password) < 6:
        return jsonify({"error": "Şifre en az 6 karakter"}), 400

    exists = db.session.query(User).filter_by(username=username).first()
    if exists:
        return jsonify({"error": "Kullanıcı adı alınmış"}), 409

    u = User(
        username=username,
        full_name=full_name[:100],
        password_hash=generate_password_hash(password),
        avatar_type="ui",
    )
    db.session.add(u)
    db.session.commit()

    session["user_id"] = u.id
    return jsonify({"success": True, "username": u.username})


@app.route("/api/auth/login", methods=["POST"])
def api_login():
    """JSON API: Giriş yap"""
    data = request.get_json()
    username = (data.get("username") or "").strip().lower()
    password = data.get("password") or ""

    u = db.session.query(User).filter_by(username=username).first()
    if not u or not u.password_hash or not check_password_hash(u.password_hash, password):
        return jsonify({"error": "Hatalı bilgiler"}), 401

    session["user_id"] = u.id
    return jsonify({"success": True, "username": u.username})


@app.route("/api/me")
def api_me():
    """Mevcut kullanıcı bilgisi"""
    u = current_user()
    if not u:
        return jsonify({"error": "Not logged in"}), 401
    
    return jsonify({
        "id": u.id,
        "username": u.username,
        "full_name": u.full_name,
        "bio": u.bio,
        "avatar_url": u.avatar_url if u.avatar_type == "preset" else ui_avatar_url(u.full_name),
        "avatar_type": u.avatar_type,
    })


@app.route("/api/profile/<username>")
def api_profile(username):
    """Profil bilgisi (JSON)"""
    username = username.lower()
    u = db.session.query(User).filter_by(username=username).first()
    if not u:
        return jsonify({"error": "User not found"}), 404

    me = current_user()
    
    posts = (
        db.session.query(Post)
        .filter(Post.user_id == u.id)
        .order_by(Post.created_at.desc())
        .limit(50)
        .all()
    )
    
    posts_json = []
    for p in posts:
        avg, cnt = post_rating_summary(p.id)
        posts_json.append({
            "id": p.id,
            "content": p.content,
            "symbol_key": p.symbol_key,
            "image_url": p.image_url,
            "created_at": p.created_at.isoformat(),
            "rating": {"avg": avg, "count": cnt}
        })
    
    comments = (
        db.session.query(SymbolComment)
        .filter(SymbolComment.user_id == u.id)
        .order_by(SymbolComment.created_at.desc())
        .limit(50)
        .all()
    )
    
    comments_json = [{
        "id": c.id,
        "symbol_key": c.symbol_key,
        "content": c.content,
        "created_at": c.created_at.isoformat()
    } for c in comments]
    
    followers = db.session.query(Follow).filter(Follow.following_id == u.id).count()
    following = db.session.query(Follow).filter(Follow.follower_id == u.id).count()
    
    is_following = False
    if me and me.id != u.id:
        is_following = (
            db.session.query(Follow)
            .filter(Follow.follower_id == me.id, Follow.following_id == u.id)
            .first() is not None
        )
    
    return jsonify({
        "id": u.id,
        "username": u.username,
        "full_name": u.full_name,
        "bio": u.bio,
        "avatar_url": u.avatar_url if u.avatar_type == "preset" else ui_avatar_url(u.full_name),
        "followers": followers,
        "following": following,
        "is_following": is_following,
        "is_me": me and me.id == u.id,
        "posts": posts_json,
        "comments": comments_json,
    })


@app.route("/api/settings/profile", methods=["POST"])
def api_settings_profile():
    """Profil güncelle (JSON)"""
    u = current_user()
    if not u:
        return jsonify({"error": "Login required"}), 401
    
    data = request.get_json()
    full_name = (data.get("full_name") or "").strip()
    bio = (data.get("bio") or "").strip()
    avatar_mode = data.get("avatar_mode") or "ui"
    avatar_url_val = data.get("avatar_url") or ""

    if full_name:
        u.full_name = full_name[:100]
    u.bio = bio[:200]
    
    if avatar_mode == "ui":
        u.avatar_type = "ui"
        u.avatar_url = None
    elif avatar_mode == "preset":
        u.avatar_type = "preset"
        u.avatar_url = avatar_url_val if avatar_url_val else None
    
    db.session.commit()
    return jsonify({"success": True})


@app.route("/api/feed")
def api_feed():
    """Feed (JSON)"""
    filter_type = request.args.get("filter", "all")
    
    query = db.session.query(FeedEvent).order_by(
        FeedEvent.score.desc(), 
        FeedEvent.created_at.desc()
    )
    
    if filter_type == "posts":
        query = query.filter(FeedEvent.type == "post")
    elif filter_type == "alerts":
        query = query.filter(FeedEvent.type == "alert")
    elif filter_type == "hot":
        query = query.filter(FeedEvent.score > 10)
    
    events = query.limit(50).all()
    
    items = []
    for ev in events:
        if ev.type == "post":
            post = db.session.get(Post, ev.ref_id)
            if not post:
                continue
            user = db.session.get(User, post.user_id)
            avg, cnt = post_rating_summary(post.id)
            
            items.append({
                "type": "post",
                "id": post.id,
                "content": post.content,
                "symbol_key": post.symbol_key,
                "image_url": post.image_url,
                "created_at": post.created_at.isoformat(),
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "full_name": user.full_name,
                } if user else None,
                "rating": {"avg": avg, "count": cnt, "my": None}
            })
        
        elif ev.type == "alert":
            alert = db.session.get(PriceAlert, ev.ref_id)
            if not alert:
                continue
            items.append({
                "type": "alert",
                "id": alert.id,
                "created_at": alert.created_at.isoformat(),
                "alert": {
                    "symbol_key": alert.symbol_key,
                    "change_pct": alert.change_pct,
                    "window": alert.window,
                    "price": alert.last_price,
                }
            })
    
    return jsonify({"items": items})


@app.route("/api/posts", methods=["POST"])
def api_create_post():
    """Post oluştur (JSON)"""
    u = current_user()
    if not u:
        return jsonify({"error": "Login required"}), 401
    
    data = request.get_json()
    content = (data.get("content") or "").strip()
    symbol_key = (data.get("symbol_key") or "").strip().upper() or None
    
    if not content:
        return jsonify({"error": "Content required"}), 400
    if len(content) > 800:
        return jsonify({"error": "Too long"}), 400
    
    symbol_map = {"BTC": "btc", "GOLD": "gold", "SILVER": "silver", 
                  "USDTRY": "usd_try", "EURTRY": "eur_try", "BIST100": "bist100"}
    symbol_key = symbol_map.get(symbol_key) if symbol_key else None
    
    p = Post(user_id=u.id, content=content, symbol_key=symbol_key)
    db.session.add(p)
    db.session.flush()
    
    fe = FeedEvent(type="post", ref_id=p.id, score=1.0)
    db.session.add(fe)
    db.session.commit()
    
    return jsonify({"success": True, "post_id": p.id})


@app.route("/api/rate", methods=["POST"])
def api_rate():
    """Genel rating endpoint"""
    u = current_user()
    if not u:
        return jsonify({"error": "Login required"}), 401
    
    data = request.get_json()
    kind = data.get("kind")
    ref_id = int(data.get("id"))
    stars = int(data.get("stars"))
    
    if stars < 1 or stars > 5:
        return jsonify({"error": "Invalid stars"}), 400
    
    if kind == "post":
        r = db.session.query(PostRating).filter(
            PostRating.post_id == ref_id,
            PostRating.user_id == u.id
        ).first()
        if r:
            r.stars = stars
        else:
            r = PostRating(post_id=ref_id, user_id=u.id, stars=stars)
            db.session.add(r)
        
        avg, cnt = post_rating_summary(ref_id, refresh=True)
        
        fe = db.session.query(FeedEvent).filter(
            FeedEvent.type == "post",
            FeedEvent.ref_id == ref_id
        ).first()
        if fe:
            fe.score = float(avg) * (1.0 + (cnt / 10.0))
        
        db.session.commit()
        return jsonify({"avg": avg, "count": cnt, "my": stars})
    
    elif kind == "comment":
        r = db.session.query(CommentRating).filter(
            CommentRating.comment_id == ref_id,
            CommentRating.user_id == u.id
        ).first()
        if r:
            r.stars = stars
        else:
            r = CommentRating(comment_id=ref_id, user_id=u.id, stars=stars)
            db.session.add(r)
        
        avg, cnt = comment_rating_summary(ref_id)
        db.session.commit()
        return jsonify({"avg": avg, "count": cnt, "my": stars})
    
    return jsonify({"error": "Invalid kind"}), 400


@app.route("/api/follow", methods=["POST"])
def api_follow():
    """Follow/unfollow (JSON)"""
    me = current_user()
    if not me:
        return jsonify({"error": "Login required"}), 401
    
    data = request.get_json()
    username = (data.get("username") or "").strip().lower()
    action = data.get("action") or "follow"
    
    target = db.session.query(User).filter_by(username=username).first()
    if not target or target.id == me.id:
        return jsonify({"error": "Invalid target"}), 404
    
    existing = db.session.query(Follow).filter(
        Follow.follower_id == me.id,
        Follow.following_id == target.id
    ).first()
    
    if action == "unfollow" and existing:
        db.session.delete(existing)
        is_following = False
    elif action == "follow" and not existing:
        db.session.add(Follow(follower_id=me.id, following_id=target.id))
        is_following = True
    else:
        is_following = existing is not None
    
    db.session.commit()
    
    followers = db.session.query(Follow).filter(Follow.following_id == target.id).count()
    
    return jsonify({
        "is_following": is_following,
        "followers": followers
    })


@app.route("/api/explore")
def api_explore():
    """Keşfet (JSON)"""
    q = request.args.get("q", "").strip()
    
    symbol_rows = trending_symbols_by_comments(limit=10)
    
    symbols = []
    for row in symbol_rows:
        key = row["symbol_key"]
        symbols.append({
            "key": key.upper(),
            "name": key.upper(),
            "change_pct": None,
            "comments": row["cnt"]
        })
    
    top = top_posts_by_rating(limit=10)
    posts = []
    for item in top:
        p = item["post"]
        u = item["user"]
        posts.append({
            "id": p.id,
            "content": p.content,
            "symbol_key": p.symbol_key,
            "created_at": p.created_at.isoformat(),
            "user": {
                "username": u.username,
                "full_name": u.full_name
            } if u else None,
            "rating": {
                "avg": item["avg"],
                "count": item["cnt"]
            }
        })
    
    return jsonify({
        "symbols": symbols,
        "posts": posts
    })


@app.route("/api/symbol/<symbol_key>/comments")
def api_symbol_comments(symbol_key):
    """Symbol yorumları (JSON)"""
    symbol_key = symbol_key.lower()
    if symbol_key not in PRICE_SYMBOLS:
        return jsonify({"error": "Invalid symbol"}), 404
    
    comments = (
        db.session.query(SymbolComment)
        .filter(SymbolComment.symbol_key == symbol_key)
        .order_by(SymbolComment.created_at.desc())
        .limit(100)
        .all()
    )
    
    items = []
    for c in comments:
        u = db.session.get(User, c.user_id)
        avg, cnt = comment_rating_summary(c.id)
        items.append({
            "id": c.id,
            "content": c.content,
            "created_at": c.created_at.isoformat(),
            "user": {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
            } if u else None,
            "rating": {"avg": avg, "cnt": cnt}
        })
    
    return jsonify({"items": items})


@app.route("/api/symbol/<symbol_key>/comment", methods=["POST"])
def api_symbol_add_comment(symbol_key):
    """Yorum ekle (JSON)"""
    u = current_user()
    if not u:
        return jsonify({"error": "Login required"}), 401
    
    symbol_key = symbol_key.lower()
    if symbol_key not in PRICE_SYMBOLS:
        return jsonify({"error": "Invalid symbol"}), 404
    
    data = request.get_json()
    content = (data.get("content") or "").strip()
    
    if not content:
        return jsonify({"error": "Content required"}), 400
    if len(content) > 2000:
        return jsonify({"error": "Too long"}), 400
    
    c = SymbolComment(symbol_key=symbol_key, user_id=u.id, content=content)
    db.session.add(c)
    db.session.commit()
    
    return jsonify({
        "success": True,
        "comment": {
            "id": c.id,
            "content": c.content,
            "created_at": c.created_at.isoformat(),
            "user": {
                "id": u.id,
                "username": u.username,
                "full_name": u.full_name,
            }
        }
    }), 201


# ----------------------------
# Routes: Social actions (Form-based - eski yöntem)
# ----------------------------
@app.route("/api/post", methods=["POST"])
def create_post():
    lr = login_required()
    if lr:
        return lr
    u = current_user()
    content = (request.form.get("content") or "").strip()
    symbol_key = (request.form.get("symbol_key") or "").strip().lower() or None

    if not content:
        flash("Boş post atılamaz.", "err")
        return redirect(request.referrer or url_for("feed"))
    if len(content) > 1000:
        flash("Post çok uzun.", "err")
        return redirect(request.referrer or url_for("feed"))

    if symbol_key and symbol_key not in PRICE_SYMBOLS:
        symbol_key = None

    p = Post(user_id=u.id, content=content, symbol_key=symbol_key)
    db.session.add(p)
    db.session.flush()

    fe = FeedEvent(type="post", ref_id=p.id, score=1.0)
    db.session.add(fe)
    db.session.commit()

    return redirect(request.referrer or url_for("feed"))


@app.route("/api/post/<int:post_id>/rate", methods=["POST"])
def rate_post(post_id):
    lr = login_required()
    if lr:
        return lr
    u = current_user()
    stars = int(request.form.get("stars") or "0")
    if stars < 1 or stars > 5:
        abort(400)

    post = db.session.get(Post, post_id)
    if not post:
        abort(404)

    r = (
        db.session.query(PostRating)
        .filter(PostRating.post_id == post_id, PostRating.user_id == u.id)
        .first()
    )
    if r:
        r.stars = stars
    else:
        r = PostRating(post_id=post_id, user_id=u.id, stars=stars)
        db.session.add(r)

    avg, cnt = post_rating_summary(post_id)
    fe = db.session.query(FeedEvent).filter(FeedEvent.type == "post", FeedEvent.ref_id == post_id).first()
    if fe:
        fe.score = float(avg) * (1.0 + (cnt / 10.0))

    db.session.commit()
    return redirect(request.referrer or url_for("feed"))


@app.route("/api/symbol/<symbol_key>/comment", methods=["POST"])
def add_symbol_comment(symbol_key):
    lr = login_required()
    if lr:
        return lr
    symbol_key = symbol_key.lower()
    if symbol_key not in PRICE_SYMBOLS:
        abort(404)

    u = current_user()
    content = (request.form.get("content") or "").strip()
    if not content:
        flash("Boş yorum atılamaz.", "err")
        return redirect(url_for("symbol_page", symbol_key=symbol_key))

    c = SymbolComment(symbol_key=symbol_key, user_id=u.id, content=content[:2000])
    db.session.add(c)
    db.session.commit()
    return redirect(url_for("symbol_page", symbol_key=symbol_key))


@app.route("/api/comment/<int:comment_id>/rate", methods=["POST"])
def rate_comment(comment_id):
    lr = login_required()
    if lr:
        return lr
    u = current_user()
    stars = int(request.form.get("stars") or "0")
    if stars < 1 or stars > 5:
        abort(400)

    c = db.session.get(SymbolComment, comment_id)
    if not c:
        abort(404)

    r = (
        db.session.query(CommentRating)
        .filter(CommentRating.comment_id == comment_id, CommentRating.user_id == u.id)
        .first()
    )
    if r:
        r.stars = stars
    else:
        r = CommentRating(comment_id=comment_id, user_id=u.id, stars=stars)
        db.session.add(r)

    db.session.commit()
    return redirect(request.referrer or url_for("symbol_page", symbol_key=c.symbol_key))


@app.route("/api/follow/<username>", methods=["POST"])
def follow_user(username):
    lr = login_required()
    if lr:
        return lr
    me = current_user()
    username = username.lower()
    target = db.session.query(User).filter_by(username=username).first()
    if not target or target.id == me.id:
        abort(404)

    existing = (
        db.session.query(Follow)
        .filter(Follow.follower_id == me.id, Follow.following_id == target.id)
        .first()
    )
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(Follow(follower_id=me.id, following_id=target.id))

    db.session.commit()
    return redirect(url_for("profile", username=target.username))


# ----------------------------
# APIs (prices/calendar)
# ----------------------------
@app.route("/api/prices")
def prices_api():
    return jsonify(get_financial_data())


@app.route("/api/calendar")
def calendar_api():
    data = {
        "fed_rate": {"current": 4.50, "next_meeting": "2026-01-28"},
        "nonfarm_payroll": {"label": "Tarım Dışı İstihdam", "value": "215K", "previous": "190K", "date": "2026-02-06"},
        "unemployment": {"label": "İşsizlik Oranı", "value": "3.9%", "previous": "4.0%", "date": "2026-02-06"},
        "inflation": {"label": "TR Enflasyon (TÜFE)", "value": "44.2%", "previous": "45.1%", "date": "2026-02-03"},
    }
    return jsonify(data)


# ----------------------------
# Error pages
# ----------------------------
@app.errorhandler(404)
def not_found(e):
    return "<h1>404</h1><p>Bulunamadı</p>", 404


# ----------------------------
# Run local
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
