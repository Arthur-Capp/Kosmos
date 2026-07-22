"""
Database module for Kosmos Telegram Bot.
Handles SQLite database connection and operations.
"""

import sqlite3
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from contextlib import contextmanager

from config import DB_FULL_PATH

logger = logging.getLogger(__name__)


@contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    Automatically commits and closes the connection.
    """
    conn = sqlite3.connect(DB_FULL_PATH)
    conn.row_factory = sqlite3.Row  # Enable column access by name
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    finally:
        conn.close()


def migrate_recurring_columns(cursor):
    """
    Migration function to add recurring reminder columns to existing reminders table.
    Checks if columns exist before adding them to prevent errors.
    """
    logger.info("Checking for recurring columns migration...")

    # Get existing columns
    cursor.execute("PRAGMA table_info(reminders)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    # Define new columns to add
    new_columns = {
        'is_recurring': 'INTEGER DEFAULT 0',
        'recurrence_type': 'TEXT',
        'recurrence_interval': 'INTEGER',
        'recurrence_days': 'TEXT',
        'recurrence_day_of_month': 'INTEGER',
        'recurrence_end_date': 'TIMESTAMP'
    }

    # Add missing columns
    for column_name, column_def in new_columns.items():
        if column_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE reminders ADD COLUMN {column_name} {column_def}")
                logger.info(f"Added column '{column_name}' to reminders table")
            except Exception as e:
                logger.error(f"Error adding column '{column_name}': {e}")
                raise
        else:
            logger.debug(f"Column '{column_name}' already exists, skipping")

    logger.info("Recurring columns migration completed")


def migrate_remind_before_column(cursor):
    """
    Migration function to add remind_before column to the reminders table.
    Allows configuring how many days before the event the user should be reminded.
    """
    logger.info("Checking for remind_before column migration...")

    # Get existing columns
    cursor.execute("PRAGMA table_info(reminders)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if 'remind_before' not in existing_columns:
        try:
            cursor.execute("ALTER TABLE reminders ADD COLUMN remind_before INTEGER DEFAULT 1")
            logger.info("Added column 'remind_before' to reminders table")
        except Exception as e:
            logger.error(f"Error adding column 'remind_before': {e}")
            raise
    else:
        logger.debug("Column 'remind_before' already exists, skipping")

    logger.info("Remind_before column migration completed")


def migrate_web_token_column(cursor):
    """
    Migration function to add web_token column to the users table.
    Stores a unique token for web dashboard authentication.
    """
    logger.info("Checking for web_token column migration...")

    # Get existing columns
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if 'web_token' not in existing_columns:
        try:
            cursor.execute("ALTER TABLE users ADD COLUMN web_token TEXT")
            logger.info("Added column 'web_token' to users table")
        except Exception as e:
            logger.error(f"Error adding column 'web_token': {e}")
            raise
    else:
        logger.debug("Column 'web_token' already exists, skipping")

    logger.info("Web_token column migration completed")


def generate_web_token(user_id: int) -> Optional[str]:
    """
    Generate a unique web token for a user and store it in the database.
    If the user already has a token, return the existing one.

    Args:
        user_id: Telegram user ID

    Returns:
        Token string or None on failure
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Check if user already has a token
            cursor.execute("SELECT web_token FROM users WHERE telegram_id = ?", (user_id,))
            row = cursor.fetchone()

            if row and row['web_token']:
                logger.info(f"User {user_id} already has web token, returning existing")
                return row['web_token']

            # Generate new token
            token = uuid.uuid4().hex
            cursor.execute(
                "UPDATE users SET web_token = ? WHERE telegram_id = ?",
                (token, user_id)
            )

            logger.info(f"Web token generated for user {user_id}")
            return token
    except Exception as e:
        logger.error(f"Error generating web token for user {user_id}: {e}")
        return None


def get_user_by_web_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Get user by web token.

    Args:
        token: Web token string

    Returns:
        User data as dictionary or None if not found
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE web_token = ?", (token,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None
    except Exception as e:
        logger.error(f"Error getting user by web token: {e}")
        return None


