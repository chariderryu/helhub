import sqlite3
import json
from datetime import datetime, timedelta
from screenshot_util import take_screenshot
import os

def get_db_connection():
    """設定ファイルからDBパスを読み込み、接続を返す"""
    with open('config.json', 'r', encoding='utf-8') as f:
        config = json.load(f)
    db_path = config.get('database_path', 'content.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def display_drafts(conn):
    """下書き状態の投稿を一覧表示する"""
    print("\n--- 投稿下書き一覧 (ステータス: draft) ---")
    drafts = conn.execute("SELECT id, media_id, scheduled_at FROM posts WHERE status = 'draft' ORDER BY id").fetchall()
    if not drafts:
        print("下書きはありません。")
        return
    for draft in drafts:
        post_id = draft['id']
        threads = conn.execute("SELECT message FROM post_threads WHERE post_id = ? ORDER BY thread_order LIMIT 1", (post_id,)).fetchone()
        first_line = threads['message'].split('\n')[0] if threads else " (メッセージなし)"
        print(f"  ID: {post_id}, メディア: {draft['media_id']}, 予約: {draft['scheduled_at']}, 内容: {first_line[:40]}...")


def view_post_details(conn, post_id):
    """指定されたIDの投稿詳細を表示する"""
    post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        print("指定されたIDの投稿が見つかりません。")
        return
    
    print("\n--- 投稿詳細 ---")
    print(f"ID: {post['id']}, メディア: {post['media_id']}, ステータス: {post['status']}, 予約日時: {post['scheduled_at']}")
    
    threads = conn.execute("SELECT * FROM post_threads WHERE post_id = ? ORDER BY thread_order", (post_id,)).fetchall()
    for thread in threads:
        print(f"\n  [スレッド {thread['thread_order']}]")
        print(f"  メッセージ:\n---\n{thread['message']}\n---")
        if thread['image_path']:
            print(f"  添付画像: {thread['image_path']}")
        else:
            print("  添付画像: なし")

def edit_message(conn, post_id):
    """投稿のメッセージを編集する"""
    threads = conn.execute("SELECT id, thread_order, message FROM post_threads WHERE post_id = ? ORDER BY thread_order", (post_id,)).fetchall()
    if not threads:
        print("編集対象のスレッドが見つかりません。")
        return

    for thread in threads:
        print(f"\n--- 現在のメッセージ (スレッド {thread['thread_order']}) ---")
        print(thread['message'])
        
        new_message = input(f"新しいメッセージを入力してください（Enterのみで変更しない）:\n> ")
        if new_message:
            conn.execute("UPDATE post_threads SET message = ? WHERE id = ?", (new_message, thread['id']))
            conn.commit()
            print("メッセージを更新しました。")

def set_schedule(conn, post_id):
    """投稿の予約日時を設定する"""
    print("予約日時を設定します。例: 'now', '+1h', '+2d', '2025-10-20 15:00'")
    time_str = input("> ").strip()
    
    scheduled_at = ""
    now = datetime.now()

    if time_str == 'now':
        scheduled_at = now.isoformat(timespec='seconds')
    elif time_str.startswith('+'):
        try:
            num = int(time_str[1:-1])
            unit = time_str[-1]
            delta = timedelta()
            if unit == 'm':
                delta = timedelta(minutes=num)
            elif unit == 'h':
                delta = timedelta(hours=num)
            elif unit == 'd':
                delta = timedelta(days=num)
            else:
                print("不正な単位です。(m, h, d)")
                return
            scheduled_at = (now + delta).isoformat(timespec='seconds')
        except (ValueError, IndexError):
            print("不正な形式です。例: +5m, +1h, +2d")
            return
    else:
        try:
            # 時刻のみ指定された場合、今日の日付を補完
            if len(time_str) <= 5 and ':' in time_str:
                time_str = f"{now.strftime('%Y-%m-%d')} {time_str}"
            
            dt_obj = datetime.fromisoformat(time_str)
            scheduled_at = dt_obj.isoformat(timespec='seconds')
        except ValueError:
            print("不正な日時形式です。例: 2025-10-20 15:00")
            return

    conn.execute("UPDATE posts SET scheduled_at = ? WHERE id = ?", (scheduled_at, post_id))
    conn.commit()
    print(f"予約日時を {scheduled_at} に設定しました。")

def manage_image(conn, post_id):
    """投稿の画像を管理する"""
    # ★ 修正点: どのテーブルのidかを明確に指定
    query = """
        SELECT
            pt.id,
            c.link,
            pt.image_path
        FROM post_threads pt
        INNER JOIN posts p ON p.id = pt.post_id
        INNER JOIN content c ON c.unique_id = p.content_unique_id
        WHERE pt.post_id = ? AND pt.thread_order = 1
    """
    thread = conn.execute(query, (post_id,)).fetchone()
    if not thread:
        print("対象のスレッドまたは関連するコンテンツが見つかりません。")
        return

    print(f"\n--- 画像管理 (投稿ID: {post_id}) ---")
    print(f"現在の添付画像: {thread['image_path'] or 'なし'}")
    print("操作を選択してください:")
    print("  1. スクリーンショットを自動撮影して添付")
    print("  2. ファイルパスを手動で指定して添付")
    print("  3. 添付画像を削除")
    
    choice = input("> ").strip()
    new_image_path = None
    
    if choice == '1':
        new_image_path = take_screenshot(thread['link'])
    elif choice == '2':
        path = input("画像ファイルのパスを入力してください: ").strip().replace('"', '')
        if os.path.exists(path):
            new_image_path = path
        else:
            print(f"ファイルが見つかりません: {path}")
            return
    elif choice == '3':
        new_image_path = "" # 空文字で削除を示す
    else:
        return

    conn.execute("UPDATE post_threads SET image_path = ? WHERE id = ?", (new_image_path or None, thread['id']))
    conn.commit()
    print("添付画像を更新しました。")


def approve_post(conn, post_id):
    """投稿を承認する"""
    conn.execute("UPDATE posts SET status = 'approved' WHERE id = ?", (post_id,))
    conn.commit()
    print(f"投稿ID: {post_id} を承認しました。予約日時に投稿されます。")

def main():
    """対話形式で投稿を管理するメインループ"""
    conn = get_db_connection()
    
    # ★ 修正点: 最初に一度だけリストを表示
    display_drafts(conn)

    while True:
        # ★ 修正点: 新しいコマンドプロンプト
        print("\nコマンド: list | view [ID] | edit [ID] | schedule [ID] | image [ID] | approve [ID] | exit")
        
        command_input = input("> ").strip().split()
        if not command_input:
            continue
        
        cmd = command_input[0]
        
        if cmd == 'exit':
            break

        # ★ 修正点: listコマンドを追加
        if cmd == 'list':
            display_drafts(conn)
            continue
            
        if len(command_input) < 2:
            if cmd in ['view', 'edit', 'schedule', 'image', 'approve']:
                print("IDを指定してください。")
            else:
                 print(f"不明なコマンドです: {cmd}")
            continue
            
        post_id = command_input[1]
        
        if cmd == 'view':
            view_post_details(conn, post_id)
        elif cmd == 'edit':
            edit_message(conn, post_id)
        elif cmd == 'schedule':
            set_schedule(conn, post_id)
        elif cmd == 'image':
            manage_image(conn, post_id)
        elif cmd == 'approve':
            approve_post(conn, post_id)
            # ★ 修正点: 承認後にリストを更新
            print("\n承認後の下書き一覧:")
            display_drafts(conn)
        else:
            print(f"不明なコマンドです: {cmd}")

    conn.close()
    print("終了します。")

if __name__ == '__main__':
    main()

