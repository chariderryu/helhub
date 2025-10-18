import sqlite3
import json
import feedparser
import re
from datetime import datetime, timezone, timedelta
from time import mktime
from screenshot_util import take_screenshot

def load_config():
    """設定ファイルを読み込む"""
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def get_db_connection():
    config = load_config()
    db_path = config.get('database_path', 'content.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def _entry_matches_classification_rules(entry_title, media_id, config):
    """
    エントリーのタイトルが、特定のメディアIDの分類ルールに一致するかを判断する。
    """
    media_info = config.get('media_templates', {}).get(media_id, {})
    x_template_settings = media_info.get('x_post_template', {})
    rules = x_template_settings.get('filtering_rules', {})
    
    if rules.get('include_regex'):
        if not re.search(rules['include_regex'], entry_title):
            return False
            
    if rules.get('exclude_regex'):
        if re.search(rules['exclude_regex'], entry_title):
            return False
            
    return True

def _classify_entry_media_id_from_shared_feed(entry_title, config, media_ids_sharing_feed):
    """
    共有フィードのエントリーを分類する。
    helwa のルールを最優先で評価する。
    """
    # 1. 最優先ルール: helwa の include_regex に一致するか？
    if 'helwa' in media_ids_sharing_feed:
        if _entry_matches_classification_rules(entry_title, 'helwa', config):
            return 'helwa'
    
    # 2. 次の優先ルール: heldio のルールに一致するか？
    if 'heldio' in media_ids_sharing_feed:
        if _entry_matches_classification_rules(entry_title, 'heldio', config):
            return 'heldio'
    
    # 3. その他のメディアのルールをチェック (config.jsonの順)
    for media_id_candidate in media_ids_sharing_feed:
        if media_id_candidate not in ['helwa', 'heldio']:
            if _entry_matches_classification_rules(entry_title, media_id_candidate, config):
                return media_id_candidate
    
    return None

def process_feeds():
    """設定されたすべてのフィードを処理する"""
    config = load_config()
    conn = get_db_connection()
    
    feeds_to_process = {}
    for media_id, media_info in config.get('media_templates', {}).items():
        feed_url = media_info.get('feed_url')
        if not feed_url or "YOUR_RSS_FEED_URL_HERE" in feed_url or feed_url == "":
            continue
        if feed_url not in feeds_to_process:
            feeds_to_process[feed_url] = []
        feeds_to_process[feed_url].append(media_id)

    for feed_url, media_ids_sharing_feed in feeds_to_process.items():
        print(f"\n--- フィードを処理中: {feed_url} ---")
        
        feed = feedparser.parse(feed_url)
        
        for entry in reversed(feed.entries):
            entry_id = entry.get('id') or entry.get('link')
            entry_title = entry.get('title', '')
            entry_link = entry.get('link')
            
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                dt_utc = datetime.fromtimestamp(mktime(entry.published_parsed)).astimezone(timezone.utc)
            else:
                dt_utc = datetime.now(timezone.utc)
            published_date = dt_utc.isoformat()
            
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM content WHERE unique_id = ?", (entry_id,))
            if cursor.fetchone():
                continue
                
            print(f"  > 新規コンテンツ発見: {entry_title}")

            current_media_id = _classify_entry_media_id_from_shared_feed(
                entry_title, config, media_ids_sharing_feed
            )

            if not current_media_id:
                print(f"  > どのメディアにも分類できませんでした: '{entry_title}' - スキップします。")
                continue

            try:
                cursor.execute("""
                    INSERT INTO content (unique_id, media_id, title, link, published_date)
                    VALUES (?, ?, ?, ?, ?)
                """, (entry_id, current_media_id, entry_title, entry_link, published_date))
                conn.commit()
                print(f"  > [{current_media_id}]としてDBに保存しました。")
            except sqlite3.IntegrityError:
                print(f"  > DBへの保存中にIntegrityErrorが発生しました（unique_id重複？）。スキップします。")
                continue

            post_media_info = config.get('media_templates', {}).get(current_media_id, {})
            x_template = post_media_info.get('x_post_template', {})
            
            if not x_template.get('is_active', False):
                print(f"  > [{current_media_id}]のX投稿が無効なため、下書き作成をスキップします。")
                continue
            
            if any(keyword in entry_title for keyword in x_template.get('exclude_keywords', [])):
                print(f"  > X投稿スキップ: 除外キーワードがタイトルに含まれています。")
                continue

            message = x_template.get('template', '{title}\n{link}').format(title=entry_title, link=entry_link)
            scheduled_at = (datetime.now() + timedelta(hours=1)).isoformat(timespec='seconds')
            
            image_path = None
            img_settings = x_template.get('image_settings', {})
            if img_settings.get('attach_image'):
                if img_settings.get('mode') == 'auto':
                    image_path = take_screenshot(entry_link)
                elif img_settings.get('mode') == 'manual':
                    image_path = img_settings.get('manual_path', None)

            try:
                cursor.execute("""
                    INSERT INTO posts (media_id, status, scheduled_at, content_unique_id)
                    VALUES (?, 'draft', ?, ?)
                """, (current_media_id, scheduled_at, entry_id))
                post_id = cursor.lastrowid
                
                cursor.execute("""
                    INSERT INTO post_threads (post_id, thread_order, message, image_path)
                    VALUES (?, 1, ?, ?)
                """, (post_id, message, image_path))
                
                conn.commit()
                print(f"  > [{current_media_id}] X投稿の下書きを作成しました (投稿ID: {post_id})。")
            except Exception as e:
                print(f"  > エラー: X投稿下書きの作成に失敗しました - {e}")

    conn.close()
    print("\nすべてのフィード処理が完了しました。")


if __name__ == '__main__':
    process_feeds()