def init_database():
    """
    Initialize database and create tables if they don't exist.
    """
    logger.info("Initializing database...")

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Create users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                telegram_id INTEGER PRIMARY KEY,
                username TEXT,
                language TEXT DEFAULT 'en',
                time_format TEXT DEFAULT '24h',
                timezone TEXT DEFAULT 'Europe/Belgrade',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Create reminders table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_text TEXT NOT NULL,
                scheduled_time TIMESTAMP NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                is_recurring INTEGER DEFAULT 0,
                recurrence_type TEXT,
                recurrence_interval INTEGER,
                recurrence_days TEXT,
                recurrence_day_of_month INTEGER,
                recurrence_end_date TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            )
        """)

        # Create index for faster queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reminders_user_status
            ON reminders(user_id, status)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reminders_scheduled_time
            ON reminders(scheduled_time, status)
        """)

        # Run migrations for recurring reminders feature
        migrate_recurring_columns(cursor)

        # Run migration for remind_before column
        migrate_remind_before_column(cursor)

        # Run migration for web_token column
        migrate_web_token_column(cursor)

        # ==================== SHOPPING LIST TABLES ====================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shopping_lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                category TEXT DEFAULT 'geral',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS shopping_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                list_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                quantity TEXT DEFAULT '1',
                estimated_price REAL DEFAULT 0,
                is_purchased INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (list_id) REFERENCES shopping_lists(id) ON DELETE CASCADE
            )
        """)

        # ==================== FINANCE TABLES ====================
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
                category TEXT NOT NULL DEFAULT 'outros',
                description TEXT DEFAULT '',
                transaction_date DATE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS finance_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                type TEXT NOT NULL CHECK(type IN ('income', 'expense')),
                color TEXT DEFAULT '#3498db',
                FOREIGN KEY (user_id) REFERENCES users(telegram_id) ON DELETE CASCADE
            )
        """)

        # ==================== INDEXES ====================
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_shopping_lists_user
            ON shopping_lists(user_id, is_active)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_shopping_items_list
            ON shopping_items(list_id)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_transactions_user_date
            ON transactions(user_id, transaction_date)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_finance_categories_user
            ON finance_categories(user_id)
        """)

    # Create pending messages table for message queue
    # (must be called outside the with block as it creates its own connection)
    # Import here to avoid circular import (message_queue imports from database)
    from message_queue import create_pending_message_table
    create_pending_message_table()

    logger.info("Database initialized successfully")


# ==================== USER OPERATIONS ====================

def create_user(telegram_id: int, username: Optional[str] = None,
                language: str = "en", timezone: str = "Europe/Belgrade") -> bool:
    """
    Create a new user or update existing user.

    Args:
        telegram_id: Telegram user ID
        username: Telegram username
        language: User's preferred language (en, sr-lat)
        timezone: User's timezone

    Returns:
        True if user was created/updated successfully
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO users (telegram_id, username, language, timezone)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    username = excluded.username,
                    language = excluded.language,
                    timezone = excluded.timezone
            """, (telegram_id, username, language, timezone))

            logger.info(f"User created/updated: {telegram_id} (@{username})")
            return True
    except Exception as e:
        logger.error(f"Error creating user {telegram_id}: {e}")
        return False


def get_user(telegram_id: int) -> Optional[Dict[str, Any]]:
    """
    Get user by Telegram ID.

    Args:
        telegram_id: Telegram user ID

    Returns:
        User data as dictionary or None if not found
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None
    except Exception as e:
        logger.error(f"Error getting user {telegram_id}: {e}")
        return None


def get_user_preferences(telegram_id: int) -> Dict[str, str]:
    """
    Get user preferences with defaults.

    Args:
        telegram_id: Telegram user ID

    Returns:
        Dict with keys: language, timezone, time_format
        Returns defaults if user not found or on error
    """
    defaults = {
        'language': 'en',
        'timezone': 'Europe/Belgrade',
        'time_format': '24h'
    }

    user = get_user(telegram_id)
    if not user:
        return defaults

    return {
        'language': user.get('language', defaults['language']),
        'timezone': user.get('timezone', defaults['timezone']),
        'time_format': user.get('time_format', defaults['time_format'])
    }


