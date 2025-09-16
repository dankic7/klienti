from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import os

app = Flask(__name__)
app.secret_key = "tajna123"  # смени ја оваа тајна

# ---- DATABASE ----
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL").replace(
    "postgres://", "postgresql://"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ---- LOGIN MANAGER ----
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# ---- MODELS ----
class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Klient(db.Model):
    __tablename__ = "klienti"
    id = db.Column(db.Integer, primary_key=True)
    ime = db.Column(db.String(100), nullable=False)
    prezime = db.Column(db.String(100), nullable=False)
    datum = db.Column(db.Date, nullable=True)
    dolg = db.Column(db.Numeric(10, 2), default=0)
    platno = db.Column(db.Numeric(10, 2), default=0)

# ---- LOGIN MANAGER HELPERS ----
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ---- ROUTES ----
@app.route("/")
@login_required
def index():
    q = request.args.get("q", "")
    if q:
        customers = Klient.query.filter(
            (Klient.ime.ilike(f"%{q}%")) | (Klient.prezime.ilike(f"%{q}%"))
        ).all()
    else:
        customers = Klient.query.order_by(Klient.id).all()
    return render_template("customers.html", customers=customers, q=q)

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
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

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        if User.query.filter_by(email=email).first():
            flash("Овој емаил веќе постои", "danger")
            return redirect(url_for("register"))
        hashed_pw = generate_password_hash(password)
        new_user = User(email=email, password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        flash("Корисникот е креиран. Најави се.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")

# ---- START ----
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
