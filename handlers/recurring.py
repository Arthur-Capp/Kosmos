"""
Recurring reminder handler for Kosmos Telegram Bot.
Handles /recurring command with conversation flow for creating recurring reminders.
"""

import json
import logging
from datetime import datetime, time, timedelta
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters
)

from database import create_reminder, get_user
from i18n import get_text
from parsers.time_parser import parse_time

logger = logging.getLogger(__name__)

# Conversation states
(
    MESSAGE,
    RECURRENCE_TYPE,
    INTERVAL_DAYS,
    WEEKLY_DAYS,
    MONTHLY_DAY,
    TIME_INPUT,
    DURATION_CHOICE,
    DURATION_INPUT,
    CONFIRM
) = range(9)


async def recurring_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Start the recurring reminder creation conversation.
    """
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        await update.message.reply_text(
            "Please start the bot first with /start"
        )
        return ConversationHandler.END

    user_lang = user.get('language', 'en')

    # Initialize conversation data
    context.user_data['recurring'] = {}

    if user_lang == "sr-lat":
        intro = "📋 *Kreiranje ponavljajućeg podsetnika*\n\n"
        prompt = "Unesi tekst podsetnika:\n"
        cancel_hint = "_/cancel za otkazivanje_"
    elif user_lang == "pt-br":
        intro = "📋 *Criar lembrete recorrente*\n\n"
        prompt = "Digite o texto do lembrete:\n"
        cancel_hint = "_/cancel para cancelar_"
    else:
        intro = "📋 *Create recurring reminder*\n\n"
        prompt = "Enter the reminder text:\n"
        cancel_hint = "_/cancel to cancel_"

    await update.message.reply_text(
        f"{intro}{prompt}{cancel_hint}",
        parse_mode="Markdown"
    )

    return MESSAGE


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle reminder message text input.
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get('language', 'en') if user else 'en'

    message_text = update.message.text.strip()

    if not message_text:
        if user_lang == "sr-lat":
            text = "Poruka ne može biti prazna. Pokušaj ponovo:"
        elif user_lang == "pt-br":
            text = "A mensagem não pode estar vazia. Tente novamente:"
        else:
            text = "Message cannot be empty. Try again:"
        await update.message.reply_text(text)
        return MESSAGE

    # Save message to context
    context.user_data['recurring']['message'] = message_text

    # Show recurrence type options with cancel button
    if user_lang == "sr-lat":
        btn_daily = "📅 Svaki dan"
        btn_interval = "🔢 Svaki X dan"
        btn_weekly = "📆 Dani u nedelji"
        btn_monthly = "📌 Mesečno"
        btn_cancel = "❌ Otkaži"
        header_text = f"✅ Podsetnik: *{message_text}*\n\nIzaberi tip ponavljanja:"
    elif user_lang == "pt-br":
        btn_daily = "📅 Todos os dias"
        btn_interval = "🔢 A cada X dias"
        btn_weekly = "📆 Dias da semana"
        btn_monthly = "📌 Mensal"
        btn_cancel = "❌ Cancelar"
        header_text = f"✅ Lembrete: *{message_text}*\n\nEscolha o tipo de recorrência:"
    else:
        btn_daily = "📅 Every day"
        btn_interval = "🔢 Every X days"
        btn_weekly = "📆 Days of week"
        btn_monthly = "📌 Monthly"
        btn_cancel = "❌ Cancel"
        header_text = f"✅ Reminder: *{message_text}*\n\nChoose recurrence type:"

    keyboard = [
        [
            InlineKeyboardButton(btn_daily, callback_data="rec_type_daily"),
            InlineKeyboardButton(btn_interval, callback_data="rec_type_interval"),
        ],
        [
            InlineKeyboardButton(btn_weekly, callback_data="rec_type_weekly"),
            InlineKeyboardButton(btn_monthly, callback_data="rec_type_monthly"),
        ],
        [
            InlineKeyboardButton(btn_cancel, callback_data="rec_type_cancel"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        header_text,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

    return RECURRENCE_TYPE


async def handle_recurrence_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle recurrence type selection.
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get('language', 'en') if user else 'en'

    query = update.callback_query
    await query.answer()

    rec_type = query.data.replace("rec_type_", "")

    if rec_type == "cancel":
        if user_lang == "sr-lat":
            cancel_text = "❌ Otkazano. Koristi /recurring da počneš ponovo."
        elif user_lang == "pt-br":
            cancel_text = "❌ Cancelado. Use /recurring para começar novamente."
        else:
            cancel_text = "❌ Canceled. Use /recurring to start again."
        await query.edit_message_text(cancel_text)
        context.user_data.pop('recurring', None)
        return ConversationHandler.END

    context.user_data['recurring']['type'] = rec_type

    if rec_type == "daily":
        # Go directly to time input
        if user_lang == "sr-lat":
            text = "✅ Tip: *Svaki dan*\n\nUnesi vreme (npr. 09:00, 14:30):\n_/cancel za otkazivanje_"
        elif user_lang == "pt-br":
            text = "✅ Tipo: *Todos os dias*\n\nDigite o horário (ex.: 09:00, 14:30):\n_/cancel para cancelar_"
        else:
            text = "✅ Type: *Every day*\n\nEnter the time (e.g. 09:00, 14:30):\n_/cancel to cancel_"
        await query.edit_message_text(text, parse_mode="Markdown")
        return TIME_INPUT

    elif rec_type == "interval":
        # Ask for number of days
        if user_lang == "sr-lat":
            text = "✅ Tip: *Svaki X dan*\n\nUnesi broj dana (npr. 3 za svaka 3 dana):\n_/cancel za otkazivanje_"
        elif user_lang == "pt-br":
            text = "✅ Tipo: *A cada X dias*\n\nDigite o número de dias (ex.: 3 para cada 3 dias):\n_/cancel para cancelar_"
        else:
            text = "✅ Type: *Every X days*\n\nEnter number of days (e.g. 3 for every 3 days):\n_/cancel to cancel_"
        await query.edit_message_text(text, parse_mode="Markdown")
        return INTERVAL_DAYS

    elif rec_type == "weekly":
        # Show day selection
        context.user_data['recurring']['selected_days'] = []
        keyboard = create_weekday_keyboard([], user_lang)
        reply_markup = InlineKeyboardMarkup(keyboard)

        if user_lang == "sr-lat":
            text = "✅ Tip: *Dani u nedelji*\n\nIzaberi dane (možeš više):"
        elif user_lang == "pt-br":
            text = "✅ Tipo: *Dias da semana*\n\nEscolha os dias (pode selecionar vários):"
        else:
            text = "✅ Type: *Days of week*\n\nSelect days (you can choose multiple):"
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )
        return WEEKLY_DAYS

    elif rec_type == "monthly":
        # Ask for day of month
        if user_lang == "sr-lat":
            text = "✅ Tip: *Mesečno*\n\nUnesi dan u mesecu (1-31):\n_/cancel za otkazivanje_"
        elif user_lang == "pt-br":
            text = "✅ Tipo: *Mensal*\n\nDigite o dia do mês (1-31):\n_/cancel para cancelar_"
        else:
            text = "✅ Type: *Monthly*\n\nEnter day of month (1-31):\n_/cancel to cancel_"
        await query.edit_message_text(text, parse_mode="Markdown")
        return MONTHLY_DAY


def create_weekday_keyboard(selected_days, user_lang="en"):
    """
    Create inline keyboard for weekday selection with checkmarks.
    """
    if user_lang == "sr-lat":
        days = [
            ("Pon", "monday"),
            ("Uto", "tuesday"),
            ("Sre", "wednesday"),
            ("Čet", "thursday"),
            ("Pet", "friday"),
            ("Sub", "saturday"),
            ("Ned", "sunday")
        ]
        done_label = "✅ Gotovo"
        cancel_label = "❌ Otkaži"
    elif user_lang == "pt-br":
        days = [
            ("Seg", "monday"),
            ("Ter", "tuesday"),
            ("Qua", "wednesday"),
            ("Qui", "thursday"),
            ("Sex", "friday"),
            ("Sáb", "saturday"),
            ("Dom", "sunday")
        ]
        done_label = "✅ Pronto"
        cancel_label = "❌ Cancelar"
    else:
        days = [
            ("Mon", "monday"),
            ("Tue", "tuesday"),
            ("Wed", "wednesday"),
            ("Thu", "thursday"),
            ("Fri", "friday"),
            ("Sat", "saturday"),
            ("Sun", "sunday")
        ]
        done_label = "✅ Done"
        cancel_label = "❌ Cancel"

    keyboard = []
    row = []

    for label, day in days:
        checkmark = "✓ " if day in selected_days else ""
        button = InlineKeyboardButton(
            f"{checkmark}{label}",
            callback_data=f"weekday_{day}"
        )
        row.append(button)

        if len(row) == 3:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    # Add "Done" and "Cancel" buttons
    keyboard.append([
        InlineKeyboardButton(done_label, callback_data="weekday_done"),
        InlineKeyboardButton(cancel_label, callback_data="weekday_cancel"),
    ])

    return keyboard


async def handle_weekday_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle weekday toggle selection.
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get('language', 'en') if user else 'en'

    query = update.callback_query
    await query.answer()

    if query.data == "weekday_cancel":
        if user_lang == "sr-lat":
            cancel_text = "❌ Otkazano. Koristi /recurring da počneš ponovo."
        elif user_lang == "pt-br":
            cancel_text = "❌ Cancelado. Use /recurring para começar novamente."
        else:
            cancel_text = "❌ Canceled. Use /recurring to start again."
        await query.edit_message_text(cancel_text)
        context.user_data.pop('recurring', None)
        return ConversationHandler.END

    if query.data == "weekday_done":
        selected_days = context.user_data['recurring'].get('selected_days', [])

        if not selected_days:
            if user_lang == "sr-lat":
                alert = "Molim te izaberi bar jedan dan!"
            elif user_lang == "pt-br":
                alert = "Por favor, escolha pelo menos um dia!"
            else:
                alert = "Please select at least one day!"
            await query.answer(alert, show_alert=True)
            return WEEKLY_DAYS

        # Save and proceed to time input
        if user_lang == "sr-lat":
            header = "✅ Dani:"
            time_prompt = "Unesi vreme (npr. 09:00, 14:30):\n_/cancel za otkazivanje_"
        elif user_lang == "pt-br":
            header = "✅ Dias:"
            time_prompt = "Digite o horário (ex.: 09:00, 14:30):\n_/cancel para cancelar_"
        else:
            header = "✅ Days:"
            time_prompt = "Enter the time (e.g. 09:00, 14:30):\n_/cancel to cancel_"
        await query.edit_message_text(
            f"{header} *{', '.join([d.capitalize() for d in selected_days])}*\n\n"
            f"{time_prompt}",
            parse_mode="Markdown"
        )
        return TIME_INPUT

    # Toggle day selection
    day = query.data.replace("weekday_", "")
    selected_days = context.user_data['recurring'].get('selected_days', [])

    if day in selected_days:
        selected_days.remove(day)
    else:
        selected_days.append(day)

    context.user_data['recurring']['selected_days'] = selected_days

    # Update keyboard
    keyboard = create_weekday_keyboard(selected_days, user_lang)
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_reply_markup(reply_markup=reply_markup)

    return WEEKLY_DAYS


async def handle_interval_days(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle interval days input.
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get('language', 'en') if user else 'en'

    try:
        days = int(update.message.text.strip())

        if days < 1 or days > 365:
            if user_lang == "sr-lat":
                text = "Broj dana mora biti između 1 i 365. Pokušaj ponovo:"
            elif user_lang == "pt-br":
                text = "O número de dias deve estar entre 1 e 365. Tente novamente:"
            else:
                text = "Number of days must be between 1 and 365. Try again:"
            await update.message.reply_text(text)
            return INTERVAL_DAYS

        context.user_data['recurring']['interval'] = days

        if user_lang == "sr-lat":
            text = f"✅ Interval: *Svaka {days} dana*\n\nUnesi vreme (npr. 09:00, 14:30):\n_/cancel za otkazivanje_"
        elif user_lang == "pt-br":
            text = f"✅ Intervalo: *A cada {days} dias*\n\nDigite o horário (ex.: 09:00, 14:30):\n_/cancel para cancelar_"
        else:
            text = f"✅ Interval: *Every {days} days*\n\nEnter the time (e.g. 09:00, 14:30):\n_/cancel to cancel_"
        await update.message.reply_text(text, parse_mode="Markdown")
        return TIME_INPUT

    except ValueError:
        if user_lang == "sr-lat":
            text = "Molim te unesi validan broj. Pokušaj ponovo:"
        elif user_lang == "pt-br":
            text = "Por favor, digite um número válido. Tente novamente:"
        else:
            text = "Please enter a valid number. Try again:"
        await update.message.reply_text(text)
        return INTERVAL_DAYS


async def handle_monthly_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle monthly day input.
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get('language', 'en') if user else 'en'

    try:
        day = int(update.message.text.strip())

        if day < 1 or day > 31:
            if user_lang == "sr-lat":
                text = "Dan mora biti između 1 i 31. Pokušaj ponovo:"
            elif user_lang == "pt-br":
                text = "O dia deve estar entre 1 e 31. Tente novamente:"
            else:
                text = "Day must be between 1 and 31. Try again:"
            await update.message.reply_text(text)
            return MONTHLY_DAY

        context.user_data['recurring']['day_of_month'] = day

        if user_lang == "sr-lat":
            text = f"✅ Dan u mesecu: *{day}.*\n\nUnesi vreme (npr. 09:00, 14:30):\n_/cancel za otkazivanje_"
        elif user_lang == "pt-br":
            text = f"✅ Dia do mês: *{day}*\n\nDigite o horário (ex.: 09:00, 14:30):\n_/cancel para cancelar_"
        else:
            text = f"✅ Day of month: *{day}*\n\nEnter the time (e.g. 09:00, 14:30):\n_/cancel to cancel_"
        await update.message.reply_text(text, parse_mode="Markdown")
        return TIME_INPUT

    except ValueError:
        if user_lang == "sr-lat":
            text = "Molim te unesi validan broj. Pokušaj ponovo:"
        elif user_lang == "pt-br":
            text = "Por favor, digite um número válido. Tente novamente:"
        else:
            text = "Please enter a valid number. Try again:"
        await update.message.reply_text(text)
        return MONTHLY_DAY


async def handle_time_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle time input and show duration choice.
    """
    time_str = update.message.text.strip()
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get('language', 'en') if user else 'en'

    # Parse time
    parsed_time = parse_time(time_str)

    if not parsed_time:
        if user_lang == "sr-lat":
            text = "❌ Neispravan format vremena. Pokušaj ponovo (npr. 09:00, 14:30):"
        elif user_lang == "pt-br":
            text = "❌ Formato de horário inválido. Tente novamente (ex.: 09:00, 14:30):"
        else:
            text = "❌ Invalid time format. Try again (e.g. 09:00, 14:30):"
        await update.message.reply_text(text)
        return TIME_INPUT

    context.user_data['recurring']['time'] = parsed_time

    # Show duration choice
    if user_lang == "sr-lat":
        btn_forever = "♾️ Zauvek"
        btn_7 = "7 dana"
        btn_14 = "14 dana"
        btn_30 = "30 dana"
        btn_custom = "📝 Unesi broj"
        btn_cancel = "❌ Otkaži"
        prompt = f"✅ Vreme: *{parsed_time.strftime('%H:%M')}*\n\nNa koliko dana želiš da se ponavlja?"
    elif user_lang == "pt-br":
        btn_forever = "♾️ Para sempre"
        btn_7 = "7 dias"
        btn_14 = "14 dias"
        btn_30 = "30 dias"
        btn_custom = "📝 Digite um número"
        btn_cancel = "❌ Cancelar"
        prompt = f"✅ Horário: *{parsed_time.strftime('%H:%M')}*\n\nPor quantos dias deseja repetir?"
    else:
        btn_forever = "♾️ Forever"
        btn_7 = "7 days"
        btn_14 = "14 days"
        btn_30 = "30 days"
        btn_custom = "📝 Enter number"
        btn_cancel = "❌ Cancel"
        prompt = f"✅ Time: *{parsed_time.strftime('%H:%M')}*\n\nFor how many days should it repeat?"

    keyboard = [
        [
            InlineKeyboardButton(btn_forever, callback_data="duration_forever"),
        ],
        [
            InlineKeyboardButton(btn_7, callback_data="duration_7"),
            InlineKeyboardButton(btn_14, callback_data="duration_14"),
        ],
        [
            InlineKeyboardButton(btn_30, callback_data="duration_30"),
            InlineKeyboardButton(btn_custom, callback_data="duration_custom"),
        ],
        [
            InlineKeyboardButton(btn_cancel, callback_data="duration_cancel"),
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        prompt,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

    return DURATION_CHOICE


async def handle_duration_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle duration selection for recurring reminder.
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get('language', 'en') if user else 'en'

    query = update.callback_query
    await query.answer()

    choice = query.data.replace("duration_", "")

    if choice == "cancel":
        if user_lang == "sr-lat":
            cancel_text = "❌ Otkazano. Koristi /recurring da počneš ponovo."
        elif user_lang == "pt-br":
            cancel_text = "❌ Cancelado. Use /recurring para começar novamente."
        else:
            cancel_text = "❌ Canceled. Use /recurring to start again."
        await query.edit_message_text(cancel_text)
        context.user_data.pop('recurring', None)
        return ConversationHandler.END

    if choice == "custom":
        if user_lang == "sr-lat":
            text = "Unesi broj dana (1-365):\n_/cancel za otkazivanje_"
        elif user_lang == "pt-br":
            text = "Digite o número de dias (1-365):\n_/cancel para cancelar_"
        else:
            text = "Enter number of days (1-365):\n_/cancel to cancel_"
        await query.edit_message_text(text, parse_mode="Markdown")
        return DURATION_INPUT

    if choice == "forever":
        context.user_data['recurring']['duration_days'] = None
    else:
        context.user_data['recurring']['duration_days'] = int(choice)

    return await _show_confirmation(query, context, user_lang)


async def handle_duration_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle custom duration input (number of days).
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get('language', 'en') if user else 'en'

    try:
        days = int(update.message.text.strip())

        if days < 1 or days > 365:
            if user_lang == "sr-lat":
                text = "Broj dana mora biti između 1 i 365. Pokušaj ponovo:"
            elif user_lang == "pt-br":
                text = "O número de dias deve estar entre 1 e 365. Tente novamente:"
            else:
                text = "Number of days must be between 1 and 365. Try again:"
            await update.message.reply_text(text)
            return DURATION_INPUT

        context.user_data['recurring']['duration_days'] = days

        # Build and send confirmation summary
        rec_data = context.user_data['recurring']
        summary = _build_summary(rec_data, user_lang)

        if user_lang == "sr-lat":
            btn_confirm = "✅ Potvrdi"
            btn_cancel = "❌ Otkaži"
        elif user_lang == "pt-br":
            btn_confirm = "✅ Confirmar"
            btn_cancel = "❌ Cancelar"
        else:
            btn_confirm = "✅ Confirm"
            btn_cancel = "❌ Cancel"

        keyboard = [
            [
                InlineKeyboardButton(btn_confirm, callback_data="confirm_yes"),
                InlineKeyboardButton(btn_cancel, callback_data="confirm_no"),
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            summary,
            parse_mode="Markdown",
            reply_markup=reply_markup
        )

        return CONFIRM

    except ValueError:
        if user_lang == "sr-lat":
            text = "Molim te unesi validan broj. Pokušaj ponovo:"
        elif user_lang == "pt-br":
            text = "Por favor, digite um número válido. Tente novamente:"
        else:
            text = "Please enter a valid number. Try again:"
        await update.message.reply_text(text)
        return DURATION_INPUT


def _build_summary(rec_data, user_lang="en"):
    """Build confirmation summary text from recurring data."""
    rec_type = rec_data['type']
    parsed_time = rec_data['time']

    if user_lang == "sr-lat":
        title = "📋 *Pregled ponavljajućeg podsetnika*\n"
        msg_label = "💬 Poruka:"
        time_label = "🕐 Vreme:"
        rec_label = "🔁 Ponavljanje:"
        dur_label = "⏳ Trajanje:"
        forever_text = "Zauvek"
        daily_text = "Svaki dan"
        dur_suffix = "dana"
    elif user_lang == "pt-br":
        title = "📋 *Resumo do lembrete recorrente*\n"
        msg_label = "💬 Mensagem:"
        time_label = "🕐 Horário:"
        rec_label = "🔁 Recorrência:"
        dur_label = "⏳ Duração:"
        forever_text = "Para sempre"
        daily_text = "Todos os dias"
        dur_suffix = "dias"
    else:
        title = "📋 *Recurring Reminder Summary*\n"
        msg_label = "💬 Message:"
        time_label = "🕐 Time:"
        rec_label = "🔁 Recurrence:"
        dur_label = "⏳ Duration:"
        forever_text = "Forever"
        daily_text = "Every day"
        dur_suffix = "days"

    summary_lines = [
        title,
        f"{msg_label} {rec_data['message']}",
        f"{time_label} {parsed_time.strftime('%H:%M')}",
    ]

    if rec_type == "daily":
        summary_lines.append(f"{rec_label} {daily_text}")
    elif rec_type == "interval":
        days = rec_data['interval']
        if user_lang == "sr-lat":
            summary_lines.append(f"{rec_label} Svaka {days} dana")
        elif user_lang == "pt-br":
            summary_lines.append(f"{rec_label} A cada {days} dias")
        else:
            summary_lines.append(f"{rec_label} Every {days} days")
    elif rec_type == "weekly":
        days_str = ', '.join([d.capitalize() for d in rec_data['selected_days']])
        summary_lines.append(f"{rec_label} {days_str}")
    elif rec_type == "monthly":
        day = rec_data['day_of_month']
        if user_lang == "sr-lat":
            summary_lines.append(f"{rec_label} Svakog {day}. u mesecu")
        elif user_lang == "pt-br":
            summary_lines.append(f"{rec_label} Dia {day} do mês")
        else:
            summary_lines.append(f"{rec_label} Day {day} of month")

    duration_days = rec_data.get('duration_days')
    if duration_days:
        summary_lines.append(f"{dur_label} {duration_days} {dur_suffix}")
    else:
        summary_lines.append(f"{dur_label} {forever_text}")

    return '\n'.join(summary_lines)


async def _show_confirmation(query, context, user_lang="en"):
    """Show confirmation summary after duration choice."""
    rec_data = context.user_data['recurring']
    summary = _build_summary(rec_data, user_lang)

    if user_lang == "sr-lat":
        btn_confirm = "✅ Potvrdi"
        btn_cancel = "❌ Otkaži"
    elif user_lang == "pt-br":
        btn_confirm = "✅ Confirmar"
        btn_cancel = "❌ Cancelar"
    else:
        btn_confirm = "✅ Confirm"
        btn_cancel = "❌ Cancel"

    keyboard = [
        [
            InlineKeyboardButton(btn_confirm, callback_data="confirm_yes"),
            InlineKeyboardButton(btn_cancel, callback_data="confirm_no"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        summary,
        parse_mode="Markdown",
        reply_markup=reply_markup
    )

    return CONFIRM


async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle confirmation and create the recurring reminder.
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get('language', 'en') if user else 'en'

    if query.data == "confirm_no":
        if user_lang == "sr-lat":
            cancel_text = "❌ Otkazano. Koristi /recurring da počneš ponovo."
        elif user_lang == "pt-br":
            cancel_text = "❌ Cancelado. Use /recurring para começar novamente."
        else:
            cancel_text = "❌ Canceled. Use /recurring to start again."
        await query.edit_message_text(cancel_text)
        context.user_data.pop('recurring', None)
        return ConversationHandler.END

    # Create recurring reminder
    user_tz = user.get('timezone', 'Europe/Belgrade')

    rec_data = context.user_data['recurring']
    rec_type = rec_data['type']
    message = rec_data['message']
    reminder_time = rec_data['time']

    # Calculate first occurrence (using user's timezone)
    try:
        tz = pytz.timezone(user_tz)
    except pytz.UnknownTimeZoneError:
        tz = pytz.timezone("Europe/Belgrade")
    now = datetime.now(tz).replace(tzinfo=None)  # Naive datetime in user's timezone

    # For interval type, first occurrence is X days from now
    if rec_type == "interval":
        interval = rec_data['interval']
        # Check if today's time is still valid, otherwise add interval days
        base_time = datetime.combine(now.date(), reminder_time)
        if base_time <= now:
            # Today's time has passed, schedule for interval days from tomorrow
            scheduled_datetime = base_time + timedelta(days=interval)
        else:
            # Today's time is still valid, but for interval we start from interval days
            scheduled_datetime = base_time + timedelta(days=interval)
    else:
        # For other types: today or tomorrow based on time
        scheduled_datetime = datetime.combine(now.date(), reminder_time)
        # If time has passed today, schedule for tomorrow
        if scheduled_datetime <= now:
            scheduled_datetime += timedelta(days=1)

    # Calculate end date if duration specified
    duration_days = rec_data.get('duration_days')
    recurrence_end_date = None
    if duration_days:
        recurrence_end_date = scheduled_datetime + timedelta(days=duration_days)

    # Prepare recurrence parameters
    recurrence_interval = None
    recurrence_days = None
    recurrence_day_of_month = None

    if rec_type == "interval":
        recurrence_interval = rec_data['interval']
    elif rec_type == "weekly":
        recurrence_days = json.dumps(rec_data['selected_days'])
    elif rec_type == "monthly":
        recurrence_day_of_month = rec_data['day_of_month']

    # Create reminder
    reminder_id = create_reminder(
        user_id=user_id,
        message_text=message,
        scheduled_time=scheduled_datetime,
        is_recurring=True,
        recurrence_type=rec_type,
        recurrence_interval=recurrence_interval,
        recurrence_days=recurrence_days,
        recurrence_day_of_month=recurrence_day_of_month,
        recurrence_end_date=recurrence_end_date
    )

    if reminder_id:
        if user_lang == "sr-lat":
            next_time_str = scheduled_datetime.strftime('%d.%m.%Y u %H:%M')
            success_text = "✅ *Ponavljajući podsetnik kreiran!*"
            next_label = "Sledeći podsetnik:"
            end_label = "⏳ Do:"
        elif user_lang == "pt-br":
            next_time_str = scheduled_datetime.strftime('%d/%m/%Y às %H:%M')
            success_text = "✅ *Lembrete recorrente criado!*"
            next_label = "Próximo lembrete:"
            end_label = "⏳ Até:"
        else:
            next_time_str = scheduled_datetime.strftime('%d.%m.%Y at %H:%M')
            success_text = "✅ *Recurring reminder created!*"
            next_label = "Next reminder:"
            end_label = "⏳ Until:"
        end_info = ""
        if recurrence_end_date:
            if user_lang == "pt-br":
                end_info = f"\n{end_label} {recurrence_end_date.strftime('%d/%m/%Y')}"
            else:
                end_info = f"\n{end_label} {recurrence_end_date.strftime('%d.%m.%Y.')}"
        await query.edit_message_text(
            f"{success_text}\n\n"
            f"{next_label} {next_time_str}{end_info}",
            parse_mode="Markdown"
        )
    else:
        if user_lang == "sr-lat":
            error_text = "❌ Greška prilikom kreiranja podsetnika. Pokušaj ponovo."
        elif user_lang == "pt-br":
            error_text = "❌ Erro ao criar lembrete. Tente novamente."
        else:
            error_text = "❌ Error creating reminder. Try again."
        await query.edit_message_text(error_text)

    # Clean up
    context.user_data.pop('recurring', None)
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancel the conversation.
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get('language', 'en') if user else 'en'

    if user_lang == "sr-lat":
        text = "❌ Otkazano. Koristi /recurring da počneš ponovo."
    elif user_lang == "pt-br":
        text = "❌ Cancelado. Use /recurring para começar novamente."
    else:
        text = "❌ Canceled. Use /recurring to start again."
    await update.message.reply_text(text)
    context.user_data.pop('recurring', None)
    return ConversationHandler.END


def register_handlers(application):
    """
    Register recurring reminder handlers.
    """
    from telegram.ext import CommandHandler, MessageHandler, filters

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("recurring", recurring_command),
            MessageHandler(filters.Regex("^(🔁 Recurring|🔁 Ponavljajući|🔁 Recorrente)$"), recurring_command)
        ],
        states={
            MESSAGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            RECURRENCE_TYPE: [CallbackQueryHandler(handle_recurrence_type, pattern="^rec_type_")],
            INTERVAL_DAYS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_interval_days)],
            WEEKLY_DAYS: [CallbackQueryHandler(handle_weekday_selection, pattern="^weekday_")],
            MONTHLY_DAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_monthly_day)],
            TIME_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_input)],
            DURATION_CHOICE: [CallbackQueryHandler(handle_duration_choice, pattern="^duration_")],
            DURATION_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_duration_input)],
            CONFIRM: [CallbackQueryHandler(handle_confirmation, pattern="^confirm_")],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    application.add_handler(conv_handler)