def update_user_language(telegram_id: int, language: str) -> bool:
    """Update user's language preference."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET language = ? WHERE telegram_id = ?",
                (language, telegram_id)
            )
            logger.info(f"User {telegram_id} language updated to {language}")
            return True
    except Exception as e:
        logger.error(f"Error updating language for user {telegram_id}: {e}")
        return False


def update_user_time_format(telegram_id: int, time_format: str) -> bool:
    """Update user's time format preference."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET time_format = ? WHERE telegram_id = ?",
                (time_format, telegram_id)
            )
            logger.info(f"User {telegram_id} time format updated to {time_format}")
            return True
    except Exception as e:
        logger.error(f"Error updating time format for user {telegram_id}: {e}")
        return False


def update_user_timezone(telegram_id: int, timezone: str) -> bool:
    """Update user's timezone."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET timezone = ? WHERE telegram_id = ?",
                (timezone, telegram_id)
            )
            logger.info(f"User {telegram_id} timezone updated to {timezone}")
            return True
    except Exception as e:
        logger.error(f"Error updating timezone for user {telegram_id}: {e}")
        return False


# ==================== REMINDER OPERATIONS ====================

def create_reminder(
    user_id: int,
    message_text: str,
    scheduled_time: datetime,
    is_recurring: bool = False,
    recurrence_type: Optional[str] = None,
    recurrence_interval: Optional[int] = None,
    recurrence_days: Optional[str] = None,
    recurrence_day_of_month: Optional[int] = None,
    recurrence_end_date: Optional[datetime] = None,
    remind_before: int = 1
) -> Optional[int]:
    """
    Create a new reminder (one-time or recurring).

    Args:
        user_id: Telegram user ID
        message_text: The reminder message
        scheduled_time: When to send the reminder (datetime object)
        is_recurring: Whether this is a recurring reminder
        recurrence_type: Type of recurrence ('daily', 'interval', 'weekly', 'monthly')
        recurrence_interval: For 'interval' type - number of days between occurrences
        recurrence_days: For 'weekly' type - JSON array of days (e.g., '["monday", "wednesday"]')
        recurrence_day_of_month: For 'monthly' type - day of month (1-31)
        recurrence_end_date: Optional end date for recurring reminders (None = forever)

    Returns:
        Reminder ID if created successfully, None otherwise
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO reminders (
                    user_id, message_text, scheduled_time, status,
                    is_recurring, recurrence_type, recurrence_interval,
                    recurrence_days, recurrence_day_of_month, recurrence_end_date,
                    remind_before
                )
                VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id, message_text, scheduled_time,
                1 if is_recurring else 0, recurrence_type, recurrence_interval,
                recurrence_days, recurrence_day_of_month, recurrence_end_date,
                remind_before
            ))

            reminder_id = cursor.lastrowid
            recurring_info = f", recurring={recurrence_type}" if is_recurring else ""
            logger.info(f"Reminder created: ID={reminder_id}, user={user_id}, time={scheduled_time}{recurring_info}")
            return reminder_id
    except Exception as e:
        logger.error(f"Error creating reminder for user {user_id}: {e}")
        return None


def get_user_reminders(user_id: int, status: str = "pending") -> List[Dict[str, Any]]:
    """
    Get all reminders for a user with specific status.

    Args:
        user_id: Telegram user ID
        status: Reminder status (pending, sent, cancelled)

    Returns:
        List of reminders as dictionaries
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM reminders
                WHERE user_id = ? AND status = ?
                ORDER BY scheduled_time ASC
            """, (user_id, status))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting reminders for user {user_id}: {e}")
        return []


