# app.py
import os
from functools import wraps
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session
)
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

app = Flask(__name__)
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
    # Твојата почетна страна / преглед (замени со твој template/route)
    return render_template("index.html") if template_exists("index.html") else "Logged in ✅"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""

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
def logout():
    session.clear()
    return redirect(url_for("login"))


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
