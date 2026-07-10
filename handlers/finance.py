"""
Finance handlers for Kosmos Telegram Bot.
Personal finance tracking: expenses, income, balance, and monthly summaries.
"""

import re
import logging
from datetime import datetime
from typing import Optional, Tuple, List, Dict, Any
from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
from database import (
    get_user, add_transaction, get_monthly_summary, get_balance,
    get_category_summary, get_recent_transactions
)

logger = logging.getLogger(__name__)

MONTH_NAMES = {
    "pt-br": ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
              "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"],
    "en": ["", "January", "February", "March", "April", "May", "June",
           "July", "August", "September", "October", "November", "December"],
    "sr-lat": ["", "Januar", "Februar", "Mart", "April", "Maj", "Jun",
               "Jul", "Avgust", "Septembar", "Oktobar", "Novembar", "Decembar"]
}


def format_currency(amount: float, user_lang: str) -> str:
    """
    Format a monetary amount according to the user's language locale.

    Args:
        amount: Numeric value to format
        user_lang: Language code (pt-br, en, sr-lat)

    Returns:
        Formatted currency string with symbol and thousand/decimal separators
    """
    if user_lang == "pt-br":
        # Brazilian: R$ 1.450,30 (dot for thousands, comma for decimals)
        integer_part = int(amount)
        decimal_part = int(round(abs(amount) - abs(integer_part), 2) * 100)
        formatted_int = f"{integer_part:,.0f}".replace(",", ".")
        return f"R$ {formatted_int},{decimal_part:02d}"
    elif user_lang == "sr-lat":
        # Serbian: 1.450,30 RSD (dot for thousands, comma for decimals)
        integer_part = int(amount)
        decimal_part = int(round(abs(amount) - abs(integer_part), 2) * 100)
        formatted_int = f"{integer_part:,.0f}".replace(",", ".")
        return f"{formatted_int},{decimal_part:02d} RSD"
    else:
        # English: $ 1,450.30 (comma for thousands, dot for decimals)
        integer_part = int(amount)
        decimal_part = int(round(abs(amount) - abs(integer_part), 2) * 100)
        formatted_int = f"{integer_part:,}"
        return f"$ {formatted_int}.{decimal_part:02d}"


def parse_finance_message(text: str) -> Optional[Tuple[float, str, str, str]]:
    """
    Parse a natural language message for finance intent.

    Recognizes patterns like:
      - "gastei 50 no mercado"       → expense, 50, mercado
      - "gastei 25.50 em gasolina"   → expense, 25.50, gasolina
      - "recebi 2000 de salário"     → income, 2000, salário
      - "recebi 500 freelance"       → income, 500, freelance
      - "paguei 100 de luz"          → expense, 100, luz
      - "ganhei 3000"                → income, 3000

    Returns:
        Tuple of (amount, type, category, description) or None if not a finance message.
        type is 'income' or 'expense'.
        category defaults to 'outros'.
    """
    if not text:
        return None

    text_lower = text.strip().lower()

    # Determine transaction type from keywords
    expense_pattern = r'^(gastei|paguei|gasto)\s'
    income_pattern = r'^(recebi|ganhei|receita)\s'

    transaction_type = None
    if re.search(expense_pattern, text_lower):
        transaction_type = 'expense'
    elif re.search(income_pattern, text_lower):
        transaction_type = 'income'
    else:
        return None

    # Extract amount: support both comma and dot as decimal separator
    amount_match = re.search(r'(\d+[.,]\d{1,2}|\d+)', text_lower)
    if not amount_match:
        return None

    amount_str = amount_match.group(1).replace(',', '.')
    try:
        amount = float(amount_str)
    except ValueError:
        return None

    # Get the rest of the text after removing the keyword and the amount
    rest = text_lower[amount_match.end():].strip()

    # Clean up known prepositions and connectors
    rest = re.sub(r'^(em|no|na|de|da|do|das|dos)\s+', '', rest).strip()

    # First word after the amount is the category
    category = 'outros'
    description = ''

    if rest:
        # Try to get the category (first word or multi-word after prepositions)
        parts = rest.split()
        if parts:
            category = parts[0]
            if len(parts) > 1:
                description = ' '.join(parts[1:])

    return (amount, transaction_type, category, description)


