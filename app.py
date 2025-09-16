from flask import Flask, render_template, redirect, url_for, request, flash
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
import psycopg2
import psycopg2.extras
import bcrypt
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "tajna_lozinka")

# ===== LOGIN MANAGER =====
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.init_app(app)

# ===== DATABASE =====
DATABASE_URL = os.environ.get("DATABASE_URL")  # од Render/Supabase

def get_db_connection():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

# ===== USER CLASS =====
class User(UserMixin):
    def __init__(self, id, email, password):
        self.id = id
        self.email = email
        self.password = password

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM users WHERE id = %s", (int(user_id),))
    user = cur.fetchone()
    conn.close()
    if user:
        return User(user["id"], user["email"], user["password"])
    return None

# ===== ROUTES =====

@app.route("/")
@login_required
def index():
    return redirect(url_for("klienti"))  # секогаш оди на муштерии

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM users WHERE email = %s", (email,))
        user = cur.fetchone()
        conn.close()

        if user and bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8")):
            user_obj = User(user["id"], user["email"], user["password"])
            login_user(user_obj)
            return redirect(url_for("klienti"))  # после успешен login
        else:
            flash("Погрешен емаил или лозинка", "danger")

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Успешно се одјавивте.", "success")
    return redirect(url_for("login"))

@app.route("/klienti")
@login_required
def klienti():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute("SELECT * FROM klienti ORDER BY id ASC")
    klienti = cur.fetchall()
    conn.close()
    return render_template("klienti.html", klienti=klienti)

# ===== START =====
if __name__ == "__main__":
    app.run(debug=True)