def get_pending_reminders() -> List[Dict[str, Any]]:
    """
    Get all pending reminders that are due (scheduled_time <= now in user's timezone).

    The scheduled_time is stored as naive datetime in the user's local timezone.
    We must compare it with the current time in each user's timezone to correctly
    determine if a reminder is due.

    Returns:
        List of reminders as dictionaries
    """
    import pytz

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Fetch all pending reminders - we'll filter by timezone in Python
            # This is necessary because each user may have a different timezone
            cursor.execute("""
                SELECT r.*, u.timezone
                FROM reminders r
                JOIN users u ON r.user_id = u.telegram_id
                WHERE r.status = 'pending'
                ORDER BY r.scheduled_time ASC
                LIMIT 1000
            """)

            rows = cursor.fetchall()

            # Filter reminders that are due in each user's timezone
            due_reminders = []
            for row in rows:
                reminder = dict(row)
                user_timezone = reminder.get('timezone', 'Europe/Belgrade')

                try:
                    tz = pytz.timezone(user_timezone)
                except pytz.UnknownTimeZoneError:
                    tz = pytz.timezone('Europe/Belgrade')

                # Get current time in user's timezone (as naive datetime for comparison)
                now_in_user_tz = datetime.now(tz).replace(tzinfo=None)

                # Parse scheduled_time (stored as string in user's local time)
                # Handle various formats: with/without microseconds, with/without timezone
                time_str = reminder['scheduled_time']
                # Remove timezone info if present (e.g., "+01:00")
                if '+' in time_str:
                    time_str = time_str.split('+')[0]
                # Remove microseconds if present
                if '.' in time_str:
                    time_str = time_str.split('.')[0]
                scheduled_time = datetime.strptime(time_str, '%Y-%m-%d %H:%M:%S')

                # Check if reminder is due in user's timezone
                if scheduled_time <= now_in_user_tz:
                    due_reminders.append(reminder)

            return due_reminders
    except Exception as e:
        logger.error(f"Error getting pending reminders: {e}")
        return []


def get_reminders_by_date(target_date) -> List[Dict[str, Any]]:
    """
    Get all active reminders for a specific date, joined with user timezone.
    Used by the daily grouped reminder notification.

    Args:
        target_date: Date to search for (date object or string 'YYYY-MM-DD')

    Returns:
        List of reminders as dictionaries with timezone info
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, u.timezone
                FROM reminders r
                JOIN users u ON r.user_id = u.telegram_id
                WHERE DATE(r.scheduled_time) = ?
                AND r.status = 'pending'
                ORDER BY r.scheduled_time ASC
            """, (target_date,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting reminders by date {target_date}: {e}")
        return []


def get_user_reminders_by_date(user_id: int, target_date) -> List[Dict[str, Any]]:
    """
    Get all pending reminders for a specific user on a specific date.
    Used by /hoje and /amanha commands.

    Args:
        user_id: Telegram user ID
        target_date: Date to search for (date object or string 'YYYY-MM-DD')

    Returns:
        List of reminders as dictionaries
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT r.*, u.timezone
                FROM reminders r
                JOIN users u ON r.user_id = u.telegram_id
                WHERE DATE(r.scheduled_time) = ?
                AND r.status = 'pending'
                AND r.user_id = ?
                ORDER BY r.scheduled_time ASC
            """, (target_date, user_id))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting reminders for user {user_id} on date {target_date}: {e}")
        return []


def update_reminder_status(reminder_id: int, status: str) -> bool:
    """
    Update reminder status.

    Args:
        reminder_id: Reminder ID
        status: New status (pending, sent, cancelled)

    Returns:
        True if updated successfully
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE reminders SET status = ? WHERE id = ?",
                (status, reminder_id)
            )
            logger.info(f"Reminder {reminder_id} status updated to {status}")
            return True
    except Exception as e:
        logger.error(f"Error updating reminder {reminder_id}: {e}")
        return False


def update_reminder_time(reminder_id: int, new_scheduled_time: datetime) -> bool:
    """
    Update reminder scheduled time (for postpone feature).

    Args:
        reminder_id: Reminder ID
        new_scheduled_time: New scheduled time

    Returns:
        True if updated successfully
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE reminders
                SET scheduled_time = ?, status = 'pending'
                WHERE id = ?
            """, (new_scheduled_time, reminder_id))
            logger.info(f"Reminder {reminder_id} rescheduled to {new_scheduled_time}")
            return True
    except Exception as e:
        logger.error(f"Error rescheduling reminder {reminder_id}: {e}")
        return False


def delete_reminder(reminder_id: int) -> bool:
    """
    Delete a reminder (mark as cancelled).

    Args:
        reminder_id: Reminder ID

    Returns:
        True if deleted successfully
    """
    return update_reminder_status(reminder_id, "cancelled")


def update_reminder(
    reminder_id: int,
    message_text: Optional[str] = None,
    scheduled_time: Optional[datetime] = None
) -> bool:
    """
    Update reminder text and/or scheduled time.

    Args:
        reminder_id: Reminder ID
        message_text: New message text (optional)
        scheduled_time: New scheduled time (optional)

    Returns:
        True if updated successfully
    """
    if message_text is None and scheduled_time is None:
        logger.warning(f"update_reminder called with no changes for reminder {reminder_id}")
        return False

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Build dynamic UPDATE query
            updates = []
            params = []

            if message_text is not None:
                updates.append("message_text = ?")
                params.append(message_text)

            if scheduled_time is not None:
                updates.append("scheduled_time = ?")
                updates.append("status = 'pending'")  # Reset status when time changes
                params.append(scheduled_time)

            params.append(reminder_id)

            query = f"UPDATE reminders SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)

            logger.info(f"Reminder {reminder_id} updated: text={message_text is not None}, time={scheduled_time is not None}")
            return True
    except Exception as e:
        logger.error(f"Error updating reminder {reminder_id}: {e}")
        return False


def get_reminder_by_id(reminder_id: int) -> Optional[Dict[str, Any]]:
    """
    Get reminder by ID.

    Args:
        reminder_id: Reminder ID

    Returns:
        Reminder data as dictionary or None if not found
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
            row = cursor.fetchone()

            if row:
                return dict(row)
            return None
    except Exception as e:
        logger.error(f"Error getting reminder {reminder_id}: {e}")
        return None


