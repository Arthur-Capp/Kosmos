"""
Shopping list handler for Kosmos Telegram Bot.
Manages shopping lists, items, and purchases via Telegram commands.
"""

import re
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from database import (
    get_user,
    create_shopping_list,
    add_shopping_item,
    get_active_shopping_lists,
    get_shopping_items,
    mark_item_purchased,
    delete_shopping_list,
    get_shopping_list_by_id,
)

logger = logging.getLogger(__name__)


def _parse_item_with_quantity(item_str: str) -> tuple:
    """
    Parse an item string like 'leite 2x' or 'pao 3' or just 'leite'.

    Returns:
        Tuple of (name, quantity_string)
    """
    item_str = item_str.strip()
    match = re.match(r'^(.+?)\s+(\d+)x?\s*$', item_str)
    if match:
        name = match.group(1).strip()
        quantity = match.group(2)
        return name, quantity
    return item_str, '1'


def _get_text(key: str, lang: str, **kwargs) -> str:
    """
    Get a hardcoded multi-language string.
    Keys follow the same pattern used across the project.

    Args:
        key: Message identifier
        lang: Language code (pt-br, sr-lat, en)
        **kwargs: Format arguments
    """
    strings = {
        # No lists
        "no_lists": {
            "pt-br": "Você não tem listas ativas. Use /lista <nome> para criar uma.",
            "sr-lat": "Nemate aktivnih lista. Koristite /lista <ime> da napravite novu.",
            "en": "You have no active lists. Use /lista <name> to create one.",
        },
        # Lists header
        "lists_header": {
            "pt-br": "📋 *Suas listas de compras:*\n\n",
            "sr-lat": "📋 *Vaše liste za kupovinu:*\n\n",
            "en": "📋 *Your shopping lists:*\n\n",
        },
        # List button text with count
        "list_btn": {
            "pt-br": "🛒 {name} ({count} itens)",
            "sr-lat": "🛒 {name} ({count} stavki)",
            "en": "🛒 {name} ({count} items)",
        },
        # New list button
        "new_list_btn": {
            "pt-br": "➕ Nova lista",
            "sr-lat": "➕ Nova lista",
            "en": "➕ New list",
        },
        # Usage for /lista
        "lista_usage": {
            "pt-br": "Use: /lista <nome> ou /lista <nome> <categoria>",
            "sr-lat": "Koristi: /lista <ime> ili /lista <ime> <kategorija>",
            "en": "Usage: /lista <name> or /lista <name> <category>",
        },
        # List created
        "lista_created": {
            "pt-br": "✅ Lista '{name}' criada! Adicione itens com /add ou clique em 'Ver itens'.",
            "sr-lat": "✅ Lista '{name}' napravljena! Dodajte stavke sa /add ili kliknite 'Pregledaj stavke'.",
            "en": "✅ List '{name}' created! Add items with /add or click 'View items'.",
        },
        # Error creating list
        "lista_error": {
            "pt-br": "❌ Erro ao criar lista.",
            "sr-lat": "❌ Greška pri kreiranju liste.",
            "en": "❌ Error creating list.",
        },
        # Usage for /add
        "add_usage": {
            "pt-br": "Use: /add <item1>, <item2>, ...",
            "sr-lat": "Koristi: /add <stavka1>, <stavka2>, ...",
            "en": "Usage: /add <item1>, <item2>, ...",
        },
        # No active lists for add
        "add_no_list": {
            "pt-br": "Você não tem listas ativas. Crie uma com /lista <nome>.",
            "sr-lat": "Nemate aktivnih lista. Napravite jednu sa /lista <ime>.",
            "en": "You have no active lists. Create one with /lista <name>.",
        },
        # Items added
        "items_added": {
            "pt-br": "✅ {count} itens adicionados à lista '{name}'.",
            "sr-lat": "✅ {count} stavki dodato u listu '{name}'.",
            "en": "✅ {count} items added to list '{name}'.",
        },
        # Items added with errors
        "items_added_errors": {
            "pt-br": "✅ {count} itens adicionados à lista '{name}'. ⚠️ {errors} falharam.",
            "sr-lat": "✅ {count} stavki dodato u listu '{name}'. ⚠️ {errors} neuspešno.",
            "en": "✅ {count} items added to list '{name}'. ⚠️ {errors} failed.",
        },
        # No items added
        "add_no_items": {
            "pt-br": "❌ Nenhum item foi adicionado.",
            "sr-lat": "❌ Nijedna stavka nije dodata.",
            "en": "❌ No items were added.",
        },
        # List not found
        "list_not_found": {
            "pt-br": "Lista não encontrada.",
            "sr-lat": "Lista nije pronađena.",
            "en": "List not found.",
        },
        # No items in list
        "no_items": {
            "pt-br": "\n\n📭 Nenhum item ainda.",
            "sr-lat": "\n\n📭 Još nema stavki.",
            "en": "\n\n📭 No items yet.",
        },
        # Estimated total
        "estimated_total": {
            "pt-br": "\nTotal estimado: R$ {total:.2f}",
            "sr-lat": "\nProcenjeni ukupno: R$ {total:.2f}",
            "en": "\nEstimated total: R$ {total:.2f}",
        },
        # Purchased count
        "purchased_count": {
            "pt-br": "\n{purchased}/{total} comprados ✅",
            "sr-lat": "\n{purchased}/{total} kupljeno ✅",
            "en": "\n{purchased}/{total} purchased ✅",
        },
        # Delete list button
        "delete_list_btn": {
            "pt-br": "🗑️ Excluir lista",
            "sr-lat": "🗑️ Obriši listu",
            "en": "🗑️ Delete list",
        },
        # Back button
        "back_btn": {
            "pt-br": "← Voltar",
            "sr-lat": "← Nazad",
            "en": "← Back",
        },
        # Confirm delete
        "confirm_delete": {
            "pt-br": "Excluir lista '{name}' e todos os itens?",
            "sr-lat": "Obrisati listu '{name}' i sve stavke?",
            "en": "Delete list '{name}' and all items?",
        },
        # Confirm delete yes
        "confirm_yes": {
            "pt-br": "Sim, excluir",
            "sr-lat": "Da, obriši",
            "en": "Yes, delete",
        },
        # Confirm delete no
        "confirm_no": {
            "pt-br": "Não, cancelar",
            "sr-lat": "Ne, otkaži",
            "en": "No, cancel",
        },
        # List deleted
        "list_deleted": {
            "pt-br": "Lista excluída ✓",
            "sr-lat": "Lista obrisana ✓",
            "en": "List deleted ✓",
        },
        # Delete cancelled
        "delete_cancelled": {
            "pt-br": "Exclusão cancelada.",
            "sr-lat": "Brisanje otkazano.",
            "en": "Deletion cancelled.",
        },
        # New list prompt (ForceReply)
        "new_list_prompt": {
            "pt-br": "Digite o nome da nova lista:",
            "sr-lat": "Unesite ime nove liste:",
            "en": "Enter the name of the new list:",
        },
        # New list from reply created
        "reply_list_created": {
            "pt-br": "✅ Lista '{name}' criada! Use /add para adicionar itens.",
            "sr-lat": "✅ Lista '{name}' napravljena! Koristite /add za dodavanje stavki.",
            "en": "✅ List '{name}' created! Use /add to add items.",
        },
        # Prompt expired
        "prompt_expired": {
            "pt-br": "⏳ Tempo expirado. Use /lista <nome> para criar uma lista ou clique em 'Nova lista' novamente.",
            "sr-lat": "⏳ Isteklo je vreme. Koristite /lista <ime> da napravite listu ili ponovo kliknite 'Nova lista'.",
            "en": "⏳ Prompt expired. Use /lista <name> to create a list or click 'New list' again.",
        },
    }

    text = strings.get(key, {}).get(lang, strings.get(key, {}).get("en", key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except KeyError:
            pass
    return text


async def listas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /listas command.
    Shows all active shopping lists for the user with inline buttons.
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    lists = get_active_shopping_lists(user_id)

    if not lists:
        await update.message.reply_text(
            _get_text("no_lists", user_lang)
        )
        return

    text = _get_text("lists_header", user_lang)
    keyboard = []

    for lst in lists:
        item_count = lst.get("item_count", 0) or 0
        btn_text = _get_text("list_btn", user_lang, name=lst["name"], count=item_count)
        keyboard.append([
            InlineKeyboardButton(btn_text, callback_data=f"shop_view_{lst['id']}")
        ])

    # New list button at the bottom
    keyboard.append([
        InlineKeyboardButton(_get_text("new_list_btn", user_lang), callback_data="shop_new")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)

    logger.info(f"User {user_id} viewed shopping lists ({len(lists)} lists)")


async def lista_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /lista command.
    Creates a new shopping list with optional category.
    Usage: /lista <nome> [categoria]
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    args = context.args
    if not args:
        await update.message.reply_text(_get_text("lista_usage", user_lang))
        return

    name = args[0]
    category = args[1] if len(args) > 1 else "geral"

    list_id = create_shopping_list(user_id, name, category)
    if list_id:
        await update.message.reply_text(
            _get_text("lista_created", user_lang, name=name)
        )
        logger.info(f"User {user_id} created shopping list '{name}' (category={category}), ID={list_id}")
    else:
        await update.message.reply_text(_get_text("lista_error", user_lang))


async def add_items_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle /add command.
    Adds items to the most recent active shopping list.
    Usage: /add <item1>, <item2>, ...   or   /add leite 2x, pao 3x
    """
    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    if not context.args:
        await update.message.reply_text(_get_text("add_usage", user_lang))
        return

    # Rejoin args into a single string, then split by commas
    full_text = " ".join(context.args)
    raw_items = [item.strip() for item in full_text.split(",")]
    raw_items = [item for item in raw_items if item]

    if not raw_items:
        await update.message.reply_text(_get_text("add_no_items", user_lang))
        return

    # Get most recent active list
    lists = get_active_shopping_lists(user_id)
    if not lists:
        await update.message.reply_text(_get_text("add_no_list", user_lang))
        return

    active_list = lists[0]  # Most recent (ordered by created_at DESC)
    list_name = active_list.get("name", "?")

    # Parse and add each item
    added = 0
    errors = 0
    for raw_item in raw_items:
        name, quantity = _parse_item_with_quantity(raw_item)
        if name:
            success = add_shopping_item(active_list["id"], name, quantity)
            if success:
                added += 1
            else:
                errors += 1

    if added > 0:
        if errors > 0:
            msg = _get_text("items_added_errors", user_lang, count=added, name=list_name, errors=errors)
        else:
            msg = _get_text("items_added", user_lang, count=added, name=list_name)
        await update.message.reply_text(msg)
        logger.info(f"User {user_id} added {added} items to shopping list {active_list['id']}")
    else:
        await update.message.reply_text(_get_text("add_no_items", user_lang))


async def view_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle shop_view_{list_id} callback.
    Shows all items in a shopping list with toggle and action buttons.
    """
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    try:
        list_id = int(callback_data.replace("shop_view_", ""))
    except (ValueError, IndexError):
        logger.error(f"Invalid shop_view callback data: {callback_data}")
        return

    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    shopping_list = get_shopping_list_by_id(list_id)
    if not shopping_list:
        await query.edit_message_text(_get_text("list_not_found", user_lang))
        return

    items = get_shopping_items(list_id)
    list_name = shopping_list.get("name", "?")
    category = shopping_list.get("category", "geral")

    # Store current list_id in user_data for the toggle callback
    context.user_data["current_list_id"] = list_id

    # Build message
    message = f"🛒 *{list_name}*"
    if category != "geral":
        message += f" ({category})"

    if not items:
        message += _get_text("no_items", user_lang)
    else:
        message += "\n\n"
        total_price = 0.0
        for item in items:
            name = item.get("name", "?")
            quantity = item.get("quantity", "1")
            price = item.get("estimated_price", 0) or 0
            is_purchased = item.get("is_purchased", 0)

            checkbox = "✅" if is_purchased else "☐"

            if price > 0:
                item_text = f"{checkbox} {name} ({quantity}x) - R$ {price:.2f}\n"
                total_price += price
            else:
                item_text = f"{checkbox} {name} ({quantity}x)\n"

            message += item_text

        if total_price > 0:
            message += _get_text("estimated_total", user_lang, total=total_price)

        # Purchased count summary
        purchased_count = sum(1 for item in items if item.get("is_purchased", 0))
        if purchased_count > 0:
            message += _get_text("purchased_count", user_lang, purchased=purchased_count, total=len(items))

    # Build keyboard: one row per item (toggle button), then action buttons
    keyboard = []
    for item in items:
        item_id = item["id"]
        name = item.get("name", "?")
        quantity = item.get("quantity", "1")
        is_purchased = item.get("is_purchased", 0)

        btn_text = f"✅ {name} ({quantity}x)" if is_purchased else f"☐ {name} ({quantity}x)"
        keyboard.append([
            InlineKeyboardButton(btn_text, callback_data=f"shop_item_{item_id}")
        ])

    # Bottom action buttons
    keyboard.append([
        InlineKeyboardButton(
            _get_text("delete_list_btn", user_lang),
            callback_data=f"shop_delete_{list_id}"
        )
    ])
    keyboard.append([
        InlineKeyboardButton(
            _get_text("back_btn", user_lang),
            callback_data="shop_back"
        )
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)


async def toggle_item_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle shop_item_{item_id} callback.
    Toggles the purchased status of an item and refreshes the list view.
    """
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    try:
        item_id = int(callback_data.replace("shop_item_", ""))
    except (ValueError, IndexError):
        logger.error(f"Invalid shop_item callback data: {callback_data}")
        return

    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    # Get the current list_id from user_data
    list_id = context.user_data.get("current_list_id")
    if not list_id:
        # Fallback: try to find the list by scanning all user lists
        lists = get_active_shopping_lists(user_id)
        for lst in lists:
            items = get_shopping_items(lst["id"])
            item_ids = {item["id"] for item in items}
            if item_id in item_ids:
                list_id = lst["id"]
                context.user_data["current_list_id"] = list_id
                break

    if not list_id:
        logger.error(f"Could not find list for item {item_id}")
        return

    # Find current item status by fetching items for this list
    items = get_shopping_items(list_id)
    current_item = None
    for item in items:
        if item["id"] == item_id:
            current_item = item
            break

    if not current_item:
        logger.error(f"Item {item_id} not found in list {list_id}")
        return

    # Toggle purchased status
    new_status = not current_item.get("is_purchased", 0)
    success = mark_item_purchased(item_id, new_status)

    if not success:
        logger.error(f"Failed to toggle item {item_id}")
        return

    logger.info(f"User {user_id} toggled item {item_id} to purchased={new_status}")

    # Re-fetch list data for refreshed view
    shopping_list = get_shopping_list_by_id(list_id)
    if not shopping_list:
        await query.edit_message_text(_get_text("list_not_found", user_lang))
        return

    items = get_shopping_items(list_id)
    list_name = shopping_list.get("name", "?")
    category = shopping_list.get("category", "geral")

    # Rebuild message (same as view_list_callback)
    message = f"🛒 *{list_name}*"
    if category != "geral":
        message += f" ({category})"

    if not items:
        message += _get_text("no_items", user_lang)
    else:
        message += "\n\n"
        total_price = 0.0
        for item in items:
            name = item.get("name", "?")
            quantity = item.get("quantity", "1")
            price = item.get("estimated_price", 0) or 0
            is_purchased = item.get("is_purchased", 0)

            checkbox = "✅" if is_purchased else "☐"
            if price > 0:
                item_text = f"{checkbox} {name} ({quantity}x) - R$ {price:.2f}\n"
                total_price += price
            else:
                item_text = f"{checkbox} {name} ({quantity}x)\n"
            message += item_text

        if total_price > 0:
            message += _get_text("estimated_total", user_lang, total=total_price)

        purchased_count = sum(1 for item in items if item.get("is_purchased", 0))
        if purchased_count > 0:
            message += _get_text("purchased_count", user_lang, purchased=purchased_count, total=len(items))

    # Rebuild keyboard
    keyboard = []
    for item in items:
        item_id_b = item["id"]
        name = item.get("name", "?")
        quantity = item.get("quantity", "1")
        is_purchased = item.get("is_purchased", 0)
        btn_text = f"✅ {name} ({quantity}x)" if is_purchased else f"☐ {name} ({quantity}x)"
        keyboard.append([
            InlineKeyboardButton(btn_text, callback_data=f"shop_item_{item_id_b}")
        ])

    keyboard.append([
        InlineKeyboardButton(
            _get_text("delete_list_btn", user_lang),
            callback_data=f"shop_delete_{list_id}"
        )
    ])
    keyboard.append([
        InlineKeyboardButton(
            _get_text("back_btn", user_lang),
            callback_data="shop_back"
        )
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(message, parse_mode="Markdown", reply_markup=reply_markup)


async def delete_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle shop_delete_{list_id} callback.
    Shows confirmation dialog before deleting the list.
    """
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    try:
        list_id = int(callback_data.replace("shop_delete_", ""))
    except (ValueError, IndexError):
        logger.error(f"Invalid shop_delete callback data: {callback_data}")
        return

    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    shopping_list = get_shopping_list_by_id(list_id)
    if not shopping_list:
        await query.edit_message_text(_get_text("list_not_found", user_lang))
        return

    list_name = shopping_list.get("name", "?")
    confirm_text = _get_text("confirm_delete", user_lang, name=list_name)

    keyboard = [
        [
            InlineKeyboardButton(
                _get_text("confirm_yes", user_lang),
                callback_data=f"shop_confirm_{list_id}"
            ),
            InlineKeyboardButton(
                _get_text("confirm_no", user_lang),
                callback_data=f"shop_cancel_{list_id}"
            ),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(confirm_text, reply_markup=reply_markup)


async def confirm_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle shop_confirm_{list_id} callback.
    Confirms deletion and removes the shopping list.
    """
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    try:
        list_id = int(callback_data.replace("shop_confirm_", ""))
    except (ValueError, IndexError):
        logger.error(f"Invalid shop_confirm callback data: {callback_data}")
        return

    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    # Delete the list
    success = delete_shopping_list(list_id)

    if success:
        # Clear cached list_id if it matches
        if context.user_data.get("current_list_id") == list_id:
            context.user_data.pop("current_list_id", None)

        await query.edit_message_text(
            _get_text("list_deleted", user_lang)
        )
        logger.info(f"User {user_id} deleted shopping list {list_id}")
    else:
        await query.edit_message_text(_get_text("lista_error", user_lang))


async def cancel_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle shop_cancel_{list_id} callback.
    Cancels deletion and returns to the list view.
    """
    query = update.callback_query
    await query.answer()

    callback_data = query.data
    try:
        list_id = int(callback_data.replace("shop_cancel_", ""))
    except (ValueError, IndexError):
        logger.error(f"Invalid shop_cancel callback data: {callback_data}")
        return

    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    await query.edit_message_text(
        _get_text("delete_cancelled", user_lang)
    )

    # Redirect back to list view
    # Rebuild the view by calling the same logic as view_list_callback
    shopping_list = get_shopping_list_by_id(list_id)
    if not shopping_list:
        # List might have been deleted; fall back to /listas
        lists = get_active_shopping_lists(user_id)
        if not lists:
            await query.message.reply_text(_get_text("no_lists", user_lang))
            return

        text = _get_text("lists_header", user_lang)
        keyboard = []
        for lst in lists:
            item_count = lst.get("item_count", 0) or 0
            btn_text = _get_text("list_btn", user_lang, name=lst["name"], count=item_count)
            keyboard.append([
                InlineKeyboardButton(btn_text, callback_data=f"shop_view_{lst['id']}")
            ])
        keyboard.append([
            InlineKeyboardButton(_get_text("new_list_btn", user_lang), callback_data="shop_new")
        ])
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=reply_markup)
        return

    # Rebuild the view for the list
    context.user_data["current_list_id"] = list_id

    items = get_shopping_items(list_id)
    list_name = shopping_list.get("name", "?")
    category = shopping_list.get("category", "geral")

    message = f"🛒 *{list_name}*"
    if category != "geral":
        message += f" ({category})"

    if not items:
        message += _get_text("no_items", user_lang)
    else:
        message += "\n\n"
        total_price = 0.0
        for item in items:
            name = item.get("name", "?")
            quantity = item.get("quantity", "1")
            price = item.get("estimated_price", 0) or 0
            is_purchased = item.get("is_purchased", 0)
            checkbox = "✅" if is_purchased else "☐"
            if price > 0:
                item_text = f"{checkbox} {name} ({quantity}x) - R$ {price:.2f}\n"
                total_price += price
            else:
                item_text = f"{checkbox} {name} ({quantity}x)\n"
            message += item_text

        if total_price > 0:
            message += _get_text("estimated_total", user_lang, total=total_price)

        purchased_count = sum(1 for item in items if item.get("is_purchased", 0))
        if purchased_count > 0:
            message += _get_text("purchased_count", user_lang, purchased=purchased_count, total=len(items))

    keyboard = []
    for item in items:
        item_id_b = item["id"]
        name = item.get("name", "?")
        quantity = item.get("quantity", "1")
        is_purchased = item.get("is_purchased", 0)
        btn_text = f"✅ {name} ({quantity}x)" if is_purchased else f"☐ {name} ({quantity}x)"
        keyboard.append([
            InlineKeyboardButton(btn_text, callback_data=f"shop_item_{item_id_b}")
        ])

    keyboard.append([
        InlineKeyboardButton(
            _get_text("delete_list_btn", user_lang),
            callback_data=f"shop_delete_{list_id}"
        )
    ])
    keyboard.append([
        InlineKeyboardButton(
            _get_text("back_btn", user_lang),
            callback_data="shop_back"
        )
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text(message, parse_mode="Markdown", reply_markup=reply_markup)


async def new_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle shop_new callback.
    Prompts the user to enter a name for the new list via ForceReply.
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    # Send prompt with ForceReply
    prompt_msg = await query.message.reply_text(
        _get_text("new_list_prompt", user_lang),
        reply_markup=ForceReply(selective=True)
    )

    # Store state so the message handler knows to process the reply
    context.user_data["awaiting_new_list_name"] = True
    context.user_data["new_list_prompt_msg_id"] = prompt_msg.message_id

    logger.info(f"User {user_id} prompted for new list name")


async def handle_new_list_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle user's reply to the new list name prompt.
    Creates a new shopping list with the provided name.
    """
    # Only process if we're expecting a list name
    if not context.user_data.get("awaiting_new_list_name"):
        return

    # Only process if this is a reply to a message
    if not update.message or not update.message.reply_to_message:
        return

    # Verify this reply is to our prompt
    prompt_msg_id = context.user_data.get("new_list_prompt_msg_id")
    if update.message.reply_to_message.message_id != prompt_msg_id:
        return

    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    # Clean up state immediately (before any async operation)
    context.user_data.pop("awaiting_new_list_name", None)
    context.user_data.pop("new_list_prompt_msg_id", None)

    list_name = update.message.text.strip()
    if not list_name:
        await update.message.reply_text(
            _get_text("prompt_expired", user_lang)
        )
        return

    # Create the list
    list_id = create_shopping_list(user_id, list_name)
    if list_id:
        reply_text = _get_text("reply_list_created", user_lang, name=list_name)
        await update.message.reply_text(reply_text)
        logger.info(f"User {user_id} created shopping list '{list_name}' via reply, ID={list_id}")
    else:
        await update.message.reply_text(_get_text("lista_error", user_lang))


async def back_to_lists_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle shop_back callback.
    Returns to the list of all shopping lists.
    """
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    user = get_user(user_id)
    user_lang = user.get("language", "en") if user else "en"

    # Clear current list context
    context.user_data.pop("current_list_id", None)

    lists = get_active_shopping_lists(user_id)

    if not lists:
        await query.edit_message_text(_get_text("no_lists", user_lang))
        return

    text = _get_text("lists_header", user_lang)
    keyboard = []

    for lst in lists:
        item_count = lst.get("item_count", 0) or 0
        btn_text = _get_text("list_btn", user_lang, name=lst["name"], count=item_count)
        keyboard.append([
            InlineKeyboardButton(btn_text, callback_data=f"shop_view_{lst['id']}")
        ])

    keyboard.append([
        InlineKeyboardButton(_get_text("new_list_btn", user_lang), callback_data="shop_new")
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=reply_markup)


def register_handlers(application):
    """
    Register shopping list command and callback handlers.
    """
    # Command handlers
    application.add_handler(CommandHandler("listas", listas_command))
    application.add_handler(CommandHandler("lista", lista_command))
    application.add_handler(CommandHandler("add", add_items_command))

    # Callback handlers
    application.add_handler(CallbackQueryHandler(view_list_callback, pattern=r'^shop_view_'))
    application.add_handler(CallbackQueryHandler(toggle_item_callback, pattern=r'^shop_item_'))
    application.add_handler(CallbackQueryHandler(delete_list_callback, pattern=r'^shop_delete_'))
    application.add_handler(CallbackQueryHandler(new_list_callback, pattern=r'^shop_new$'))
    application.add_handler(CallbackQueryHandler(confirm_delete_callback, pattern=r'^shop_confirm_'))
    application.add_handler(CallbackQueryHandler(cancel_delete_callback, pattern=r'^shop_cancel_'))
    application.add_handler(CallbackQueryHandler(back_to_lists_callback, pattern=r'^shop_back$'))

    # Message handler for ForceReply when creating a new list
    # Only triggers on text replies that are not commands
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND & filters.REPLY, handle_new_list_reply)
    )
