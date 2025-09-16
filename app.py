import os
from datetime import date, datetime
from decimal import Decimal

from flask import (
Flask, render_template, request, redirect, url_for, flash
)
from flask_login import (
LoginManager, login_user, login_required, logout_user,
UserMixin, current_user
)

from werkzeug.security import (
generate_password_hash, check_password_hash
)

# Optional – за bcrypt поддршка (за хешови од тип $2b$...)
try:
from passlib.hash import bcrypt # type: ignore
HAS_PASSLIB = True
except Exception:
HAS_PASSLIB = False

from sqlalchemy import (
create_engine, Column, Integer, String, Date, Numeric, text, func, DateTime
)
from sqlalchemy.orm import (
declarative_base, sessionmaker, scoped_session
)

# ------------------------------------------------------------------------------
# App & Config
# ------------------------------------------------------------------------------

app = Flask(__name__)

# SECRET_KEY
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "please-change-me")

# DATABASE_URL (Render/Supabase)
raw_db_url = os.environ.get("DATABASE_URL", "")
if raw_db_url.startswith("postgres://"):
raw_db_url = raw_db_url.replace("postgres://", "postgresql+psycopg2://", 1)
elif raw_db_url.startswith("postgresql://") and "+psycopg2" not in raw_db_url:
raw_db_url = raw_db_url.replace("postgresql://", "postgresql+psycopg2://", 1)

if not raw_db_url:
raise RuntimeError("DATABASE_URL environment variable is not set!")

engine = create_engine(raw_db_url, future=True)
SessionLocal = scoped_session(sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True))
Base = declarative_base()


# ------------------------------------------------------------------------------
# Models
# ------------------------------------------------------------------------------

class User(Base, UserMixin):
__tablename__ = "users"
id = Column(Integer, primary_key=True)
email = Column(String, unique=True, nullable=False, index=True)
password = Column(String, nullable=False)
created_at = Column(DateTime, nullable=False, server_default=func.now())

# Flask-Login requires get_id(); UserMixin го има.


class Klient(Base):
__tablename__ = "klienti"
id = Column(Integer, primary_key=True)
ime = Column(String, nullable=False)
prezime = Column(String, nullable=True)
datum = Column(Date, nullable=False, server_default=func.current_date())
dolg = Column(Numeric(12, 2), nullable=False, server_default=text("0"))
plateno = Column(Numeric(10, 2), nullable=False, server_default=text("0"))


# ------------------------------------------------------------------------------
# Auth helpers (поддршка и за pbkdf2:sha256 и за bcrypt)
# ------------------------------------------------------------------------------

def hash_password_pbkdf2(plain: str) -> str:
"""Default hashing за нови корисници (pbkdf2)."""
return generate_password_hash(plain) # pbkdf2:sha256


def verify_password(stored_hash: str, plain: str) -> bool:
"""
Проверува лозинка против:
- pbkdf2:sha256 (werkzeug)
- bcrypt $2a/$2b/$2y (passlib, ако е инсталиран)
"""
try:
# pbkdf2 (werkzeug) формат
if stored_hash.startswith("pbkdf2:"):
return check_password_hash(stored_hash, plain)

# bcrypt формат – $2a / $2b / $2y
if stored_hash.startswith("$2") and HAS_PASSLIB:
return bcrypt.verify(plain, stored_hash)
except Exception:
return False
return False


# ------------------------------------------------------------------------------
# Flask-Login
# ------------------------------------------------------------------------------

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


# ------------------------------------------------------------------------------
# DB init & ensure admin
# ------------------------------------------------------------------------------

def ensure_tables():
Base.metadata.create_all(bind=engine)


def ensure_admin():
"""Креира иницијален админ ако го нема (email+password од околина)."""
admin_email = os.environ.get("ADMIN_EMAIL")
admin_password = os.environ.get("ADMIN_PASSWORD")

if not admin_email or not admin_password:
# Не креирaме ако недостигаат креденцијали – само логичко предупредување во консола
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


# ------------------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------------------

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
# Ако имаш templates/login.html – ќе се рендерира. Инаку, едноставен HTML.
try:
return render_template("login.html")
except Exception:
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
# Пробај темплејт; ако го нема, врати едноставен текст.
try:
return render_template("customers.html", klienti=klienti, q="")
except Exception:
return "Logged in ✅", 200
finally:
db.close()


# ------------------------------------------------------------------------------
# App start (Render ќе го ignoriра, но е корисно за локално)
# ------------------------------------------------------------------------------

def _startup():
ensure_tables()
ensure_admin()
app.logger.info("Startup complete.")


_startup()

if __name__ == "__main__":
# Локално стартување
port = int(os.environ.get("PORT", "8000"))
app.run(host="0.0.0.0", port=port, debug=True)
