# -*- coding: utf-8 -*-
import os
from datetime import datetime
from decimal import Decimal

from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import (
    LoginManager, login_user, logout_user, login_required, current_user, UserMixin
)
from werkzeug.security import generate_password_hash, check_password_hash

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
@app.route("/")
@login_required
def index():
    klienti = Klient.query.order_by(Klient.id.desc()).all()
    return render_template("index.html", klienti=klienti)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password") or ""
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for("index"))
        flash("Погрешен емаил или лозинка", "danger")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
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