# ==================== QUICK REMINDER OPERATIONS ====================

def get_frequent_reminder_texts(user_id: int, limit: int = 10) -> List[str]:
    """
    Get the most frequent reminder texts from a user's last 100 sent reminders.
    Excludes recurring reminder copies to avoid skewing results.

    Args:
        user_id: Telegram user ID
        limit: Maximum number of texts to return

    Returns:
        List of most frequent reminder texts (deduplicated by LOWER())
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT message_text, COUNT(*) as cnt
                FROM (
                    SELECT message_text FROM reminders
                    WHERE user_id = ? AND status = 'sent' AND is_recurring = 0
                    ORDER BY created_at DESC
                    LIMIT 100
                )
                GROUP BY LOWER(message_text)
                ORDER BY cnt DESC
                LIMIT ?
            """, (user_id, limit))

            rows = cursor.fetchall()
            return [row['message_text'] for row in rows]
    except Exception as e:
        logger.error(f"Error getting frequent reminders for user {user_id}: {e}")
        return []


# ==================== STATISTICS OPERATIONS ====================

def get_monthly_active_users() -> int:
    """
    Get count of users who created at least one reminder in the last 30 days.

    Returns:
        Number of active users in the last month
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(DISTINCT user_id) as active_users
                FROM reminders
                WHERE created_at >= datetime('now', '-30 days')
            """)
            row = cursor.fetchone()
            return row['active_users'] if row else 0
    except Exception as e:
        logger.error(f"Error getting monthly active users: {e}")
        return 0


def get_peak_monthly_users() -> int:
    """
    Get the highest number of unique users who created reminders in any single month.

    Returns:
        Peak number of users in a month
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT MAX(monthly_users) as peak_users
                FROM (
                    SELECT COUNT(DISTINCT user_id) as monthly_users
                    FROM reminders
                    WHERE created_at IS NOT NULL
                    GROUP BY strftime('%Y-%m', created_at)
                )
            """)
            row = cursor.fetchone()
            return row['peak_users'] if row and row['peak_users'] else 0
    except Exception as e:
        logger.error(f"Error getting peak monthly users: {e}")
        return 0


