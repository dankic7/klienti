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
from dotenv import load_dotenv

# Вчитај .env (локално)
load_dotenv()

# ------------------------------------------------------
# Flask и конфигурација
# ------------------------------------------------------
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET", "dev-secret-change-me")

db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL is not set! Add it in Render Environment.")

# Претвори postgres:// -> postgresql+psycopg2://
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

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
    password = db.Column(db.String(200), nullable=False)

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
        email = request.form.get("email")
        password = request.form.get("password")
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

    k = Klient(ime=ime, prezime=prezime, dolg=dolg, plateno=plateno)
    db.session.add(k)
    db.session.commit()
    flash("Клиентот е успешно додаден!", "success")
    return redirect(url_for("index"))

# ------------------------------------------------------
# Старт и иницијализација (табели + админ)
# ------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # креира табели ако не постојат

        # Креира админ ако го нема
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_pass = os.getenv("ADMIN_PASSWORD", "admin123")
        if admin_email and not User.query.filter_by(email=admin_email).first():
            u = User(email=admin_email, password=generate_password_hash(admin_pass))
            db.session.add(u)
            db.session.commit()
            print(f"✅ Admin created: {admin_email} / {admin_pass}")

    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))


