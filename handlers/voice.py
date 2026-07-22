"""
Voice message handler for Kosmos Telegram Bot.
Transcribes voice messages and creates reminders from the transcribed text.
"""

import logging
import re
from io import BytesIO
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from telegram.error import NetworkError, TimedOut

from database import get_user, create_reminder, add_transaction, create_shopping_list, get_active_shopping_lists, add_shopping_item
from parsers.time_parser import parse_reminder, format_reminder_confirmation
from i18n import get_text
from message_queue import queue_message

logger = logging.getLogger(__name__)

# Map bot languages to Google SpeechRecognition language codes
STT_LANGUAGE_MAP = {
    "en": "en-US",
    "pt-br": "pt-BR",
    "sr-lat": "sr-RS",
}


def detect_shopping_intent(text: str, user_lang: str):
    """
    Detect shopping list intent from transcribed text.

    Args:
        text: Transcribed text from voice message
        user_lang: User's language code (pt-br, en, sr-lat)

    Returns:
        Tuple of (action, data) where action is 'create_list' or 'add_items'
        and data is the list name (str) or items list (list[str]).
        Returns None if no shopping intent detected.
    """
    if not text:
        return None

    text_lower = text.strip().lower()
    user_lang = user_lang if user_lang in ("pt-br", "en", "sr-lat") else "en"

    # Keywords per language
    create_keywords = {
        "pt-br": ["cria lista", "nova lista", "criar lista", "crie uma lista"],
        "en":     ["create list", "new list", "create a list", "make a list"],
        "sr-lat": ["napravi listu", "nova lista", "kreiraj listu"],
    }

    add_keywords = {
        "pt-br": ["adiciona na lista", "adiciona na", "coloca na lista", "adiciona "],
        "en":     ["add to list", "add to shopping", "add "],
        "sr-lat": ["dodaj na listu", "dodaj u"],
    }

    # --- check create list intent ---
    for kw in create_keywords[user_lang]:
        if kw in text_lower:
            idx = text_lower.index(kw) + len(kw)
            name = text[idx:].strip()
            # clean trailing prepositions / qualifiers
            name = re.sub(
                r'(?i)^(de compras|do mercado|da feira|shopping|for)\s*',
                '', name
            ).strip()
            # clean leading articles
            name = re.sub(r'(?i)^(a|o|as|os|the)\s+', '', name).strip()
            if not name:
                # default name per language
                defaults = {"pt-br": "Compras", "en": "Shopping", "sr-lat": "Kupovina"}
                name = defaults.get(user_lang, "Shopping")
            return ('create_list', name)

    # --- check add items intent ---
    for kw in add_keywords[user_lang]:
        if kw in text_lower:
            idx = text_lower.index(kw) + len(kw)
            rest = text[idx:].strip()

            # trim trailing list reference
            if user_lang == "pt-br":
                rest = re.sub(
                    r'(?i)\s+(na|nesta|nessa)\s+lista(\s+de\s+compras)?\s*$',
                    '', rest
                ).strip()
                # when keyword ended with "na" we may have leading "lista"
                rest = re.sub(r'(?i)^lista\s+', '', rest).strip()
            elif user_lang == "en":
                rest = re.sub(
                    r'(?i)\s+(to|in|on)\s+(the\s+)?(list|shopping)(\s+list)?\s*$',
                    '', rest
                ).strip()
            elif user_lang == "sr-lat":
                rest = re.sub(
                    r'(?i)\s+(na|u)\s+listu\s*$',
                    '', rest
                ).strip()

            if rest:
                items = re.split(r'[,;]|\s+e\s+|\s+and\s+', rest)
                items = [it.strip() for it in items if it.strip()]
                if items:
                    return ('add_items', items)

    return None


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Handle voice messages by transcribing them and creating reminders.
    """
    if not update.effective_user or not update.message or not update.message.voice:
        return

    user_id = update.effective_user.id

    user = get_user(user_id)
    if not user:
        await update.message.reply_text(get_text("error_occurred", "en"))
        return

    user_lang = user.get("language", "en")
    user_timezone = user.get("timezone", "America/Sao_Paulo")
    user_time_format = user.get("time_format", "24h")

    # Send "transcribing" status message
    status_msg = await update.message.reply_text(
        get_text("voice_transcribing", user_lang)
    )

    try:
        # Download voice file from Telegram
        voice = update.message.voice
        file = await context.bot.get_file(voice.file_id)

        voice_bytes = BytesIO()
        await file.download_to_memory(voice_bytes)
        voice_bytes.seek(0)

        # Convert ogg -> wav using pydub
        from pydub import AudioSegment
        audio = AudioSegment.from_ogg(voice_bytes)
        wav_bytes = BytesIO()
        audio.export(wav_bytes, format="wav")
        wav_bytes.seek(0)

        # Transcribe using Google SpeechRecognition
        import speech_recognition as sr
        recognizer = sr.Recognizer()
        with sr.AudioFile(wav_bytes) as source:
            audio_data = recognizer.record(source)
            stt_lang = STT_LANGUAGE_MAP.get(user_lang, "en-US")
            text = recognizer.recognize_google(audio_data, language=stt_lang)

        if not text or not text.strip():
            await status_msg.edit_text(get_text("voice_empty", user_lang))
            return

        # Show transcription to user
        await status_msg.edit_text(
            get_text("voice_transcribed", user_lang, text=text)
        )

        # === INTENT DETECTION ===
        # Try finance intent first (lazy import to avoid circular dependency)
        from handlers.finance import parse_finance_message, format_currency

        finance_result = parse_finance_message(text)
        if finance_result:
            amount, ftype, category, description = finance_result
            transaction_id = add_transaction(
                user_id=user_id,
                amount=amount,
                type=ftype,
                category=category,
                description=description,
            )
            if transaction_id:
                if ftype == 'expense':
                    label_pt = 'Despesa'
                    label_en = 'Expense'
                    label_sr = 'Trošak'
                else:
                    label_pt = 'Receita'
                    label_en = 'Income'
                    label_sr = 'Prihod'

                if user_lang == 'pt-br':
                    confirm = f"✅ {label_pt} registrada: {format_currency(amount, user_lang)} - {category}"
                elif user_lang == 'sr-lat':
                    confirm = f"✅ {label_sr} zabeležen: {format_currency(amount, user_lang)} - {category}"
                else:
                    confirm = f"✅ {label_en} recorded: {format_currency(amount, user_lang)} - {category}"

                await update.message.reply_text(confirm)
                logger.info(
                    f"Voice finance transaction created: user={user_id}, "
                    f"amount={amount}, type={ftype}, category={category}"
                )
                return
            else:
                await update.message.reply_text(get_text("error_occurred", user_lang))
                return

        # Try shopping intent
        shopping_result = detect_shopping_intent(text, user_lang)
        if shopping_result:
            action, data = shopping_result

            if action == 'create_list':
                list_id = create_shopping_list(user_id=user_id, name=data)
                if list_id:
                    if user_lang == 'pt-br':
                        confirm = f"✅ Lista criada: {data}"
                    elif user_lang == 'sr-lat':
                        confirm = f"✅ Lista kreirana: {data}"
                    else:
                        confirm = f"✅ List created: {data}"
                    await update.message.reply_text(confirm)
                    logger.info(f"Voice shopping list created: user={user_id}, name={data}")
                    return
                else:
                    await update.message.reply_text(get_text("error_occurred", user_lang))
                    return

            elif action == 'add_items':
                lists = get_active_shopping_lists(user_id=user_id)
                if not lists:
                    if user_lang == 'pt-br':
                        await update.message.reply_text(
                            "Você não tem nenhuma lista de compras ativa. Crie uma primeiro."
                        )
                    elif user_lang == 'sr-lat':
                        await update.message.reply_text(
                            "Nemate aktivnu listu za kupovinu. Prvo napravite jednu."
                        )
                    else:
                        await update.message.reply_text(
                            "You don't have any active shopping list. Create one first."
                        )
                    return

                list_id = lists[0]['id']
                added = []
                for item in data:
                    if add_shopping_item(list_id=list_id, name=item):
                        added.append(item)

                if added:
                    if user_lang == 'pt-br':
                        confirm = "✅ Item(ns) adicionado(s) à lista"
                    elif user_lang == 'sr-lat':
                        confirm = "✅ Stavka(e) dodata(e) na listu"
                    else:
                        confirm = "✅ Item(s) added to list"
                    await update.message.reply_text(confirm)
                    logger.info(
                        f"Voice shopping items added: user={user_id}, "
                        f"list_id={list_id}, items={added}"
                    )
                    return
                else:
                    await update.message.reply_text(get_text("error_occurred", user_lang))
                    return

        # Fallback: parse transcribed text as a reminder (original behavior)
        result = parse_reminder(text, user_timezone)

        if not result:
            await update.message.reply_text(
                get_text("reminder_parse_error", user_lang),
                parse_mode="Markdown"
            )
            logger.info(f"Failed to parse voice reminder from user {user_id}: '{text}'")
            return

        reminder_text, scheduled_time = result

        # Validate not in past
        try:
            tz = pytz.timezone(user_timezone)
        except pytz.UnknownTimeZoneError:
            tz = pytz.timezone("America/Sao_Paulo")
        now = datetime.now(tz).replace(tzinfo=None)
        if scheduled_time <= now:
            await update.message.reply_text(
                get_text("reminder_in_past", user_lang)
            )
            logger.info(f"User {user_id} tried to create voice reminder in the past: {scheduled_time}")
            return

        # Create reminder in database
        reminder_id = create_reminder(
            user_id=user_id,
            message_text=reminder_text,
            scheduled_time=scheduled_time
        )

        if reminder_id:
            confirmation_msg = format_reminder_confirmation(
                reminder_text, scheduled_time, user_time_format, now=now
            )
            try:
                await update.message.reply_text(confirmation_msg)
                logger.info(
                    f"Voice reminder created: ID={reminder_id}, user={user_id}, "
                    f"time={scheduled_time}, text='{reminder_text}'"
                )
            except (NetworkError, TimedOut) as e:
                logger.warning(f"Network error sending confirmation to user {user_id}, queuing: {e}")
                queue_message(user_id, confirmation_msg, message_type='reminder_confirmation')
            except Exception as e:
                logger.error(f"Error sending confirmation to user {user_id}, queuing: {e}")
                queue_message(user_id, confirmation_msg, message_type='reminder_confirmation')
        else:
            try:
                await update.message.reply_text(get_text("error_occurred", user_lang))
            except Exception as reply_error:
                logger.error(f"Failed to send error message to user {user_id}: {reply_error}")
            logger.error(f"Failed to create voice reminder in database for user {user_id}")

    except ImportError as e:
        logger.error(f"Missing dependency for voice handling: {e}")
        try:
            await status_msg.edit_text(get_text("voice_transcription_failed", user_lang))
        except Exception:
            pass
    except Exception as e:
        # Check if it's a speech_recognition specific error
        error_str = str(e).lower()
        if "unknownvalue" in error_str or "request" in error_str:
            logger.error(f"Google STT error for user {user_id}: {e}")
        else:
            logger.error(f"Voice handler error for user {user_id}: {e}", exc_info=True)
        try:
            await status_msg.edit_text(get_text("voice_transcription_failed", user_lang))
        except Exception:
            pass


def register_handlers(application):
    """Register voice message handler."""
    application.add_handler(MessageHandler(filters.VOICE, handle_voice_message))