def get_total_users() -> int:
    """
    Get total number of registered users.

    Returns:
        Total number of users
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as total FROM users")
            row = cursor.fetchone()
            return row['total'] if row else 0
    except Exception as e:
        logger.error(f"Error getting total users: {e}")
        return 0


# ==================== SHOPPING LIST OPERATIONS ====================

def create_shopping_list(user_id: int, name: str, category: str = 'geral') -> Optional[int]:
    """Create a new shopping list. Returns list id or None on failure."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO shopping_lists (user_id, name, category)
                VALUES (?, ?, ?)
            """, (user_id, name, category))

            list_id = cursor.lastrowid
            logger.info(f"Shopping list created: ID={list_id}, user={user_id}, name={name}")
            return list_id
    except Exception as e:
        logger.error(f"Error creating shopping list for user {user_id}: {e}")
        return None


def add_shopping_item(list_id: int, name: str, quantity: str = '1', estimated_price: float = 0) -> bool:
    """Add an item to a shopping list. Returns True on success."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO shopping_items (list_id, name, quantity, estimated_price)
                VALUES (?, ?, ?, ?)
            """, (list_id, name, quantity, estimated_price))

            logger.info(f"Shopping item added: list={list_id}, name={name}, qty={quantity}")
            return True
    except Exception as e:
        logger.error(f"Error adding shopping item to list {list_id}: {e}")
        return False


def get_active_shopping_lists(user_id: int) -> List[Dict[str, Any]]:
    """Get all active shopping lists for a user. Returns list of dicts with id, name, category, item_count."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sl.id, sl.name, sl.category,
                       COUNT(si.id) as item_count,
                       SUM(CASE WHEN si.is_purchased = 0 THEN 1 ELSE 0 END) as pending_count
                FROM shopping_lists sl
                LEFT JOIN shopping_items si ON si.list_id = sl.id
                WHERE sl.user_id = ? AND sl.is_active = 1
                GROUP BY sl.id
                ORDER BY sl.created_at DESC
            """, (user_id,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting active shopping lists for user {user_id}: {e}")
        return []


def get_shopping_items(list_id: int) -> List[Dict[str, Any]]:
    """Get all items in a shopping list. Returns list of dicts with id, name, quantity, estimated_price, is_purchased."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, name, quantity, estimated_price, is_purchased
                FROM shopping_items
                WHERE list_id = ?
                ORDER BY is_purchased ASC, id ASC
            """, (list_id,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting shopping items for list {list_id}: {e}")
        return []


def mark_item_purchased(item_id: int, purchased: bool = True) -> bool:
    """Mark a shopping item as purchased or not. Returns True on success."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE shopping_items SET is_purchased = ? WHERE id = ?
            """, (1 if purchased else 0, item_id))

            logger.info(f"Shopping item {item_id} purchased={purchased}")
            return True
    except Exception as e:
        logger.error(f"Error updating shopping item {item_id}: {e}")
        return False


def delete_shopping_list(list_id: int) -> bool:
    """Delete a shopping list and all its items (cascade). Returns True on success."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM shopping_lists WHERE id = ?", (list_id,))

            logger.info(f"Shopping list deleted: ID={list_id}")
            return True
    except Exception as e:
        logger.error(f"Error deleting shopping list {list_id}: {e}")
        return False


def get_shopping_list_by_id(list_id: int) -> Optional[Dict[str, Any]]:
    """Get a single shopping list by id. Returns dict or None."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT sl.*, COUNT(si.id) as item_count,
                       SUM(CASE WHEN si.is_purchased = 0 THEN 1 ELSE 0 END) as pending_count
                FROM shopping_lists sl
                LEFT JOIN shopping_items si ON si.list_id = sl.id
                WHERE sl.id = ?
                GROUP BY sl.id
            """, (list_id,))

            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
    except Exception as e:
        logger.error(f"Error getting shopping list {list_id}: {e}")
        return None


# ==================== FINANCE OPERATIONS ====================

def add_transaction(user_id: int, amount: float, type: str, category: str = 'outros',
                    description: str = '', transaction_date: Optional[str] = None) -> Optional[int]:
    """Add a financial transaction. type is 'income' or 'expense'. transaction_date is YYYY-MM-DD string, defaults to today. Returns transaction id or None."""
    if transaction_date is None:
        transaction_date = datetime.now().strftime('%Y-%m-%d')

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions (user_id, amount, type, category, description, transaction_date)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, amount, type, category, description, transaction_date))

            transaction_id = cursor.lastrowid
            logger.info(f"Transaction created: ID={transaction_id}, user={user_id}, amount={amount}, type={type}")
            return transaction_id
    except Exception as e:
        logger.error(f"Error adding transaction for user {user_id}: {e}")
        return None


