# import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    portfolio = db.execute("SELECT UPPER(stock_symbol) as stock, price, SUM(shares), value FROM transactions WHERE user_id = ? GROUP BY stock_symbol HAVING SUM(shares) != 0", session["user_id"])

    for stocks in portfolio:
        stock = lookup(stocks["stock"])
        price = stock["price"]
        stocks["price"] = price

        value = stocks["SUM(shares)"] * price
        stocks["value"] = value

    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    cash = float(cash[0]["cash"])

    assets = cash
    for stock in portfolio:
        assets += stock["value"]
    assets = assets

    return render_template("/index.html", portfolio=portfolio, cash=cash, assets=assets)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = float(request.form.get("shares"))

        if not lookup(symbol):
            return apology("Invalid stock symbol", 400)
        if shares < 1 or not shares.is_integer:
            return apology("Full shares only, no fractional shares", 400)

        shares = int(shares)
        stock = lookup(symbol)
        price = shares * stock["price"]

        budget = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        budget = float(budget[0]["cash"])

        if budget < price:
            return apology("Insufficient balance")
        else:
            db.execute("UPDATE users SET cash = ? WHERE id = ?", budget - price, session["user_id"])
            date = datetime.now().date()
            time = datetime.now().time()
            db.execute("INSERT INTO transactions (user_id, stock_symbol, price, shares, type, value, date, time) VALUES (?,?,?,?,?,?,?,?)", session["user_id"], symbol, stock["price"], shares, "buy", price, date, time)
            return redirect("/")
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT UPPER(stock_symbol) as stock, price, ABS(shares) as absshares, type, value, date, time FROM transactions WHERE user_id = ?", session["user_id"])

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")

        if not lookup(symbol):
            return apology("Invalid stock symbol")

        stock = lookup(symbol)

        return render_template("quoted.html", stock=stock)

    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST
    if request.method == "POST":

        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # Ensure username was submitted
        if not username:
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 400)

        # Ensure verify password matches
        elif (confirmation != password):
            return apology("passwords must match", 400)

        # Check for duplicate username
        else:
            try:
                db.execute("INSERT INTO users (username, hash) VALUES (?,?)", username, generate_password_hash(password))
            except ValueError:
                return apology("username taken. choose unique username", 400)

        # Redirect user to login page
        return redirect("/login")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        symbol = request.form.get("symbol")
        shares = float(request.form.get("shares"))

        portfolio = db.execute("SELECT UPPER(stock_symbol) as stock, ROUND(AVG(price), 2), SUM(shares) FROM transactions WHERE user_id = ? GROUP BY stock_symbol", session["user_id"])

        for stocks in portfolio:
            if stocks["stock"] == symbol:
                stock = lookup(symbol)
                stock_shares = stocks["SUM(shares)"]
                break
        else:
            return apology("Invalid stock symbol")

        if shares < 1 or not shares.is_integer:
            return apology("Full shares only, no fractional shares")
        if shares > stock_shares:
            return apology("Shares selected exceed owned shares")

        shares = int(shares)
        price = shares * stock["price"]

        budget = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        budget = float(budget[0]["cash"])

        db.execute("UPDATE users SET cash = ? WHERE id = ?", budget + price, session["user_id"])
        date = datetime.now().date()
        time = datetime.now().time()
        db.execute("INSERT INTO transactions (user_id, stock_symbol, price, shares, type, value, date, time) VALUES (?,?,?,?,?,?,?,?)", session["user_id"], symbol.lower(), stock["price"], -shares, "sell", price, date, time)

        return redirect("/")

    else:
        portfolio = db.execute("SELECT UPPER(stock_symbol) as stock, SUM(shares) FROM transactions WHERE user_id = ? GROUP BY stock_symbol", session["user_id"])

        return render_template("sell.html", portfolio=portfolio)


@app.route("/wallet", methods=["GET", "POST"])
@login_required
def wallet():
    """Topup or withdraw cash"""
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
    cash = float(cash[0]["cash"])

    if request.method == "POST":
        update = float(request.form.get("amount"))
        if update < 0:
            return apology("Invalid amount")

        if request.form["update"] == "topup":
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash + update, session["user_id"])

        else:
            if update > cash:
                return apology("Insufficient cash balance")
            db.execute("UPDATE users SET cash = ? WHERE id = ?", cash - update, session["user_id"])

        return redirect("/")

    else:
        return render_template("wallet.html", cash=cash)
