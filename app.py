@@ -1,131 +1,200 @@
# -*- coding: utf-8 -*-
# app.py
import os
from datetime import datetime
from decimal import Decimal

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session
)
from werkzeug.security import generate_password_hash, check_password_hash
import psycopg2
from psycopg2.pool import SimpleConnectionPool


# -----------------------------------------------------------------------------
# Config
# -----------------------------------------------------------------------------
def _normalize_dsn(url: str) -> str:
    """
    Render/Supabase ти даваат SQLAlchemy стил URL (postgresql+psycopg2://...)
    а psycopg2 сака чист (postgresql://...). Ова го нормализира.
    """
    if url.startswith("postgresql+psycopg2://"):
        url = url.replace("postgresql+psycopg2://", "postgresql://", 1)
    # Осигурај се дека имаме sslmode=require (Supabase го бара тоа)
    if "sslmode=" not in url:
        sep = "&" if "?" in url else "?"
        url = f"{url}{sep}sslmode=require"
    return url


DATABASE_URL = _normalize_dsn(os.environ.get("DATABASE_URL", "").strip())
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is missing!")

SECRET_KEY = os.environ.get("FLASK_SECRET", "change-me-please")

# ------------------------------------------------------
# Flask конфигурација
# ------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET", "dev-secret-change-me")

db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL is not set!")

# дозволи стар префикс ако случајно е "postgres://"
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)

# SQLAlchemy + pgBouncer/SSL опции
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 280,
    "pool_size": 5,
    "max_overflow": 5,
    "connect_args": {
        "sslmode": "require",
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    },
}

db = SQLAlchemy(app)

# ------------------------------------------------------
# Login Manager
# ------------------------------------------------------
login_manager = LoginManager(app)
login_manager.login_view = "login"

# ------------------------------------------------------
# Модели
# ------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)

class Klient(db.Model):
    __tablename__ = "klienti"
    id = db.Column(db.Integer, primary_key=True)
    ime = db.Column(db.String(100))
    prezime = db.Column(db.String(100))
    datum = db.Column(db.Date, default=datetime.utcnow)
    dolg = db.Column(db.Numeric(10, 2), default=0)
    plateno = db.Column(db.Numeric(10, 2), default=0)

# ------------------------------------------------------
# User loader
# ------------------------------------------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ------------------------------------------------------
# Иницијализација при старт (без before_first_request)
# ------------------------------------------------------
def init_db_and_admin():
    db.create_all()
    admin_email = os.getenv("ADMIN_EMAIL")
    admin_pass = os.getenv("ADMIN_PASSWORD")
    if admin_email and admin_pass:
        if not User.query.filter_by(email=admin_email).first():
            db.session.add(User(email=admin_email,
                                password=generate_password_hash(admin_pass)))
            db.session.commit()

with app.app_context():
    # safe/idempotent; ќе се изврши еднаш при подигање на worker
    init_db_and_admin()

# ------------------------------------------------------
# Рути
# ------------------------------------------------------
app.secret_key = SECRET_KEY

# Connection pool (1..10 конекции)
pool = SimpleConnectionPool(1, 10, dsn=DATABASE_URL)


# -----------------------------------------------------------------------------
# DB helpers
# -----------------------------------------------------------------------------
def get_conn():
    return pool.getconn()

def put_conn(conn):
    if conn:
        pool.putconn(conn)

def fetch_one(sql, params=()):
    conn = cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row
    finally:
        if cur:
            cur.close()
        put_conn(conn)

def execute(sql, params=()):
    conn = cur = None
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        if cur:
            cur.close()
        put_conn(conn)


# -----------------------------------------------------------------------------
# Bootstrap: креирај табела ако ја нема (safe)
# -----------------------------------------------------------------------------
def ensure_schema():
    execute("""
        CREATE EXTENSION IF NOT EXISTS pgcrypto;

        CREATE TABLE IF NOT EXISTS public.users (
            id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email    TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        );
    """)

ensure_schema()


# -----------------------------------------------------------------------------
# Auth helpers
# -----------------------------------------------------------------------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get("user_id"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return wrapper


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    klienti = Klient.query.order_by(Klient.id.desc()).all()
    return render_template("index.html", klienti=klienti)
    # Твојата почетна страна / преглед (замени со твој template/route)
    return render_template("index.html") if template_exists("index.html") else "Logged in ✅"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("index"))

        # Клучната разлика: проверка со crypt во базата!
        row = fetch_one("""
            SELECT id, email
            FROM public.users
            WHERE email = %s
              AND password = crypt(%s, password);
        """, (email, password))

        if row:
            session["user_id"] = str(row[0])
            session["email"] = row[1]
            next_url = request.args.get("next") or url_for("index")
            return redirect(next_url)

        flash("Погрешен емаил или лозинка", "danger")
    return render_template("login.html")

    # Render на твојот постоечки login.html, ако го нема – минимален форм
    if template_exists("login.html"):
        return render_template("login.html")
    return """
        <h1>Најава</h1>
        <form method="post">
            <input type="email" name="email" placeholder="Email" required /><br />
            <input type="password" name="password" placeholder="Лозинка" required /><br />
            <button type="submit">Влези</button>
        </form>
    """

@app.route("/logout")
@login_required
def logout():
    logout_user()
    session.clear()
    return redirect(url_for("login"))

@app.route("/add_klient", methods=["POST"])
@login_required
def add_klient():
    ime = request.form.get("ime") or ""
    prezime = request.form.get("prezime") or ""
    dolg = Decimal(request.form.get("dolg") or "0")
    plateno = Decimal(request.form.get("plateno") or "0")
    db.session.add(Klient(ime=ime, prezime=prezime, dolg=dolg, plateno=plateno))
    db.session.commit()
    flash("Клиентот е успешно додаден!", "success")
    return redirect(url_for("index"))

# -----------------------------------------------------------------------------
# Utility: проверка дали постои template (за да не кидне ако нема)
# -----------------------------------------------------------------------------
def template_exists(name: str) -> bool:
    try:
        # ќе фрли грешка ако не постои темплејтот
        app.jinja_env.get_or_select_template(name)
        return True
    except Exception:
        return False


# -----------------------------------------------------------------------------
# Optional: seed user (само ако сакаш да креираш админ од ENV)
# -----------------------------------------------------------------------------
@app.cli.command("seed-admin")
def seed_admin():
    """
    Пример: render.com -> Shell -> `flask seed-admin`
    Потребни ENV:
      ADMIN_EMAIL
      ADMIN_PASSWORD
    """
    admin_email = os.environ.get("ADMIN_EMAIL")
    admin_pass = os.environ.get("ADMIN_PASSWORD")
    if not admin_email or not admin_pass:
        print("ADMIN_EMAIL/ADMIN_PASSWORD env not set.")
        return

    # Insert со bcrypt hash во базата
    execute("""
        INSERT INTO public.users (email, password)
        VALUES (%s, crypt(%s, gen_salt('bf')))
        ON CONFLICT (email) DO NOTHING;
    """, (admin_email, admin_pass))
    print("Admin seeded (или веќе постоеше).")


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    # Локално стартување
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
