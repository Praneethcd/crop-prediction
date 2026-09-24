import sqlite3
import os
from werkzeug.security import generate_password_hash
from datetime import datetime

DATABASE = 'agripredict.db'


def get_db():
    """Get a database connection."""
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    """Initialize the database with tables and default admin."""
    db = get_db()
    cursor = db.cursor()

    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            full_name TEXT NOT NULL,
            phone TEXT,
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS predictions_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            prediction_type TEXT NOT NULL,
            input_data TEXT NOT NULL,
            result TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS forum_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'General',
            crop_type TEXT DEFAULT 'General',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS marketplace_listings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            crop_name TEXT NOT NULL,
            quantity TEXT NOT NULL,
            price TEXT NOT NULL,
            description TEXT,
            listing_type TEXT DEFAULT 'sell',
            location TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
    ''')

    # Create default admin if not exists
    admin = cursor.execute('SELECT id FROM users WHERE email = ?',
                           ('admin@agripredict.com',)).fetchone()
    if not admin:
        cursor.execute(
            'INSERT INTO users (username, email, password_hash, role, full_name) VALUES (?, ?, ?, ?, ?)',
            ('admin', 'admin@agripredict.com',
             generate_password_hash('admin123'), 'admin', 'Administrator')
        )

    db.commit()
    db.close()


def get_user_by_email(email):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
    db.close()
    return user


def get_user_by_id(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    db.close()
    return user


def create_user(username, email, password_hash, role, full_name, phone='', location=''):
    db = get_db()
    try:
        db.execute(
            'INSERT INTO users (username, email, password_hash, role, full_name, phone, location) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (username, email, password_hash, role, full_name, phone, location)
        )
        db.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        db.close()


def save_prediction(user_id, prediction_type, input_data, result):
    db = get_db()
    db.execute(
        'INSERT INTO predictions_history (user_id, prediction_type, input_data, result) VALUES (?, ?, ?, ?)',
        (user_id, prediction_type, input_data, result)
    )
    db.commit()
    db.close()


def get_user_predictions(user_id, limit=20):
    db = get_db()
    predictions = db.execute(
        'SELECT * FROM predictions_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?',
        (user_id, limit)
    ).fetchall()
    db.close()
    return predictions


def save_forum_post(user_id, title, content, category='General', crop_type='General'):
    db = get_db()
    db.execute(
        'INSERT INTO forum_posts (user_id, title, content, category, crop_type) VALUES (?, ?, ?, ?, ?)',
        (user_id, title, content, category, crop_type)
    )
    db.commit()
    db.close()


def get_forum_posts(limit=50):
    db = get_db()
    posts = db.execute('''
        SELECT forum_posts.*, users.full_name, users.location
        FROM forum_posts
        JOIN users ON forum_posts.user_id = users.id
        ORDER BY forum_posts.created_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    db.close()
    return posts


def get_user_forum_posts(user_id):
    db = get_db()
    posts = db.execute(
        'SELECT * FROM forum_posts WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()
    db.close()
    return posts


def save_marketplace_listing(user_id, crop_name, quantity, price, description='', listing_type='sell', location=''):
    db = get_db()
    db.execute(
        'INSERT INTO marketplace_listings (user_id, crop_name, quantity, price, description, listing_type, location) VALUES (?, ?, ?, ?, ?, ?, ?)',
        (user_id, crop_name, quantity, price, description, listing_type, location)
    )
    db.commit()
    db.close()


def get_marketplace_listings(limit=50):
    db = get_db()
    listings = db.execute('''
        SELECT marketplace_listings.*, users.full_name, users.phone
        FROM marketplace_listings
        JOIN users ON marketplace_listings.user_id = users.id
        ORDER BY marketplace_listings.created_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    db.close()
    return listings


def get_user_listings(user_id):
    db = get_db()
    listings = db.execute(
        'SELECT * FROM marketplace_listings WHERE user_id = ? ORDER BY created_at DESC',
        (user_id,)
    ).fetchall()
    db.close()
    return listings


# Admin helpers
def get_all_users():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY created_at DESC').fetchall()
    db.close()
    return users


def get_user_stats():
    db = get_db()
    total = db.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
    farmers = db.execute("SELECT COUNT(*) as count FROM users WHERE role = 'farmer'").fetchone()['count']
    users = db.execute("SELECT COUNT(*) as count FROM users WHERE role = 'user'").fetchone()['count']
    predictions = db.execute('SELECT COUNT(*) as count FROM predictions_history').fetchone()['count']
    posts = db.execute('SELECT COUNT(*) as count FROM forum_posts').fetchone()['count']
    listings = db.execute('SELECT COUNT(*) as count FROM marketplace_listings').fetchone()['count']
    db.close()
    return {
        'total_users': total,
        'farmers': farmers,
        'users': users,
        'predictions': predictions,
        'forum_posts': posts,
        'listings': listings
    }


def delete_user(user_id):
    db = get_db()
    db.execute('DELETE FROM predictions_history WHERE user_id = ?', (user_id,))
    db.execute('DELETE FROM forum_posts WHERE user_id = ?', (user_id,))
    db.execute('DELETE FROM marketplace_listings WHERE user_id = ?', (user_id,))
    db.execute('DELETE FROM users WHERE id = ?', (user_id,))
    db.commit()
    db.close()


def get_recent_predictions(limit=10):
    db = get_db()
    predictions = db.execute('''
        SELECT predictions_history.*, users.full_name, users.role
        FROM predictions_history
        JOIN users ON predictions_history.user_id = users.id
        ORDER BY predictions_history.created_at DESC LIMIT ?
    ''', (limit,)).fetchall()
    db.close()
    return predictions


def delete_forum_post(post_id):
    db = get_db()
    db.execute('DELETE FROM forum_posts WHERE id = ?', (post_id,))
    db.commit()
    db.close()


def delete_marketplace_listing(listing_id):
    db = get_db()
    db.execute('DELETE FROM marketplace_listings WHERE id = ?', (listing_id,))
    db.commit()
    db.close()
