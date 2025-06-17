# database.py
import sqlite3
import json

def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY,
        channel_id INTEGER UNIQUE NOT NULL,
        regions TEXT DEFAULT 'all',
        alert_message TEXT DEFAULT '🚨 Повітряна тривога в: {region}',
        end_alert_message TEXT DEFAULT '✅ Відбій тривоги в: {region}',
        artillery_message TEXT DEFAULT '💥 Артилерійський обстріл: {region}',
        end_artillery_message TEXT DEFAULT '✅ Відбій загрози артобстрілу: {region}'
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY,
        user_id INTEGER UNIQUE NOT NULL,
        expiry_date TEXT
    )
    ''')
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS known_channels (
        id INTEGER PRIMARY KEY,
        channel_id INTEGER UNIQUE NOT NULL,
        channel_title TEXT
    )
    ''')
    conn.commit()
    conn.close()

# --- Новые и обновленные функции ---

def get_channel_settings(channel_id):
    """Возвращает все настройки для конкретного канала."""
    conn = sqlite3.connect('bot_database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,))
    settings = cursor.fetchone()
    conn.close()
    return settings

def update_channel_message(channel_id, message_type, text):
    """Обновляет текст для конкретного типа сообщения."""
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    # Безопасно формируем запрос, чтобы избежать SQL-инъекций
    # Убедимся, что message_type - это одно из допустимых полей
    allowed_columns = ['alert_message', 'end_alert_message', 'artillery_message', 'end_artillery_message']
    if message_type not in allowed_columns:
        raise ValueError("Недопустимый тип сообщения")
    
    cursor.execute(f"UPDATE channels SET {message_type} = ? WHERE channel_id = ?", (text, channel_id))
    conn.commit()
    conn.close()

# --- Остальные функции (без изменений) ---

def add_known_channel(channel_id, channel_title):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO known_channels (channel_id, channel_title) VALUES (?, ?)", (channel_id, channel_title))
    conn.commit()
    conn.close()

def remove_known_channel(channel_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM known_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()

def get_all_known_channels():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT channel_id, channel_title FROM known_channels")
    channels = cursor.fetchall()
    conn.close()
    return channels

def add_or_get_channel(channel_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,))
    channel = cursor.fetchone()
    if not channel:
        cursor.execute("INSERT INTO channels (channel_id) VALUES (?)", (channel_id,))
        conn.commit()
    conn.close()

def get_all_channels():
    conn = sqlite3.connect('bot_database.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM channels")
    channels = cursor.fetchall()
    conn.close()
    return channels

def update_channel_regions(channel_id, regions_json):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE channels SET regions = ? WHERE channel_id = ?", (regions_json, channel_id))
    conn.commit()
    conn.close()

def add_admin(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()

def is_admin(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM admins WHERE user_id = ?", (user_id,))
    admin = cursor.fetchone()
    conn.close()
    return admin is not None