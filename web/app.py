"""
Flask web dashboard for Kosmos Telegram Bot.
Provides web-based visualization for reminders, shopping lists, and finances.
"""

import logging
import threading
from datetime import datetime

from flask import Flask, render_template, jsonify, request, abort

from config import WEB_SECRET, WEB_PORT
from database import (
    get_user_by_web_token,
    get_user,
    get_balance,
    get_monthly_summary,
    get_category_summary,
    get_recent_transactions,
    get_transactions,
    get_user_reminders,
    get_active_shopping_lists,
    get_shopping_items,
)

logger = logging.getLogger(__name__)

app = Flask(__name__)


# ==================== TOKEN VALIDATION ====================

def validate_token(token: str):
    """
    Validate the web token and return the user dict.
    Aborts with 403 if invalid.
    """
    if not token:
        abort(403)

    user = get_user_by_web_token(token)
    if not user:
        abort(403)

    return user


# ==================== ERROR HANDLERS ====================

@app.errorhandler(403)
def forbidden_error(e):
    """Handle 403 errors with a nice template."""
    return render_template("error.html", message="Token inválido ou expirado."), 403


# ==================== PAGE ROUTES ====================

@app.route("/")
def index():
    """Redirect to dashboard if token is valid, otherwise show error."""
    token = request.args.get("token", "")
    user = validate_token(token)
    return render_template("dashboard.html", user=user, token=token)


@app.route("/dashboard")
def dashboard():
    """Dashboard overview page."""
    token = request.args.get("token", "")
    user = validate_token(token)

    user_id = user["telegram_id"]
    user_lang = user.get("language", "en")
    now = datetime.now()

    # Get data for dashboard
    balance = get_balance(user_id)
    reminders = get_user_reminders(user_id, status="pending")[:3]
    lists = get_active_shopping_lists(user_id)[:3]
    recent_txns = get_recent_transactions(user_id, limit=5)

    # Category summary for mini pie chart
    categories = get_category_summary(user_id, now.month, now.year)

    return render_template(
        "dashboard.html",
        user=user,
        token=token,
        balance=balance,
        reminders=reminders,
        lists=lists,
        recent_txns=recent_txns,
        categories=categories,
        user_lang=user_lang,
    )


@app.route("/finance")
def finance():
    """Finance overview page with charts."""
    token = request.args.get("token", "")
    user = validate_token(token)

    user_id = user["telegram_id"]
    user_lang = user.get("language", "en")
    now = datetime.now()

    # Get current month data
    balance = get_balance(user_id)
    summary = get_monthly_summary(user_id, now.month, now.year)
    categories = get_category_summary(user_id, now.month, now.year)
    transactions = get_transactions(user_id, now.month, now.year)

    return render_template(
        "finance.html",
        user=user,
        token=token,
        balance=balance,
        summary=summary,
        categories=categories,
        transactions=transactions,
        user_lang=user_lang,
        month=now.month,
        year=now.year,
    )


@app.route("/shopping")
def shopping():
    """Shopping lists page."""
    token = request.args.get("token", "")
    user = validate_token(token)

    user_id = user["telegram_id"]
    user_lang = user.get("language", "en")

    lists = get_active_shopping_lists(user_id)
    items_by_list = {}
    for lst in lists:
        items_by_list[lst["id"]] = get_shopping_items(lst["id"])

    return render_template(
        "shopping.html",
        user=user,
        token=token,
        lists=lists,
        items_by_list=items_by_list,
        user_lang=user_lang,
    )


@app.route("/reminders")
def reminders():
    """Reminders page."""
    token = request.args.get("token", "")
    user = validate_token(token)

    user_id = user["telegram_id"]
    user_lang = user.get("language", "en")

    all_reminders = get_user_reminders(user_id, status="pending")

    return render_template(
        "reminders.html",
        user=user,
        token=token,
        reminders=all_reminders,
        user_lang=user_lang,
    )


# ==================== API ROUTES (JSON for Chart.js) ====================

@app.route("/api/finance/data")
def api_finance_data():
    """JSON endpoint with finance data for Chart.js."""
    token = request.args.get("token", "")
    user = validate_token(token)

    user_id = user["telegram_id"]
    now = datetime.now()

    # Category summary for pie chart (current month)
    categories = get_category_summary(user_id, now.month, now.year)

    # Get monthly income/expense for last 6 months
    monthly_data = []
    for i in range(5, -1, -1):
        m = now.month - i
        y = now.year
        while m < 1:
            m += 12
            y -= 1
        while m > 12:
            m -= 12
            y += 1

        summary = get_monthly_summary(user_id, m, y)
        monthly_data.append({
            "month": m,
            "year": y,
            "income": summary["total_income"],
            "expense": summary["total_expense"],
            "balance": summary["balance"],
        })

    balance = get_balance(user_id)

    return jsonify({
        "categories": categories,
        "monthly": monthly_data,
        "balance": balance,
    })


@app.route("/api/shopping/data")
def api_shopping_data():
    """JSON endpoint with shopping data."""
    token = request.args.get("token", "")
    user = validate_token(token)

    user_id = user["telegram_id"]

    lists = get_active_shopping_lists(user_id)
    data = []
    for lst in lists:
        items = get_shopping_items(lst["id"])
        data.append({
            "id": lst["id"],
            "name": lst["name"],
            "category": lst.get("category", "geral"),
            "item_count": lst.get("item_count", 0),
            "pending_count": lst.get("pending_count", 0),
            "items": items,
        })

    return jsonify(data)


@app.route("/api/reminders/data")
def api_reminders_data():
    """JSON endpoint with upcoming reminders."""
    token = request.args.get("token", "")
    user = validate_token(token)

    user_id = user["telegram_id"]

    reminders = get_user_reminders(user_id, status="pending")

    data = []
    for r in reminders:
        data.append({
            "id": r["id"],
            "message": r["message_text"],
            "scheduled": r["scheduled_time"],
            "status": r["status"],
        })

    return jsonify(data)


# ==================== FLASK STARTUP ====================

def start_flask():
    """Start Flask web server in a daemon thread."""
    thread = threading.Thread(
        target=app.run,
        kwargs={"host": "0.0.0.0", "port": WEB_PORT, "debug": False, "use_reloader": False},
        daemon=True,
    )
    thread.start()
    logger.info(f"Flask web dashboard started on port {WEB_PORT}")


if __name__ == "__main__":
    # For direct testing
    from config import setup_logging
    setup_logging()
    app.run(host="0.0.0.0", port=WEB_PORT, debug=True)
