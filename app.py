import os
from datetime import date, datetime
from decimal import Decimal

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import (
    LoginManager, login_user, login_required, logout_user,
    UserMixin, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash

# ---------------------------------------------------------------------
# Optional – за bcrypt ($2a/$2b/$2y) преку passlib, ако е инсталиран
# ---------------------------------------------------------------------
try:
    from passlib.hash import bcrypt  # type: ignore
    HAS_PASSLIB = True
except Exception:
    HAS_PASSLIB = False

from sqlalchemy import (
    create_engine, Column, Integer, String, Date, Numeric, text, func, DateTime
)
from sqlalchemy.orm import declarative_base, sessionmaker, scoped_session
from sqlalchemy.exc import ProgrammingError

# ---------------------------------------------------------------------
# App & Config
# ---------------------------------------------------------------------

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "please-change-me")

# Render/Supabase DATABASE_URL нормализација -> psycopg2
raw_db_url = os.environ.get("DATABASE_URL", "")
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif raw_db_url.startswith("postgresql://") and "+psycopg2" not in raw_db_url:
    raw_db_url = raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

if not raw_db_url:
    raise RuntimeError("DATABASE_URL environment variable is not set!")

engine = create_engine(
    raw_db_url,
    future=True,
    pool_pre_ping=True,
)
SessionLocal = scoped_session(
    sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
)
Base = declarative_base()

# ---------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------

class User(Base, UserMixin):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False, index=True)
    password = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    # UserMixin -> get_id()

class Klient(Base):
    __tablename__ = "klienti"

    id = Column(Integer, primary_key=True)
    ime = Column(String, nullable=False)
    prezime = Column(String, nullable=True)
    datum = Column(Date, nullable=False, server_default=func.current_date())
    dolg = Column(Numeric(12, 2), nullable=False, server_default=text("0"))
    plateno = Column(Numeric(10, 2), nullable=False, server_default=text("0"))

# ---------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------

def hash_password_pbkdf2(plain: str) -> str:
    """Default hashing за нови корисници (pbkdf2:sha256)."""
    return generate_password_hash(plain)

def verify_password(stored_hash: str, plain: str) -> bool:
    """
    Поддржува:
    - pbkdf2:sha256 (werkzeug)
    - bcrypt $2* (passlib, ако е инсталиран)
    """
    try:
        if not stored_hash:
            return False

        if stored_hash.startswith("pbkdf2:"):
            return check_password_hash(stored_hash, plain)

        if stored_hash.startswith("$2") and HAS_PASSLIB:
            return bcrypt.verify(plain, stored_hash)

        # Непознат формат
        return False
    except Exception:
        return False

# ---------------------------------------------------------------------
# Flask-Login
# ---------------------------------------------------------------------

login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id: str):
    db = SessionLocal()
    try:
        return db.get(User, int(user_id))
    finally:
        db.close()

# ---------------------------------------------------------------------
# DB init & DDL fixes
# ---------------------------------------------------------------------

def ensure_tables():
    """Креира табели ако недостигаат."""
    Base.metadata.create_all(bind=engine)

def apply_ddl_fixes():
    """
    Поправки кои create_all не ги прави:
    - додај users.created_at ако ја нема колоната
    """
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            ALTER TABLE IF EXISTS public.users
            ADD COLUMN IF NOT EXISTS created_at timestamp NOT NULL DEFAULT now();
        """)

def ensure_admin():
    """
    Креира иницијален админ ако го нема (ADMIN_EMAIL/ADMIN_PASSWORD од env).
    Лозинката се чува како pbkdf2:sha256 (werkzeug).
    """
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_password = os.environ.get("ADMIN_PASSWORD")

    if not admin_email or not admin_password:
        app.logger.info("ADMIN_EMAIL/ADMIN_PASSWORD not provided – skipping admin creation.")
        return

    db = SessionLocal()
    try:
        already = db.query(User).filter(User.email == admin_email).first()
        if not already:
            u = User(email=admin_email, password=hash_password_pbkdf2(admin_password))
            db.add(u)
            db.commit()
            app.logger.info("Admin user created: %s", admin_email)
    finally:
        db.close()

# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------

@app.get("/health")
def health():
    return "ok", 200

@app.route("/login", methods=["GET", "POST"])
def login():
    db = SessionLocal()
    try:
        if request.method == "POST":
            email = (request.form.get("email") or "").strip()
            password = request.form.get("password") or ""

            user = db.query(User).filter(User.email == email).first()
            if user and verify_password(user.password, password):
                login_user(user)
                nxt = request.args.get("next") or url_for("index")
                return redirect(nxt)

            flash("Погрешен email или лозинка", "danger")
            return redirect(url_for("login"))

        # GET
        try:
            return render_template("login.html")
        except Exception:
            # Фолбек ако нема темплејт
            return (
                "<h3>Најава</h3>"
                "<form method='post'>"
                "<input name='email' placeholder='Email'><br>"
                "<input name='password' placeholder='Лозинка' type='password'><br>"
                "<button type='submit'>Влези</button>"
                "</form>",
                200,
            )
    finally:
        db.close()

@app.get("/logout")
@login_required
def logout():
    logout_user()
    flash("Одјавени сте", "success")
    return redirect(url_for("login"))

@app.get("/")
@login_required
def index():
    db = SessionLocal()
    try:
        klienti = db.query(Klient).order_by(Klient.id.desc()).limit(50).all()
        try:
            return render_template("customers.html", klienti=klienti, q="")
        except Exception:
            return "Logged in ✅", 200
    finally:
        db.close()

# ---------------------------------------------------------------------
# Startup (Render го извршува при import)
# ---------------------------------------------------------------------

def _startup():
    ensure_tables()
    apply_ddl_fixes()     # <= важен дел за твојот случај (created_at)
    ensure_admin()
    app.logger.info("Startup complete.")

_startup()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
