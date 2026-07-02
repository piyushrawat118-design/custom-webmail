import sqlite3
import datetime
import os

DB_PATH = 'webmail.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    # Settings table
    c.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imap_host TEXT,
            imap_port INTEGER,
            smtp_host TEXT,
            smtp_port INTEGER,
            email TEXT,
            password TEXT
        )
    ''')
    
    # Emails table
    c.execute('''
        CREATE TABLE IF NOT EXISTS emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder TEXT, -- 'inbox', 'sent', 'trash'
            subject TEXT,
            sender TEXT,
            recipient TEXT,
            body TEXT,
            date_received TEXT,
            uid TEXT UNIQUE -- To prevent duplicates
        )
    ''')
    conn.commit()
    conn.close()

def get_settings():
    conn = get_db()
    settings = conn.execute('SELECT * FROM settings ORDER BY id DESC LIMIT 1').fetchone()
    conn.close()
    return dict(settings) if settings else None

def save_settings(imap_host, imap_port, smtp_host, smtp_port, email, password):
    conn = get_db()
    conn.execute('DELETE FROM settings') # Keep only one config
    conn.execute('''
        INSERT INTO settings (imap_host, imap_port, smtp_host, smtp_port, email, password)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (imap_host, imap_port, smtp_host, smtp_port, email, password))
    conn.commit()
    conn.close()

def save_email(folder, subject, sender, recipient, body, date_received, uid=None):
    conn = get_db()
    try:
        conn.execute('''
            INSERT INTO emails (folder, subject, sender, recipient, body, date_received, uid)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (folder, subject, sender, recipient, body, date_received, uid))
        conn.commit()
    except sqlite3.IntegrityError:
        pass # Duplicate UID
    conn.close()

def get_emails(folder):
    conn = get_db()
    emails = conn.execute('SELECT * FROM emails WHERE folder = ? ORDER BY id DESC', (folder,)).fetchall()
    conn.close()
    return [dict(e) for e in emails]

def move_to_trash(email_id):
    conn = get_db()
    conn.execute('UPDATE emails SET folder = ? WHERE id = ?', ('trash', email_id))
    conn.commit()
    conn.close()

def delete_email(email_id):
    conn = get_db()
    conn.execute('DELETE FROM emails WHERE id = ?', (email_id,))
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
