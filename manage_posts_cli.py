import sqlite3
import json
from datetime import datetime, timedelta, timezone  # ★ timezone 追加
from screenshot_util import take_screenshot
import os
import tempfile
import subprocess

# ★ 追加: タイムゾーン（Python 3.9+ 標準）
from zoneinfo import ZoneInfo

def load_config():
    """設定ファイルを読み込む"""
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def get_db_connection():
    """設定ファイルからDBパスを読み込み、接続を返す"""
    config = load_config()
    db_path = config.get('database_path', 'content.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# ★ 追加: TZ設定の取得（config.json で上書き可能）
def get_tz_prefs():
    cfg = load_config()
    sched = cfg.get("scheduling", {})
    input_tz = sched.get("input_tz", "Asia/Tokyo")         # 日本時間既定
    preview_tz = sched.get("preview_tz", "Pacific/Auckland")  # NZ 既定
    return input_tz, preview_tz

# ★ 追加: UTC ISO8601（...Z 統一）
def isoformat_utc(dt: datetime) -> str:
    dt_utc = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt_utc.isoformat().replace("+00:00", "Z")

# ★ 追加: “UTC っぽい文字列”を tz-aware datetime に（Z/オフセット/なし対応）
def parse_utcish(iso_str: str) -> datetime:
    if not iso_str:
        return None
    s = iso_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except Exception:
        return None
    if dt.tzinfo is None:  # tzなしはUTCとみなす（過去データ救済）
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

# ★ 追加: 'YYYY-MM-DD [HH:MM[:SS]]' を input_tz で tz-aware に
def parse_local_datetime(s: str, tz_name: str) -> datetime:
    s = s.strip().replace("T", " ")
    fmts = ["%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
    tz = ZoneInfo(tz_name)
    last_err = None
    for fmt in fmts:
        try:
            naive = datetime.strptime(s, fmt)
            # 日付のみのときは 09:00 を既定に（必要なら変更）
            if fmt == "%Y-%m-%d":
                naive = naive.replace(hour=9, minute=0, second=0)
            return naive.replace(tzinfo=tz)
        except Exception as e:
            last_err = e
    raise ValueError(f"日時の解釈に失敗: '{s}' (tz={tz_name}) / {last_err}")

# ★ 追加: UTC文字列を任意TZの見やすい表記へ
def pretty_in_tz(iso_utc: str, tz_name: str) -> str:
    dt = parse_utcish(iso_utc)
    if not dt:
        return "-"
    local = dt.astimezone(ZoneInfo(tz_name))
    return local.strftime("%Y-%m-%d %H:%M (%Z)")

def _edit_text_in_editor(initial_content=""):
    """
    一時ファイルを作成し、外部エディタで編集させ、その結果を返す。
    """
    config = load_config()
#    editor_path = config.get('editor_path', os.getenv('EDITOR', 'notepad.exe'))
    editor_path = 'C:/bin/hidemaru/Hidemaru.exe'

    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix=".txt", encoding='utf-8') as tf:
        tf.write(initial_content)
        temp_filepath = tf.name

    print(f"外部エディタ ({editor_path}) を起動します。編集後、保存してエディタを終了してください。")
    
    try:
        subprocess.run([editor_path, "/fu8", temp_filepath], check=True)
    except FileNotFoundError:
        print(f"!!! エラー: エディタ '{editor_path}' が見つかりません。")
        print("!!! config.jsonの'editor_path'を確認するか、環境変数 EDITOR を設定してください。")
        os.unlink(temp_filepath)
        return None
    except Exception as e:
        print(f"!!! エディタの起動中にエラーが発生しました: {e}")
        os.unlink(temp_filepath)
        return None

    with open(temp_filepath, 'r', encoding='utf-8') as f:
        edited_content = f.read().strip()
        
    os.unlink(temp_filepath)
    
    return edited_content

def display_drafts(conn):
    """下書き状態の投稿を一覧表示する"""
    input_tz, preview_tz = get_tz_prefs()  # ★
    print("\n--- 投稿下書き一覧 (ステータス: draft) ---")
    drafts = conn.execute("SELECT id, media_id, scheduled_at FROM posts WHERE status = 'draft' ORDER BY id").fetchall()
    if not drafts:
        print("下書きはありません。")
        return
    for draft in drafts:
        post_id = draft['id']
        threads = conn.execute("SELECT message FROM post_threads WHERE post_id = ? ORDER BY thread_order LIMIT 1", (post_id,)).fetchone()
        first_line = threads['message'].split('\n')[0:] if threads else " (メッセージなし)"
        sched_utc = draft['scheduled_at'] or ""
        # ★ 追記: プレビュータイムゾーンでの見え方
        sched_local = pretty_in_tz(sched_utc, preview_tz) if sched_utc else "-"
        print(f"  ID: {post_id:<4} | メディア: {draft['media_id']:<18} | 予約(UTC): {sched_utc:<20} | → {preview_tz}: {sched_local} | 内容: {first_line[:70]}...")

def view_post_details(conn, post_id):
    """指定されたIDの投稿詳細を表示する"""
    input_tz, preview_tz = get_tz_prefs()  # ★
    post = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        print("指定されたIDの投稿が見つかりません。")
        return
    
    print("\n--- 投稿詳細 ---")
    sched_utc = post['scheduled_at'] or ""
    print(f"ID: {post['id']}, メディア: {post['media_id']}, ステータス: {post['status']}")
    if sched_utc:
        print(f"予約日時: {sched_utc} (UTC)  /  {preview_tz}: {pretty_in_tz(sched_utc, preview_tz)}  /  JST: {pretty_in_tz(sched_utc, 'Asia/Tokyo')}")
    else:
        print("予約日時: -")
    
    threads = conn.execute("SELECT * FROM post_threads WHERE post_id = ? ORDER BY thread_order", (post_id,)).fetchall()
    for thread in threads:
        print(f"\n  [スレッド {thread['thread_order']}] (thread_id: {thread['id']})")
        print(f"  メッセージ:\n---\n{thread['message']}\n---")
        if thread['image_path']:
            print(f"  添付画像: {thread['image_path']}")
        else:
            print("  添付画像: なし")

def new_post(conn):
    """新しい投稿を手動で作成する"""
    print("\n--- 新規投稿作成 ---")
    
    config = load_config()
    media_templates = config.get('media_templates', {})
    media_ids = list(media_templates.keys())
    
    print("メディアを選択してください:")
    for i, mid in enumerate(media_ids):
        print(f"  {i+1}. {mid}")
    try:
        choice = int(input("> ").strip()) - 1
        media_id = media_ids[choice]
    except (ValueError, IndexError):
        print("不正な選択です。キャンセルしました。")
        return

    template_str = media_templates.get(media_id, {}).get('x_post_template', {}).get('template', '')
    initial_content = template_str.format(title="", link="")

    print("最初のツイートのメッセージをエディタで入力します。")
    message = _edit_text_in_editor(initial_content)

    if not message:
        print("メッセージが空のため、作成をキャンセルしました。")
        return

    # ★ 変更: 予約時刻の既定は「今から1時間後（UTC）」に統一
    scheduled_at = isoformat_utc(datetime.now(timezone.utc) + timedelta(hours=1))

    cursor = conn.cursor()
    cursor.execute("INSERT INTO posts (media_id, status, scheduled_at) VALUES (?, 'draft', ?)", (media_id, scheduled_at))
    post_id = cursor.lastrowid
    
    cursor.execute("INSERT INTO post_threads (post_id, thread_order, message) VALUES (?, 1, ?)", (post_id, message))
    
    conn.commit()
    print(f"\n新しい下書きを作成しました (投稿ID: {post_id})。")

def delete_post(conn, post_id):
    """指定されたIDの投稿（下書き）を削除する"""
    post = conn.execute("SELECT id, status FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not post:
        print("指定されたIDの投稿が見つかりません。")
        return
    
    if post['status'] != 'draft':
        print(f"エラー: ID {post_id} は下書き状態ではないため削除できません (現在の状態: {post['status']})。")
        return

    print(f"\n投稿ID: {post_id} を削除します。")
    view_post_details(conn, post_id)
    confirm = input("本当によろしいですか？ (y/n): ").strip().lower()
    
    if confirm == 'y':
        conn.execute("DELETE FROM post_threads WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
        print(f"投稿ID: {post_id} を削除しました。")
    else:
        print("削除をキャンセルしました。")

def add_thread(conn, post_id):
    """新しいスレッドを投稿に追加する"""
    max_order = conn.execute("SELECT MAX(thread_order) as max FROM post_threads WHERE post_id = ?", (post_id,)).fetchone()['max']
    new_order = (max_order or 0) + 1
    
    print(f"スレッド {new_order} のメッセージをエディタで入力します。")
    message = _edit_text_in_editor()
    
    if not message:
        print("メッセージが空のため、追加をキャンセルしました。")
        return

    conn.execute("INSERT INTO post_threads (post_id, thread_order, message) VALUES (?, ?, ?)", (post_id, new_order, message))
    conn.commit()
    print(f"スレッド {new_order} を追加しました。")
    view_post_details(conn, post_id)


def edit_post_or_thread(conn, post_id, thread_order_to_edit=None):
    """投稿または特定のスレッドを編集する"""
    thread_to_edit = None
    if thread_order_to_edit is None:
        threads = conn.execute("SELECT id, message, thread_order FROM post_threads WHERE post_id = ?", (post_id,)).fetchall()
        if not threads:
            print("編集対象のスレッドが見つかりません。")
            return
        if len(threads) > 1:
            print("この投稿は複数のスレッドからなります。編集するスレッドの順序を指定してください。")
            print("コマンド例: edit-thread [ID] [順序]")
            view_post_details(conn, post_id)
            return
        thread_to_edit = threads[0]
    else:
        thread_to_edit = conn.execute("SELECT id, message, thread_order FROM post_threads WHERE post_id = ? AND thread_order = ?", (post_id, thread_order_to_edit)).fetchone()

    if not thread_to_edit:
        print("指定されたスレッドが見つかりません。")
        return

    print(f"スレッド {thread_to_edit['thread_order']} のメッセージをエディタで編集します。")
    new_message = _edit_text_in_editor(thread_to_edit['message'])

    if new_message is not None:
        conn.execute("UPDATE post_threads SET message = ? WHERE id = ?", (new_message, thread_to_edit['id']))
        conn.commit()
        print("メッセージを更新しました。")
    else:
        print("メッセージの編集をキャンセルしました。")

def delete_thread(conn, post_id, thread_order_to_delete):
    """特定のスレッドを削除する"""
    thread_count = conn.execute("SELECT COUNT(*) as count FROM post_threads WHERE post_id = ?", (post_id,)).fetchone()['count']
    if thread_count <= 1:
        print("エラー: 最後のスレッドは削除できません。")
        return

    thread = conn.execute("SELECT id FROM post_threads WHERE post_id = ? AND thread_order = ?", (post_id, thread_order_to_delete)).fetchone()
    if not thread:
        print("指定されたスレッドが見つかりません。")
        return

    conn.execute("DELETE FROM post_threads WHERE id = ?", (thread['id'],))
    remaining_threads = conn.execute("SELECT id FROM post_threads WHERE post_id = ? ORDER BY thread_order", (post_id,)).fetchall()  # NOTE: 元コードのまま
    # ↑ 元コードに ORDER BY のスペース抜けがある場合は修正してください: "ORDER BY"
    # ここではオリジナルを尊重しつつコメントで注意喚起します。
    for i, remaining_thread in enumerate(remaining_threads):
        conn.execute("UPDATE post_threads SET thread_order = ? WHERE id = ?", (i + 1, remaining_thread['id']))
    
    conn.commit()
    print(f"スレッド {thread_order_to_delete} を削除し、順序を更新しました。")
    view_post_details(conn, post_id)


def set_schedule(conn, post_id):
    """投稿の予約日時を設定する（入力TZで解釈→UTCで保存）"""
    input_tz, preview_tz = get_tz_prefs()  # ★ 入力TZ/プレビューTZ
    print("予約日時を設定します。例: 'now', '+30m', '+2h', '+1d', '2025-10-20 15:00'（既定=日本時間として解釈）")
    print(f"入力タイムゾーン: {input_tz} / プレビュー: {preview_tz}")
    time_str = input("> ").strip()
    
    # 入力TZの現在時刻
    now_local = datetime.now(ZoneInfo(input_tz))
    scheduled_dt_local = None

    if time_str == 'now':
        scheduled_dt_local = now_local
    elif time_str.startswith('+'):
        try:
            num = int(time_str[1:-1])
            unit = time_str[-1]
            delta = timedelta()
            if unit == 'm': delta = timedelta(minutes=num)
            elif unit == 'h': delta = timedelta(hours=num)
            elif unit == 'd': delta = timedelta(days=num)
            else:
                print("不正な単位です。(m, h, d)")
                return
            scheduled_dt_local = now_local + delta
        except (ValueError, IndexError):
            print("不正な形式です。例: +5m, +1h, +2d")
            return
    else:
        try:
            # 文字列を input_tz として解釈
            scheduled_dt_local = parse_local_datetime(time_str, input_tz)
        except ValueError as e:
            print(str(e))
            print("不正な日時形式です。例: 2025-10-20 15:00")
            return

    # UTC に正規化して保存
    scheduled_at = isoformat_utc(scheduled_dt_local)

    conn.execute("UPDATE posts SET scheduled_at = ? WHERE id = ?", (scheduled_at, post_id))
    conn.commit()

    # 確認出力（UTC / JST / プレビューTZ）
    print(f"予約日時を {scheduled_at} (UTC) に設定しました。")
    print(f"  • 日本時間: {pretty_in_tz(scheduled_at, 'Asia/Tokyo')}")
    print(f"  • {preview_tz}: {pretty_in_tz(scheduled_at, preview_tz)}")

def manage_image(conn, post_id):
    """投稿の画像を管理する"""
    query = """
        SELECT pt.id, c.link, pt.image_path
        FROM post_threads pt
        INNER JOIN posts p ON p.id = pt.post_id
        LEFT JOIN content c ON c.unique_id = p.content_unique_id
        WHERE pt.post_id = ? AND pt.thread_order = 1
    """
    thread = conn.execute(query, (post_id,)).fetchone()
    if not thread:
        print("対象のスレッドが見つかりません。")
        return
    
    original_link = thread['link']

    print(f"\n--- 画像管理 (投稿ID: {post_id}) ---")
    print(f"現在の添付画像: {thread['image_path'] or 'なし'}")
    print("操作を選択してください:")
    if original_link: print("  1. スクリーンショットを自動撮影して添付")
    print("  2. ファイルパスを手動で指定して添付")
    print("  3. 添付画像を削除")
    
    choice = input("> ").strip()
    new_image_path = None
    
    if choice == '1':
        if not original_link:
            print("エラー: この投稿はRSSフィード由来ではないため、自動撮影できません。")
            return
        new_image_path = take_screenshot(original_link)
    elif choice == '2':
        path = input("画像ファイルのパスを入力してください: ").strip().replace('"', '')
        if os.path.exists(path):
            new_image_path = path
        else:
            print(f"ファイルが見つかりません: {path}")
            return
    elif choice == '3':
        new_image_path = ""
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
    display_drafts(conn)

    while True:
        print("\n--- コマンド一覧 ---")
        print(" 基本: list | new | view [ID] | approve [ID] | delete [ID] | exit")
        print(" 編集: edit [ID] (単一) | schedule [ID] | image [ID]")
        print(" ｽﾚｯﾄﾞ: add-thread [ID] | edit-thread [ID] [順序] | del-thread [ID] [順序]")

        command_input = input("> ").strip().split()
        if not command_input: continue
        
        cmd = command_input[0]
        
        if cmd == 'exit': break
        if cmd == 'list':
            display_drafts(conn)
            continue
        if cmd == 'new':
            new_post(conn)
            display_drafts(conn)
            continue
            
        try:
            if cmd in ['view', 'add-thread', 'schedule', 'image', 'approve', 'edit', 'delete']:
                if len(command_input) < 2: raise IndexError("IDが必要です。")
                post_id = command_input[1]
                if cmd == 'view': view_post_details(conn, post_id)
                elif cmd == 'add-thread': add_thread(conn, post_id)
                elif cmd == 'schedule': set_schedule(conn, post_id)
                elif cmd == 'image': manage_image(conn, post_id)
                elif cmd == 'approve':
                    approve_post(conn, post_id)
                    print("\n承認後の下書き一覧:")
                    display_drafts(conn)
                elif cmd == 'edit':
                    edit_post_or_thread(conn, post_id)
                elif cmd == 'delete':
                    delete_post(conn, post_id)
                    print("\n削除後の下書き一覧:")
                    display_drafts(conn)

            elif cmd in ['edit-thread', 'del-thread']:
                if len(command_input) < 3: raise IndexError("IDとスレッド順序が必要です。")
                post_id = command_input[1]
                thread_order = int(command_input[2])
                if cmd == 'edit-thread': edit_post_or_thread(conn, post_id, thread_order)
                elif cmd == 'del-thread': delete_thread(conn, post_id, thread_order)

            else:
                print(f"不明なコマンドです: {cmd}")
        
        except IndexError as e:
            print(f"エラー: コマンドの引数が不足しています - {e}")
        except ValueError:
            print("エラー: IDやスレッド順序には数値を指定してください。")
        except Exception as e:
            print(f"予期せぬエラーが発生しました: {e}")

    conn.close()
    print("終了します。")

if __name__ == '__main__':
    main()
