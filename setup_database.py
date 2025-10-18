import sqlite3
import json

def load_config():
    """設定ファイルを読み込む"""
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def setup_database():
    """データベースのテーブルを初期化（作成）する"""
    config = load_config()
    db_path = config.get('database_path', 'content.db')
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # --- content テーブル ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS content (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unique_id TEXT UNIQUE NOT NULL,
        media_id TEXT NOT NULL,
        title TEXT NOT NULL,
        link TEXT NOT NULL,
        published_date TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # --- posts テーブル ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        media_id TEXT,
        content_unique_id TEXT, -- RSS由来でない手動投稿の場合はNULLになる
        status TEXT NOT NULL CHECK(status IN ('draft', 'approved', 'posted', 'error')),
        scheduled_at TEXT NOT NULL,
        posted_at TEXT,
        error_message TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (content_unique_id) REFERENCES content (unique_id)
    )
    """)

    # --- post_threads テーブル ---
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS post_threads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        post_id INTEGER NOT NULL,
        thread_order INTEGER NOT NULL,
        message TEXT NOT NULL,
        image_path TEXT,
        posted_tweet_id TEXT,
        FOREIGN KEY (post_id) REFERENCES posts (id)
    )
    """)

    conn.commit()
    conn.close()
    
    print(f"データベース '{db_path}' のセットアップが完了しました。")


if __name__ == '__main__':
    setup_database()

