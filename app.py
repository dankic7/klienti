# -*- coding: utf-8 -*-
import os
from datetime import datetime, date
from decimal import Decimal
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET", "dev-secret-change-me")
import os
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
import os
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")


db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


# ---------------- Models ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(64))
    notes = db.Column(db.Text)
    accounts = db.relationship("Account", backref="customer", cascade="all, delete-orphan")


class Account(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    year = db.Column(db.String(4), nullable=False)
    initial_debt = db.Column(db.Numeric(12,2), default=0)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    payments = db.relationship("Payment", backref="account", cascade="all, delete-orphan")


class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(10), nullable=False)  # ISO yyyy-mm-dd string
    amount = db.Column(db.Numeric(12,2), nullable=False)
    note = db.Column(db.Text)
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# ------------- Helpers -------------
def money(val):
    try:
        d = Decimal(str(val)).quantize(Decimal("0.01"))
    except Exception:
        d = Decimal("0.00")
    return d

def parse_date(s):
    s = (s or "").strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            pass
    return None

def calc_year_balance(account: Account):
    total_paid = sum((p.amount or 0) for p in account.payments)
    return (account.initial_debt or 0) - (total_paid or 0)

def calc_total_balance(c: Customer):
    total = Decimal("0.00")
    for acc in c.accounts:
        total += calc_year_balance(acc)
    return total

with app.app_context():
    db.create_all()
    from os import getenv
    email = getenv("ADMIN_EMAIL", "admin@example.com")
    if not User.query.filter_by(email=email).first():
        u = User(email=email)
        u.set_password("admin123")  # ќе ја смениш после логирање
        db.session.add(u)
        db.session.commit()

