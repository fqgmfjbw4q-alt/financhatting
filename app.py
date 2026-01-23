import os
from datetime import datetime, timezone, timedelta
from urllib.parse import quote_plus

from flask import (
    Flask, render_template, jsonify, request, redirect, url_for, session, abort, flash
)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

import yfinance as yf

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
    # Heroku/Railway bazen postgres:// verir, SQLAlchemy postgresql:// bekler
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

    avatar_type = db.Column(db.String(16), nullable=False, default="ui")  # ui | preset | upload
    avatar_url = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class Follow(db.Model):
    __tablename__ = "follows"
    id = db.Column(db.BigInteger, primary_key=True)
    follower_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    following_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        db.UniqueConstraint("follower_id", "following_id", name="uq_follow_pair"),
    )


class Post(db.Model):
    __tablename__ = "posts"
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = db.Column(db.Text, nullable=False)
    symbol_key = db.Column(db.String(16), nullable=True, index=True)  # opsiyonel (BTC, GOLD vs.)
    image_url = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class PostRating(db.Model):
    __tablename__ = "post_ratings"
    id = db.Column(db.BigInteger, primary_key=True)
    post_id = db.Column(db.BigInteger, db.ForeignKey("posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    stars = db.Column(db.SmallInteger, nullable=False)  # 1..5
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        db.UniqueConstraint("post_id", "user_id", name="uq_post_rating_once"),
    )


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
    __table_args__ = (
        db.UniqueConstraint("comment_id", "user_id", name="uq_comment_rating_once"),
    )


class PriceAlert(db.Model):
    __tablename__ = "price_alerts"
    id = db.Column(db.BigInteger, primary_key=True)
    symbol_key = db.Column(db.String(16), nullable=False, index=True)
    change_pct = db.Column(db.Float, nullable=False)
    window = db.Column(db.String(8), nullable=False, default="1d")
    last_price = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (
        # aynı sembol için aynı gün aynı pencere tekrar basmasın
        db.UniqueConstraint("symbol_key", "window", "created_at", name="uq_alert_uniq_soft"),
    )


class FeedEvent(db.Model):
    __tablename__ = "feed_events"
    id = db.Column(db.BigInteger, primary_key=True)
    type = db.Column(db.String(16), nullable=False)  # post | alert
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
    name = quote_plus(full_name.strip() or "User")
    # tema mevcut tasarıma uygun
    return f"https://ui-avatars.com/api/?name={name}&background=0f172a&color=10b981&size=256&bold=true"

def username_is_valid(u: str) -> bool:
    if not u or len(u) < 3 or len(u) > 32:
        return False
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_.")
    return all(ch in allowed for ch in u)

# ----------------------------
# Finance Data (ORİJİNAL KALDI)
# ----------------------------
PRICE_SYMBOLS = {
    "btc": "BTC-USD",
    "gold": "GC=F",
    "silver": "SI=F",
    "copper": "HG=F",
    "usd_try": "USDTRY=X",
    "eur_try": "EURTRY=X",
    "bist100": "^XU100",
}

# Basit cache: 20 sn
_price_cache = {"ts": None, "data": None}

def _last_close_non_empty(ticker: yf.Ticker, periods=("1d", "5d")):
    for p in periods:
        data = ticker.history(period=p)
        if data is not None and not data.empty:
            return float(data["Close"].iloc[-1])
    return None

def get_financial_data():
    global _price_cache
    ts = _price_cache["ts"]
    if ts and (now_utc() - ts).total_seconds() < 20 and _price_cache["data"]:
        return _price_cache["data"]

    prices = {}
    try:
        for key, symbol in PRICE_SYMBOLS.items():
            ticker = yf.Ticker(symbol)
            prices[key] = _last_close_non_empty(ticker)

        # Gram Altın TL (Ons / 31.1035 * USDTRY)
        if prices.get("gold") and prices.get("usd_try"):
            prices["gram_altin"] = (prices["gold"] / 31.1035) * prices["usd_try"]
        else:
            prices["gram_altin"] = None

    except Exception as e:
        print(f"Veri çekme hatası: {e}")

    prices["timestamp"] = datetime.now().isoformat()

    _price_cache = {"ts": now_utc(), "data": prices}
    return prices

def compute_change_pct(symbol: str) -> float | None:
    """1d değişim yüzdesi için son 2-5 gün kapanışlarını karşılaştır."""
    try:
        t = yf.Ticker(symbol)
        data = t.history(period="5d")
        if data is None or data.empty or len(data["Close"]) < 2:
            return None
        closes = data["Close"].dropna()
        if len(closes) < 2:
            return None
        last = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        if prev == 0:
            return None
        return ((last - prev) / prev) * 100.0
    except Exception as e:
        print("change_pct error:", e)
        return None

def maybe_create_price_alerts():
    """%20+ değişim varsa feed'e alert düşür (günde 1 defa / sembol)."""
    # son 24 saat içinde aynı sembol alert var mı?
    since = now_utc() - timedelta(hours=24)

    for k, sym in PRICE_SYMBOLS.items():
        pct = compute_change_pct(sym)
        if pct is None:
            continue
        if abs(pct) < 20:
            continue

        exists = (
            db.session.query(PriceAlert)
            .filter(PriceAlert.symbol_key == k, PriceAlert.created_at >= since)
            .first()
        )
        if exists:
            continue

        # son fiyat
        last_price = None
        try:
            t = yf.Ticker(sym)
            d = t.history(period="1d")
            if d is not None and not d.empty:
                last_price = float(d["Close"].iloc[-1])
        except Exception:
            pass

        alert = PriceAlert(symbol_key=k, change_pct=float(pct), window="1d", last_price=last_price)
        db.session.add(alert)
        db.session.flush()  # id için

        score = abs(float(pct)) + 10.0  # basit skor
        fe = FeedEvent(type="alert", ref_id=alert.id, score=score)
        db.session.add(fe)

    db.session.commit()

# ----------------------------
# DB init (stabil ve basit)
# ----------------------------
with app.app_context():
    db.create_all()

# ----------------------------
# Routes: Pages
# ----------------------------
@app.route("/")
def index():
    return render_template("index.html", user=current_user())

@app.route("/feed")
def feed():
    # feed'e alert üretimini burada tetiklemek stabil (cron yok)
    try:
        maybe_create_price_alerts()
    except Exception as e:
        print("alert üretim hatası:", e)

    # Hot sıralama: score DESC, created_at DESC
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
    # Basit keşfet: en çok oylanan postlar + en çok yorum alan semboller (basit)
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

# Twitter tarzı profil: /@username
@app.route("/@<username>")
def profile(username):
    username = username.lower()
    u = db.session.query(User).filter_by(username=username).first()
    if not u:
        abort(404)

    # kullanıcının postları
    posts = (
        db.session.query(Post)
        .filter(Post.user_id == u.id)
        .order_by(Post.created_at.desc())
        .limit(50)
        .all()
    )

    # follow stats
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

    # post rating özetleri
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

    # yorumlar
    comments = (
        db.session.query(SymbolComment)
        .filter(SymbolComment.symbol_key == symbol_key)
        .order_by(SymbolComment.created_at.desc())
        .limit(100)
        .all()
    )

    comment_rows = []
    for c in comments:
        u = db.session.get(User, c.user_id)
        avg, cnt = comment_rating_summary(c.id)
        comment_rows.append({"c": c, "u": u, "avg": avg, "cnt": cnt})

    return render_template(
        "symbol.html",
        user=current_user(),
        symbol_key=symbol_key,
        comments=comment_rows,
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
        # bazı akışlarda userinfo ayrı endpointten gelir
        userinfo = oauth.google.parse_id_token(token)

    google_id = userinfo.get("sub")
    full_name = userinfo.get("name") or "Google User"

    u = db.session.query(User).filter_by(google_id=google_id).first()
    if not u:
        # username otomatik öner (sonra kullanıcı isterse değiştiririz)
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
# Routes: Social actions
# ----------------------------
@app.route("/api/post", methods=["POST"])
def create_post():
    lr = login_required()
    if lr:
        return lr  # redirect
    u = current_user()
    content = (request.form.get("content") or "").strip()
    symbol_key = (request.form.get("symbol_key") or "").strip().lower() or None

    if not content or len(content) < 1:
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

    # feed event
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

    # feed hot skorunu güncelle (basit)
    avg, cnt = post_rating_summary(post_id, refresh=True)
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
        # unfollow
        db.session.delete(existing)
    else:
        db.session.add(Follow(follower_id=me.id, following_id=target.id))

    db.session.commit()
    return redirect(url_for("profile", username=target.username))

# ----------------------------
# Routes: Existing APIs (prices/calendar)
# ----------------------------
@app.route("/api/prices")
def prices_api():
    return jsonify(get_financial_data())

@app.route("/api/calendar")
def calendar_api():
    # şimdilik hardcoded
    data = {
        "fed_rate": {"current": 4.50, "next_meeting": "2026-01-28"},
        "nonfarm_payroll": {"label": "Tarım Dışı İstihdam", "value": "215K", "previous": "190K", "date": "2026-02-06"},
        "unemployment": {"label": "İşsizlik Oranı", "value": "3.9%", "previous": "4.0%", "date": "2026-02-06"},
        "inflation": {"label": "TR Enflasyon (TÜFE)", "value": "44.2%", "previous": "45.1%", "date": "2026-02-03"}
    }
    return jsonify(data)

# ----------------------------
# Rating summaries
# ----------------------------
def post_rating_summary(post_id: int, refresh: bool = False):
    q = db.session.query(
        db.func.avg(PostRating.stars),
        db.func.count(PostRating.id)
    ).filter(PostRating.post_id == post_id)
    avg, cnt = q.first()
    avg = float(avg) if avg is not None else 0.0
    cnt = int(cnt or 0)
    return avg, cnt

def comment_rating_summary(comment_id: int):
    q = db.session.query(
        db.func.avg(CommentRating.stars),
        db.func.count(CommentRating.id)
    ).filter(CommentRating.comment_id == comment_id)
    avg, cnt = q.first()
    avg = float(avg) if avg is not None else 0.0
    cnt = int(cnt or 0)
    return avg, cnt

def top_posts_by_rating(limit=10):
    # avg*count gibi basit bir “etkileşim” sıralaması
    rows = db.session.query(
        Post,
        db.func.avg(PostRating.stars).label("avg"),
        db.func.count(PostRating.id).label("cnt"),
    ).outerjoin(PostRating, PostRating.post_id == Post.id).group_by(Post.id).all()

    enriched = []
    for p, avg, cnt in rows:
        score = (float(avg or 0.0) * (1.0 + (int(cnt or 0) / 5.0)))
        enriched.append((score, p, float(avg or 0.0), int(cnt or 0)))

    enriched.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, p, avg, cnt in enriched[:limit]:
        u = db.session.get(User, p.user_id)
        out.append({"post": p, "user": u, "avg": avg, "cnt": cnt})
    return out

def trending_symbols_by_comments(limit=10):
    rows = db.session.query(
        SymbolComment.symbol_key,
        db.func.count(SymbolComment.id).label("cnt"),
    ).group_by(SymbolComment.symbol_key).order_by(db.func.count(SymbolComment.id).desc()).limit(limit).all()
    return [{"symbol_key": r[0], "cnt": int(r[1])} for r in rows]

# ----------------------------
# Error pages
# ----------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("base.html", user=current_user(), content="<div class='error-message'>404 - Bulunamadı</div>"), 404

# ----------------------------
# Run local
# ----------------------------
if __name__ == "__main__":
    app.run(debug=True)
