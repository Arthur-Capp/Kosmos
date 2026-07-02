"""
Today and Tomorrow handlers for Kosmos Telegram Bot.
Shows user's appointments for today or tomorrow on demand.
"""

import logging
from datetime import datetime, timedelta
import pytz
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from database import get_user, get_user_reminders_by_date

logger = logging.getLogger(__name__)


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /hoje command - show today's appointments."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"
    user_timezone = user.get("timezone", "America/Sao_Paulo") if user else "America/Sao_Paulo"

    # Get today's date in user's timezone
    tz = pytz.timezone(user_timezone)
    today = datetime.now(tz).date()

    reminders = get_user_reminders_by_date(user_id, today)

    if not reminders:
        if user_lang == "pt-br":
            await update.message.reply_text("📅 Você não tem compromissos hoje.")
        elif user_lang == "sr-lat":
            await update.message.reply_text("📅 Nemate zakazanih obaveza danas.")
        else:
            await update.message.reply_text("📅 You have no appointments today.")
        return

    # Build message
    date_str = today.strftime("%d/%m/%Y")
    if user_lang == "pt-br":
        message = f"📅 *Hoje ({date_str}) seus compromissos são:*\n\n"
    elif user_lang == "sr-lat":
        message = f"📅 *Danas ({date_str}) vaše obaveze su:*\n\n"
    else:
        message = f"📅 *Today ({date_str}) your appointments are:*\n\n"

    for r in reminders:
        # Parse scheduled_time to get time string
        scheduled = r.get("scheduled_time")
        if isinstance(scheduled, str):
            try:
                scheduled_dt = datetime.strptime(scheduled, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    scheduled_dt = datetime.strptime(scheduled, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    scheduled_dt = None
        else:
            scheduled_dt = scheduled
        if scheduled_dt:
            time_str = scheduled_dt.strftime("%H:%M")
        else:
            time_str = "??:??"
        message += f"• {time_str} - {r.get('message_text', 'N/A')}\n"

    await update.message.reply_text(message, parse_mode="Markdown")
    logger.info(f"User {user_id} requested today's appointments")


async def tomorrow_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /amanha command - show tomorrow's appointments."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"
    user_timezone = user.get("timezone", "America/Sao_Paulo") if user else "America/Sao_Paulo"

    # Get tomorrow's date in user's timezone
    tz = pytz.timezone(user_timezone)
    tomorrow = (datetime.now(tz) + timedelta(days=1)).date()

    reminders = get_user_reminders_by_date(user_id, tomorrow)

    if not reminders:
        if user_lang == "pt-br":
            await update.message.reply_text("📅 Você não tem compromissos amanhã.")
        elif user_lang == "sr-lat":
            await update.message.reply_text("📅 Nemate zakazanih obaveza sutra.")
        else:
            await update.message.reply_text("📅 You have no appointments tomorrow.")
        return

    # Build message
    date_str = tomorrow.strftime("%d/%m/%Y")
    if user_lang == "pt-br":
        message = f"📅 *Amanhã ({date_str}) seus compromissos são:*\n\n"
    elif user_lang == "sr-lat":
        message = f"📅 *Sutra ({date_str}) vaše obaveze su:*\n\n"
    else:
        message = f"📅 *Tomorrow ({date_str}) your appointments are:*\n\n"

    for r in reminders:
        scheduled = r.get("scheduled_time")
        if isinstance(scheduled, str):
            try:
                scheduled_dt = datetime.strptime(scheduled, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    scheduled_dt = datetime.strptime(scheduled, "%Y-%m-%d %H:%M:%S.%f")
                except ValueError:
                    scheduled_dt = None
        else:
            scheduled_dt = scheduled
        if scheduled_dt:
            time_str = scheduled_dt.strftime("%H:%M")
        else:
            time_str = "??:??"
        message += f"• {time_str} - {r.get('message_text', 'N/A')}\n"

    await update.message.reply_text(message, parse_mode="Markdown")
    logger.info(f"User {user_id} requested tomorrow's appointments")


def register_handlers(application):
    """Register today and tomorrow command handlers."""
    application.add_handler(CommandHandler("hoje", today_command))
    application.add_handler(CommandHandler("amanha", tomorrow_command))
