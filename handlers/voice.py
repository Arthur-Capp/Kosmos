"""
Voice message handler for Kosmos Telegram Bot.
Transcribes voice messages and creates reminders from the transcribed text.
"""

import logging
from io import BytesIO
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
from telegram.error import NetworkError, TimedOut

from database import get_user, create_reminder
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

        # Parse transcribed text as a reminder (same logic as reminder.py)
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
