# -*- coding: utf-8 -*-
import os
from datetime import datetime, date
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

# Вчитај .env променливи (локално развој)
load_dotenv()

# Иницијализација на Flask
app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET", "dev-secret-change-me")

# PostgreSQL конекција од Render / Supabase
db_url = os.getenv("DATABASE_URL")
if not db_url:
    raise RuntimeError("DATABASE_URL is not set! Please configure in Render Environment.")

# ✅ psycopg2 формат
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql+psycopg2://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Иницијализација на база
db = SQLAlchemy(app)

# Login Manager
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
# Login Manager callback
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
    klienti = Klient.query.all()
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
        else:
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
    ime = request.form.get("ime")
    prezime = request.form.get("prezime")
    dolg = request.form.get("dolg", 0)
    plateno = request.form.get("plateno", 0)

    klient = Klient(
        ime=ime,
        prezime=prezime,
        dolg=Decimal(dolg),
        plateno=Decimal(plateno)
    )
    db.session.add(klient)
    db.session.commit()
    flash("Клиентот е успешно додаден!", "success")
    return redirect(url_for("index"))

# ------------------------------------------------------
# Main
# ------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()  # создава табели ако не постојат
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