async def expense_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gasto command - register an expense."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    # Parse arguments: /gasto <valor> <categoria> [descrição]
    args = context.args
    if not args:
        if user_lang == "pt-br":
            await update.message.reply_text(
                "❌ Use: /gasto <valor> <categoria> [descrição]\n"
                "Exemplo: /gasto 50 mercado"
            )
        elif user_lang == "sr-lat":
            await update.message.reply_text(
                "❌ Koristi: /gasto <iznos> <kategorija> [opis]\n"
                "Primer: /gasto 50 pijaca"
            )
        else:
            await update.message.reply_text(
                "❌ Usage: /gasto <amount> <category> [description]\n"
                "Example: /gasto 50 groceries"
            )
        return

    # First argument is the amount
    amount_str = args[0].replace(',', '.')
    try:
        amount = float(amount_str)
    except ValueError:
        if user_lang == "pt-br":
            await update.message.reply_text("❌ Valor inválido. Use números (ex: 50 ou 25.50).")
        elif user_lang == "sr-lat":
            await update.message.reply_text("❌ Nevažeći iznos. Koristi brojeve (npr. 50 ili 25.50).")
        else:
            await update.message.reply_text("❌ Invalid amount. Use numbers (e.g., 50 or 25.50).")
        return

    if amount <= 0:
        if user_lang == "pt-br":
            await update.message.reply_text("❌ O valor deve ser positivo.")
        elif user_lang == "sr-lat":
            await update.message.reply_text("❌ Iznos mora biti pozitivan.")
        else:
            await update.message.reply_text("❌ Amount must be positive.")
        return

    # Second argument is the category (optional, defaults to 'outros')
    category = 'outros'
    description = ''

    if len(args) >= 2:
        category = args[1]
        if len(args) >= 3:
            description = ' '.join(args[2:])

    # Add transaction
    result = add_transaction(user_id, amount, 'expense', category, description)

    if result:
        current_balance = get_balance(user_id)
        balance_str = format_currency(current_balance, user_lang)
        amount_str_formatted = format_currency(amount, user_lang)

        if user_lang == "pt-br":
            msg = (
                f"💸 Gasto registrado: {amount_str_formatted} - {category.capitalize()}\n"
                f"Saldo atual: {balance_str}"
            )
        elif user_lang == "sr-lat":
            msg = (
                f"💸 Trošak zabeležen: {amount_str_formatted} - {category.capitalize()}\n"
                f"Trenutni saldo: {balance_str}"
            )
        else:
            msg = (
                f"💸 Expense recorded: {amount_str_formatted} - {category.capitalize()}\n"
                f"Current balance: {balance_str}"
            )

        await update.message.reply_text(msg)
        logger.info(f"User {user_id} registered expense: {amount} {category}")
    else:
        if user_lang == "pt-br":
            await update.message.reply_text("❌ Erro ao registrar gasto. Tente novamente.")
        elif user_lang == "sr-lat":
            await update.message.reply_text("❌ Greška pri beleženju troška. Pokušaj ponovo.")
        else:
            await update.message.reply_text("❌ Error recording expense. Try again.")


async def income_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /receita command - register an income."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    # Parse arguments: /receita <valor> <categoria> [descrição]
    args = context.args
    if not args:
        if user_lang == "pt-br":
            await update.message.reply_text(
                "❌ Use: /receita <valor> <categoria> [descrição]\n"
                "Exemplo: /receita 2000 salário"
            )
        elif user_lang == "sr-lat":
            await update.message.reply_text(
                "❌ Koristi: /receita <iznos> <kategorija> [opis]\n"
                "Primer: /receita 2000 plata"
            )
        else:
            await update.message.reply_text(
                "❌ Usage: /receita <amount> <category> [description]\n"
                "Example: /receita 2000 salary"
            )
        return

    # First argument is the amount
    amount_str = args[0].replace(',', '.')
    try:
        amount = float(amount_str)
    except ValueError:
        if user_lang == "pt-br":
            await update.message.reply_text("❌ Valor inválido. Use números (ex: 2000 ou 1500.50).")
        elif user_lang == "sr-lat":
            await update.message.reply_text("❌ Nevažeći iznos. Koristi brojeve (npr. 2000 ili 1500.50).")
        else:
            await update.message.reply_text("❌ Invalid amount. Use numbers (e.g., 2000 or 1500.50).")
        return

    if amount <= 0:
        if user_lang == "pt-br":
            await update.message.reply_text("❌ O valor deve ser positivo.")
        elif user_lang == "sr-lat":
            await update.message.reply_text("❌ Iznos mora biti pozitivan.")
        else:
            await update.message.reply_text("❌ Amount must be positive.")
        return

    # Second argument is the category (optional, defaults to 'outros')
    category = 'outros'
    description = ''

    if len(args) >= 2:
        category = args[1]
        if len(args) >= 3:
            description = ' '.join(args[2:])

    # Add transaction
    result = add_transaction(user_id, amount, 'income', category, description)

    if result:
        current_balance = get_balance(user_id)
        balance_str = format_currency(current_balance, user_lang)
        amount_str_formatted = format_currency(amount, user_lang)

        if user_lang == "pt-br":
            msg = (
                f"💰 Receita registrada: {amount_str_formatted} - {category.capitalize()}\n"
                f"Saldo atual: {balance_str}"
            )
        elif user_lang == "sr-lat":
            msg = (
                f"💰 Prihod zabeležen: {amount_str_formatted} - {category.capitalize()}\n"
                f"Trenutni saldo: {balance_str}"
            )
        else:
            msg = (
                f"💰 Income recorded: {amount_str_formatted} - {category.capitalize()}\n"
                f"Current balance: {balance_str}"
            )

        await update.message.reply_text(msg)
        logger.info(f"User {user_id} registered income: {amount} {category}")
    else:
        if user_lang == "pt-br":
            await update.message.reply_text("❌ Erro ao registrar receita. Tente novamente.")
        elif user_lang == "sr-lat":
            await update.message.reply_text("❌ Greška pri beleženju prihoda. Pokušaj ponovo.")
        else:
            await update.message.reply_text("❌ Error recording income. Try again.")