# ------------- Auth routes -------------
@app.route("/register", methods=["GET", "POST"])
def register():
    # Allow register only if there are no users yet
    if User.query.count() > 0:
        flash("Регистрација е оневозможена (веќе постои админ).", "warning")
        return redirect(url_for("login"))
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pw = request.form.get("password","")
        if not email or not pw:
            flash("Внесете email и лозинка.", "danger")
            return render_template("register.html")
        u = User(email=email)
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        flash("Успешна регистрација. Најавете се.", "success")
        return redirect(url_for("login"))
    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email","").strip().lower()
        pw = request.form.get("password","")
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(pw):
            login_user(user)
            return redirect(url_for("index"))
        flash("Неточни креденцијали.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


# ------------- Customer CRUD -------------
@app.route("/")
@login_required
def index():
    q = request.args.get("q","").strip().lower()
    customers = Customer.query.order_by(Customer.name.asc()).all()
    if q:
        customers = [c for c in customers if q in (c.name or "").lower() or q in (c.phone or "").lower()]
    balances = {c.id: calc_total_balance(c) for c in customers}
    return render_template("customers.html", customers=customers, balances=balances, q=q)


@app.route("/customer/new", methods=["GET", "POST"])
@login_required
def customer_new():
    if request.method == "POST":
        name = request.form.get("name","").strip()
        phone = request.form.get("phone","").strip()
        notes = request.form.get("notes","").strip()
        if not name:
            flash("Име и презиме е задолжително.", "danger")
            return render_template("customer_form.html", c=None)
        c = Customer(name=name, phone=phone, notes=notes)
        db.session.add(c)
        db.session.commit()
        flash("Муштеријата е креирана.", "success")
        return redirect(url_for("index"))
    return render_template("customer_form.html", c=None)


@app.route("/customer/<int:cid>/edit", methods=["GET", "POST"])
@login_required
def customer_edit(cid):
    c = Customer.query.get_or_404(cid)
    if request.method == "POST":
        c.name = request.form.get("name","").strip()
        c.phone = request.form.get("phone","").strip()
        c.notes = request.form.get("notes","").strip()
        if not c.name:
            flash("Име и презиме е задолжително.", "danger")
            return render_template("customer_form.html", c=c)
        db.session.commit()
        flash("Муштеријата е ажурирана.", "success")
        return redirect(url_for("index"))
    return render_template("customer_form.html", c=c)


@app.route("/customer/<int:cid>/delete", methods=["POST"])
@login_required
def customer_delete(cid):
    c = Customer.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    flash("Муштеријата е избришана.", "success")
    return redirect(url_for("index"))


# ------------- Accounts & Payments -------------
@app.route("/customer/<int:cid>")
@login_required
def customer_detail(cid):
    c = Customer.query.get_or_404(cid)
    # ensure a year is selected
    year = request.args.get("year") or str(date.today().year)
    acc = Account.query.filter_by(customer_id=c.id, year=year).first()
    years = sorted({a.year for a in c.accounts} | {str(date.today().year-1), str(date.today().year), str(date.today().year+1)})
    balance = calc_year_balance(acc) if acc else Decimal("0.00")
    return render_template("customer_detail.html", c=c, acc=acc, years=years, year=year, balance=balance)


@app.route("/customer/<int:cid>/year/select", methods=["POST"])
@login_required
def select_year(cid):
    c = Customer.query.get_or_404(cid)
    year = (request.form.get("year") or "").strip()
    if not (year.isdigit() and len(year)==4):
        flash("Невалидна година.", "danger")
        return redirect(url_for("customer_detail", cid=cid))
    acc = Account.query.filter_by(customer_id=c.id, year=year).first()
    if not acc:
        acc = Account(customer_id=c.id, year=year, initial_debt=0)
        db.session.add(acc)
        db.session.commit()
        flash(f"Додадена година {year}.", "success")
    return redirect(url_for("customer_detail", cid=cid, year=year))


@app.route("/account/<int:aid>/initial", methods=["POST"])
@login_required
def set_initial(aid):
    acc = Account.query.get_or_404(aid)
    try:
        val = Decimal(request.form.get("initial_debt","0").replace(",","."))
        if val < 0:
            raise ValueError
    except Exception:
        flash("Невалиден износ за почетен долг.", "danger")
        return redirect(url_for("customer_detail", cid=acc.customer_id, year=acc.year))
    acc.initial_debt = val
    db.session.commit()
    flash("Почетниот долг е зачуван.", "success")
    return redirect(url_for("customer_detail", cid=acc.customer_id, year=acc.year))


@app.route("/account/<int:aid>/payment/new", methods=["POST"])
@login_required
def payment_new(aid):
    acc = Account.query.get_or_404(aid)
    ds = request.form.get("date","")
    ds_parsed = parse_date(ds)
    if not ds_parsed:
        flash("Невалиден датум.", "danger")
        return redirect(url_for("customer_detail", cid=acc.customer_id, year=acc.year))
    try:
        amt = Decimal(request.form.get("amount","0").replace(",","."))
        if amt <= 0:
            raise ValueError
    except Exception:
        flash("Невалиден износ.", "danger")
        return redirect(url_for("customer_detail", cid=acc.customer_id, year=acc.year))
    note = request.form.get("note","").strip()
    p = Payment(account_id=aid, date=ds_parsed, amount=amt, note=note)
    db.session.add(p)
    db.session.commit()
    flash("Уплатата е додадена.", "success")
    return redirect(url_for("customer_detail", cid=acc.customer_id, year=acc.year))


@app.route("/payment/<int:pid>/edit", methods=["POST"])
@login_required
def payment_edit(pid):
    p = Payment.query.get_or_404(pid)
    ds = request.form.get("date","")
    ds_parsed = parse_date(ds)
    if not ds_parsed:
        flash("Невалиден датум.", "danger")
        return redirect(url_for("customer_detail", cid=p.account.customer_id, year=p.account.year))
    try:
        amt = Decimal(request.form.get("amount","0").replace(",","."))
        if amt <= 0:
            raise ValueError
    except Exception:
        flash("Невалиден износ.", "danger")
        return redirect(url_for("customer_detail", cid=p.account.customer_id, year=p.account.year))
    p.date = ds_parsed
    p.amount = amt
    p.note = request.form.get("note","").strip()
    db.session.commit()
    flash("Уплатата е ажурирана.", "success")
    return redirect(url_for("customer_detail", cid=p.account.customer_id, year=p.account.year))


@app.route("/payment/<int:pid>/delete", methods=["POST"])
@login_required
def payment_delete(pid):
    p = Payment.query.get_or_404(pid)
    cid = p.account.customer_id
    year = p.account.year
    db.session.delete(p)
    db.session.commit()
    flash("Уплатата е избришана.", "success")
    return redirect(url_for("customer_detail", cid=cid, year=year))


# ------------- Exports -------------
def compose_year_report(c: Customer, acc: Account):
    initial = acc.initial_debt or 0
    payments = sorted(acc.payments, key=lambda x: x.date)
    total_paid = sum((p.amount or 0) for p in payments)
    balance = initial - total_paid

    lines = []
    lines.append("===========================================")
    lines.append(f"   ИЗВЕШТАЈ ЗА МУШТЕРИЈА – ГОДИНА: {acc.year}")
    lines.append("===========================================")
    lines.append(f"Датум на извештај: {date.today().isoformat()}")
    lines.append(f"Муштерија : {c.name}")
    lines.append(f"Телефон   : {c.phone or '-'}")
    lines.append("")
    lines.append(f"Почетен долг: {initial:.2f} ден.")
    lines.append("-------------------------------------------")
    lines.append("УПЛАТИ:")
    if payments:
        for i, p in enumerate(payments, 1):
            lines.append(f"{i:02d}. {p.date}  |  {p.amount:.2f} ден.  |  {p.note or ''}")
    else:
        lines.append("Нема евидентирани уплати за оваа година.")
    lines.append("-------------------------------------------")
    lines.append(f"Вкупно уплатено: {total_paid:.2f} ден.")
    lines.append(f"Преостанато салдо: {balance:.2f} ден.")
    lines.append("")
    return "\n".join(lines)

@app.route("/export/<int:cid>/<year>.txt")
@login_required
def export_year(cid, year):
    c = Customer.query.get_or_404(cid)
    acc = Account.query.filter_by(customer_id=c.id, year=str(year)).first()
    if not acc:
        abort(404)
    content = compose_year_report(c, acc).encode("utf-8")
    fname = f"Izvestaj_{c.name.replace(' ','_')}_{year}.txt"
    return send_file(BytesIO(content), mimetype="text/plain; charset=utf-8", as_attachment=True, download_name=fname)

@app.route("/export/<int:cid>/all.txt")
@login_required
def export_all_years_one(cid):
    c = Customer.query.get_or_404(cid)
    years = sorted(c.accounts, key=lambda a: a.year)
    if not years:
        abort(404)
    all_lines = []
    all_lines.append("============================================================")
    all_lines.append("         ЗБИРЕН ИЗВЕШТАЈ ЗА МУШТЕРИЈА (сите години)")
    all_lines.append("============================================================")
    all_lines.append(f"Датум на извештај: {date.today().isoformat()}")
    all_lines.append(f"Муштерија : {c.name}")
    all_lines.append(f"Телефон   : {c.phone or '-'}")
    all_lines.append("")

    grand_initial = Decimal("0.00")
    grand_paid = Decimal("0.00")
    grand_balance = Decimal("0.00")

    for acc in years:
        txt = compose_year_report(c, acc)
        all_lines.append(txt)
        initial = acc.initial_debt or 0
        total_paid = sum((p.amount or 0) for p in acc.payments)
        balance = initial - total_paid
        grand_initial += Decimal(str(initial))
        grand_paid += Decimal(str(total_paid))
        grand_balance += Decimal(str(balance))

    all_lines.append("============================================================")
    all_lines.append("                  ВКУПНИ ЗБИРНИ ВРЕДНОСТИ")
    all_lines.append("============================================================")
    all_lines.append(f"Вкупно почетни долгови (сите години): {grand_initial:.2f} ден.")
    all_lines.append(f"Вкупно уплатено (сите години):        {grand_paid:.2f} ден.")
    all_lines.append(f"Збирно преостанато салдо:             {grand_balance:.2f} ден.")
    all_lines.append("============================================================")
    all_lines.append("")

    content = "\n".join(all_lines).encode("utf-8")
    fname = f"Izvestaj_ZBIRNO_{c.name.replace(' ','_')}.txt"
    return send_file(BytesIO(content), mimetype="text/plain; charset=utf-8", as_attachment=True, download_name=fname)

@app.route("/export/<int:cid>/batch.zip")
@login_required
def export_batch_zip(cid):
    c = Customer.query.get_or_404(cid)
    years = sorted(c.accounts, key=lambda a: a.year)
    if not years:
        abort(404)

    mem = BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for acc in years:
            txt = compose_year_report(c, acc).encode("utf-8")
            fname = f"Izvestaj_{c.name.replace(' ','_')}_{acc.year}.txt"
            zf.writestr(fname, txt)
    mem.seek(0)
    return send_file(mem, mimetype="application/zip", as_attachment=True,
                     download_name=f"Izvestaj_{c.name.replace(' ','_')}_batch.zip")


# ------------- CLI: init db -------------
@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("DB initialized.")
    # create default admin if none
    if User.query.count() == 0:
        email = os.getenv("ADMIN_EMAIL", "admin@example.com")
        u = User(email=email)
        u.set_password("admin123")
        db.session.add(u)
        db.session.commit()
        print(f"Created default admin: {email} / admin123  (change password after login)")


# ------------- Run -------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