def get_transactions(user_id: int, month: Optional[int] = None, year: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get transactions for a user, optionally filtered by month/year. Returns list of dicts with id, amount, type, category, description, transaction_date."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            if month is not None and year is not None:
                cursor.execute("""
                    SELECT id, amount, type, category, description, transaction_date
                    FROM transactions
                    WHERE user_id = ?
                    AND strftime('%m', transaction_date) = ?
                    AND strftime('%Y', transaction_date) = ?
                    ORDER BY transaction_date DESC, id DESC
                """, (user_id, f'{month:02d}', str(year)))
            elif year is not None:
                cursor.execute("""
                    SELECT id, amount, type, category, description, transaction_date
                    FROM transactions
                    WHERE user_id = ?
                    AND strftime('%Y', transaction_date) = ?
                    ORDER BY transaction_date DESC, id DESC
                """, (user_id, str(year)))
            else:
                cursor.execute("""
                    SELECT id, amount, type, category, description, transaction_date
                    FROM transactions
                    WHERE user_id = ?
                    ORDER BY transaction_date DESC, id DESC
                """, (user_id,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting transactions for user {user_id}: {e}")
        return []


def get_monthly_summary(user_id: int, month: int, year: int) -> Dict[str, Any]:
    """Get monthly finance summary. Returns dict with total_income, total_expense, balance, expense_by_category (dict of category->amount)."""
    summary = {
        'total_income': 0.0,
        'total_expense': 0.0,
        'balance': 0.0,
        'expense_by_category': {}
    }

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get total income
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total
                FROM transactions
                WHERE user_id = ?
                AND type = 'income'
                AND strftime('%m', transaction_date) = ?
                AND strftime('%Y', transaction_date) = ?
            """, (user_id, f'{month:02d}', str(year)))
            row = cursor.fetchone()
            summary['total_income'] = row['total'] if row else 0.0

            # Get total expense and expense by category
            cursor.execute("""
                SELECT COALESCE(SUM(amount), 0) as total, category
                FROM transactions
                WHERE user_id = ?
                AND type = 'expense'
                AND strftime('%m', transaction_date) = ?
                AND strftime('%Y', transaction_date) = ?
                GROUP BY category
                ORDER BY total DESC
            """, (user_id, f'{month:02d}', str(year)))
            rows = cursor.fetchall()

            total_expense = 0.0
            expense_by_category = {}
            for row in rows:
                expense_by_category[row['category']] = row['total']
                total_expense += row['total']

            summary['total_expense'] = total_expense
            summary['expense_by_category'] = expense_by_category
            summary['balance'] = summary['total_income'] - summary['total_expense']

            return summary
    except Exception as e:
        logger.error(f"Error getting monthly summary for user {user_id}: {e}")
        return summary


def get_balance(user_id: int) -> float:
    """Get total balance (all income - all expense) for a user. Returns float."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COALESCE(SUM(CASE WHEN type = 'income' THEN amount ELSE 0 END), 0) -
                    COALESCE(SUM(CASE WHEN type = 'expense' THEN amount ELSE 0 END), 0) as balance
                FROM transactions
                WHERE user_id = ?
            """, (user_id,))

            row = cursor.fetchone()
            return row['balance'] if row else 0.0
    except Exception as e:
        logger.error(f"Error getting balance for user {user_id}: {e}")
        return 0.0


def get_category_summary(user_id: int, month: int, year: int) -> List[Dict[str, Any]]:
    """Get expense summary by category for a month. Returns list of dicts with category, total, count, ordered by total desc."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT category, COUNT(*) as count, SUM(amount) as total
                FROM transactions
                WHERE user_id = ?
                AND type = 'expense'
                AND strftime('%m', transaction_date) = ?
                AND strftime('%Y', transaction_date) = ?
                GROUP BY category
                ORDER BY total DESC
            """, (user_id, f'{month:02d}', str(year)))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting category summary for user {user_id}: {e}")
        return []


def get_recent_transactions(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    """Get most recent transactions. Returns list of dicts."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, amount, type, category, description, transaction_date
                FROM transactions
                WHERE user_id = ?
                ORDER BY transaction_date DESC, id DESC
                LIMIT ?
            """, (user_id, limit))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting recent transactions for user {user_id}: {e}")
        return []


def delete_transaction(transaction_id: int) -> bool:
    """Delete a transaction. Returns True on success."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))

            logger.info(f"Transaction deleted: ID={transaction_id}")
            return True
    except Exception as e:
        logger.error(f"Error deleting transaction {transaction_id}: {e}")
        return False


# Initialize database on module import
if __name__ == "__main__":
    # When run directly, initialize the database
    from config import setup_logging
    setup_logging()
    init_database()
    logger.info("Database module initialized")