async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gastos command - show monthly expense summary."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    now = datetime.now()
    month = now.month
    year = now.year

    summary = get_monthly_summary(user_id, month, year)
    categories = get_category_summary(user_id, month, year)

    month_name = MONTH_NAMES.get(user_lang, MONTH_NAMES["en"])[month]
    total_income_str = format_currency(summary['total_income'], user_lang)
    total_expense_str = format_currency(summary['total_expense'], user_lang)
    balance_str = format_currency(summary['balance'], user_lang)

    if user_lang == "pt-br":
        message = f"📊 *Resumo de {month_name} {year}*\n\n"
        message += f"💰 Receitas: {total_income_str}\n"
        message += f"💸 Despesas: {total_expense_str}\n"
        message += f"✅ Saldo: {balance_str}\n"

        if categories:
            message += "\n*Gastos por categoria:*\n"
            for cat in categories:
                cat_total = format_currency(cat['total'], user_lang)
                message += f"• {cat['category'].capitalize()}: {cat_total} ({cat['count']})\n"
    elif user_lang == "sr-lat":
        message = f"📊 *Rezime za {month_name} {year}*\n\n"
        message += f"💰 Prihodi: {total_income_str}\n"
        message += f"💸 Troškovi: {total_expense_str}\n"
        message += f"✅ Saldo: {balance_str}\n"

        if categories:
            message += "\n*Troškovi po kategoriji:*\n"
            for cat in categories:
                cat_total = format_currency(cat['total'], user_lang)
                message += f"• {cat['category'].capitalize()}: {cat_total} ({cat['count']})\n"
    else:
        message = f"📊 *Summary for {month_name} {year}*\n\n"
        message += f"💰 Income: {total_income_str}\n"
        message += f"💸 Expenses: {total_expense_str}\n"
        message += f"✅ Balance: {balance_str}\n"

        if categories:
            message += "\n*Expenses by category:*\n"
            for cat in categories:
                cat_total = format_currency(cat['total'], user_lang)
                message += f"• {cat['category'].capitalize()}: {cat_total} ({cat['count']})\n"

    if not summary['total_expense'] and not summary['total_income']:
        if user_lang == "pt-br":
            message += "\n_Nenhuma transação registrada neste mês._"
        elif user_lang == "sr-lat":
            message += "\n_Nema zabeleženih transakcija ovog meseca._"
        else:
            message += "\n_No transactions recorded this month._"

    await update.message.reply_text(message, parse_mode="Markdown")
    logger.info(f"User {user_id} requested monthly summary for {month}/{year}")


async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /saldo command - show current balance."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    balance = get_balance(user_id)
    balance_str = format_currency(balance, user_lang)

    if user_lang == "pt-br":
        msg = f"💰 *Saldo atual:* {balance_str}"
    elif user_lang == "sr-lat":
        msg = f"💰 *Trenutni saldo:* {balance_str}"
    else:
        msg = f"💰 *Current balance:* {balance_str}"

    await update.message.reply_text(msg, parse_mode="Markdown")
    logger.info(f"User {user_id} requested balance: {balance}")


async def statement_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /extrato command - show recent transactions."""
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    transactions = get_recent_transactions(user_id, limit=10)

    if not transactions:
        if user_lang == "pt-br":
            await update.message.reply_text("📋 Nenhuma transação encontrada.")
        elif user_lang == "sr-lat":
            await update.message.reply_text("📋 Nema pronađenih transakcija.")
        else:
            await update.message.reply_text("📋 No transactions found.")
        return

    if user_lang == "pt-br":
        message = "📋 *Extrato recente:*\n\n"
    elif user_lang == "sr-lat":
        message = "📋 *Skorašnje transakcije:*\n\n"
    else:
        message = "📋 *Recent statement:*\n\n"

    for t in transactions:
        amount_val = t['amount']
        amount_str = format_currency(amount_val, user_lang)
        txn_type = t['type']
        category = t['category'].capitalize()
        description = t.get('description', '')

        # Parse date for display (DD/MM format)
        date_str = t.get('transaction_date', '')
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            day_month = dt.strftime("%d/%m")
        except (ValueError, TypeError):
            day_month = date_str

        if txn_type == 'income':
            prefix = "💰"
        else:
            prefix = "💸"

        line = f"{prefix} {amount_str} - {category} ({day_month})"
        if description:
            line += f"\n   _{description}_"
        message += line + "\n"

    await update.message.reply_text(message, parse_mode="Markdown")
    logger.info(f"User {user_id} requested statement")


def register_handlers(application):
    """Register finance command handlers."""
    application.add_handler(CommandHandler("gasto", expense_command))
    application.add_handler(CommandHandler("receita", income_command))
    application.add_handler(CommandHandler("gastos", summary_command))
    application.add_handler(CommandHandler("saldo", balance_command))
    application.add_handler(CommandHandler("extrato", statement_command))
