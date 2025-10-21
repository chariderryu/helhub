import sqlite3
import json
import feedparser
import re
from datetime import datetime, timezone, timedelta
from time import mktime
from screenshot_util import take_screenshot

# 追加: 文字列日付のパース用
from email.utils import parsedate_to_datetime  # RFC822 等

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

# ===== ここから日付処理の強化（追加） =====

def _parse_date_str(s: str):
    """RFC822 / ISO8601 を受け、UTC の datetime にして返す（失敗時は None）。"""
    if not s:
        return None
    s = s.strip()

    # 1) RFC822（例: Wed, 18 Oct 2023 12:34:56 GMT）
    try:
        dt = parsedate_to_datetime(s)
        # tz が無い場合は UTC とみなす
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        pass

    # 2) 代表的な ISO8601
    for fmt in ("%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue

    return None

def _choose_entry_datetime_utc(entry):
    """
    エントリーの公開日時を決定して UTC datetime を返す。
    優先順位:
      1) published_parsed
      2) updated_parsed
      3) published（文字列）
      4) updated（文字列）
      5) dc_date（RDFの dc:date → feedparser では 'dc_date' に入ることが多い）
      6) issued / created（保険）
      7) なければ現在UTC
    """
    # struct_time 系（feedparserが既にパース）
    if getattr(entry, 'published_parsed', None):
        return datetime.fromtimestamp(mktime(entry.published_parsed), tz=timezone.utc)
    if getattr(entry, 'updated_parsed', None):
        return datetime.fromtimestamp(mktime(entry.updated_parsed), tz=timezone.utc)

    # 文字列系（順に試す）
    for key in ("published", "updated", "dc_date", "issued", "created"):
        dt = _parse_date_str(entry.get(key))
        if dt:
            return dt

    return datetime.now(timezone.utc)

# ===== ここまで追加 =====

def isoformat_utc(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

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

            # 変更: dc:date を含む複数候補からUTCに正規化
            dt_utc = _choose_entry_datetime_utc(entry)
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
            # NG: naiveのnowをそのまま文字列化
            # scheduled_at = (datetime.now() + timedelta(hours=1)).isoformat(timespec='seconds')
            # OK: かならずUTC化してZで保存
            scheduled_at = isoformat_utc(datetime.now(timezone.utc) + timedelta(hours=1))
            
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
