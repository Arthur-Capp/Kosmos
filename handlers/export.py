"""
Export handler for Kosmos Telegram Bot.
Exports all user reminders as a downloadable text file.
"""

import logging
from io import BytesIO
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from database import get_user, get_user_reminders

logger = logging.getLogger(__name__)


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /export command - export all reminders as a text file."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"
    user_timezone = user.get("timezone", "America/Sao_Paulo") if user else "America/Sao_Paulo"

    reminders = get_user_reminders(user_id, status="pending")

    if not reminders:
        if user_lang == "pt-br":
            await update.message.reply_text("📭 Você não tem lembretes para exportar.")
        elif user_lang == "sr-lat":
            await update.message.reply_text("📭 Nemate podsetnika za izvoz.")
        else:
            await update.message.reply_text("📭 You have no reminders to export.")
        return

    # Build export content
    tz = pytz.timezone(user_timezone)
    now = datetime.now(tz)

    if user_lang == "pt-br":
        header = f"=== Exportação de Lembretes - Kosmos ===\n"
        header += f"Data: {now.strftime('%d/%m/%Y %H:%M')}\n"
        header += f"Total de lembretes: {len(reminders)}\n"
        header += f"{'=' * 40}\n\n"
    elif user_lang == "sr-lat":
        header = f"=== Izvoz Podsetnika - Kosmos ===\n"
        header += f"Datum: {now.strftime('%d/%m/%Y %H:%M')}\n"
        header += f"Ukupno podsetnika: {len(reminders)}\n"
        header += f"{'=' * 40}\n\n"
    else:
        header = f"=== Reminder Export - Kosmos ===\n"
        header += f"Date: {now.strftime('%d/%m/%Y %H:%M')}\n"
        header += f"Total reminders: {len(reminders)}\n"
        header += f"{'=' * 40}\n\n"

    lines = []
    for i, r in enumerate(reminders, 1):
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
            date_str = scheduled_dt.strftime("%d/%m/%Y %H:%M")
        else:
            date_str = "N/A"

        recurring = ""
        if r.get("is_recurring"):
            recurring = " [Recorrente]"

        lines.append(f"{i}. {date_str} - {r.get('message_text', 'N/A')}{recurring}")

    content = header + "\n".join(lines)

    # Send as file
    bio = BytesIO(content.encode("utf-8"))
    bio.name = f"lembretes_{now.strftime('%Y%m%d')}.txt"

    await update.message.reply_document(
        document=bio,
        filename=f"lembretes_{now.strftime('%Y%m%d')}.txt",
        caption="📄 Exportação de lembretes" if user_lang == "pt-br" else
                "📄 Izvoz podsetnika" if user_lang == "sr-lat" else
                "📄 Reminder export"
    )
    logger.info(f"User {user_id} exported {len(reminders)} reminders")


def register_handlers(application):
    """Register export command handler."""
    application.add_handler(CommandHandler("export", export_command))
