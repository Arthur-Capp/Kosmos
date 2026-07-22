"""
Dashboard handler for Kosmos Telegram Bot.
Generates web dashboard links for users.
"""

import logging
from telegram import Update, BotCommand
from telegram.ext import ContextTypes, CommandHandler

from database import get_user, generate_web_token
from config import WEB_PORT

logger = logging.getLogger(__name__)

# Multi-language strings
_STRINGS = {
    "dashboard_link": {
        "pt-br": "📊 Acesse seu dashboard:",
        "en": "📊 Access your dashboard:",
        "sr-lat": "📊 Pristupite svom dashboardu:",
    },
    "dashboard_error": {
        "pt-br": "❌ Erro ao gerar link do dashboard. Tente novamente.",
        "en": "❌ Error generating dashboard link. Try again.",
        "sr-lat": "❌ Greška pri generisanju linka za dashboard. Pokušaj ponovo.",
    },
}


def _get_text(key: str, lang: str) -> str:
    """Get translated string."""
    return _STRINGS.get(key, {}).get(lang, _STRINGS.get(key, {}).get("en", key))


async def dashboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /dashboard command.
    Generates or retrieves a web token for the user and sends a dashboard link.
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    # Generate or retrieve existing token
    token = generate_web_token(user_id)

    if not token:
        await update.message.reply_text(_get_text("dashboard_error", user_lang))
        logger.error(f"Failed to generate web token for user {user_id}")
        return

    link = f"http://localhost:{WEB_PORT}/dashboard?token={token}"
    message = f"{_get_text('dashboard_link', user_lang)}\n{link}"

    await update.message.reply_text(message)
    logger.info(f"User {user_id} requested dashboard link")


def register_handlers(application):
    """Register dashboard command handlers."""
    application.add_handler(CommandHandler("dashboard", dashboard_command))
