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

from datetime import datetime, timedelta, timezone  # 既に取り込み済みのはず
# from zoneinfo import ZoneInfo  # 既に取り込み済みのはず

def list_posts(conn, status_filter='draft', recent_days=None, media_id=None, preview_tz_override=None):
    """
    投稿を一覧表示する（拡張版）
      - status_filter: 'draft' (default), 'approved', 'posted', 'all'
      - recent_days:   例) 3 を指定すると「直近3日以内（UTC）」で絞り込み
      - media_id:      例) 'hellog' などメディアIDで絞り込み
      - preview_tz_override: 表示タイムゾーンを一時的に上書き（例: 'Asia/Tokyo'）
    """
    # 既定TZの取得（config.json の scheduling.preview_tz）
    _, preview_tz_default = get_tz_prefs()
    preview_tz = preview_tz_override or preview_tz_default

    # WHERE 構築
    where_clauses = []
    params = []

    if status_filter != 'all':
        where_clauses.append("status = ?")
        params.append(status_filter)

    if media_id:
        where_clauses.append("media_id = ?")
        params.append(media_id)

    if recent_days is not None:
        # 直近N日：scheduled_at があるものを対象（NULLは除外）
        cutoff_iso = isoformat_utc(datetime.now(timezone.utc) - timedelta(days=recent_days))
        where_clauses.append("scheduled_at IS NOT NULL AND scheduled_at >= ?")
        params.append(cutoff_iso)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

    query = f"""
        SELECT id, media_id, status, scheduled_at
          FROM posts
          {where_sql}
         ORDER BY COALESCE(scheduled_at, '9999-12-31T23:59:59Z') ASC, id ASC
    """
    rows = conn.execute(query, params).fetchall()

    # 見出し
    head = f"status={status_filter}"
    if media_id: head += f", media={media_id}"
    if recent_days is not None: head += f", recent={recent_days}d"
    head += f", tz={preview_tz}"
    print(f"\n--- 投稿一覧 ({head}) ---")

    if not rows:
        print("該当する投稿がありません。")
        return

    for row in rows:
        post_id = row["id"]
        sched_utc = row["scheduled_at"] or ""
        sched_local = pretty_in_tz(sched_utc, preview_tz) if sched_utc else "-"
        # 最初のスレッドの先頭行を取得（スニペット用）
        thread = conn.execute(
            "SELECT message FROM post_threads WHERE post_id = ? ORDER BY thread_order LIMIT 1",
            (post_id,)
        ).fetchone()
        snippet = (thread["message"].splitlines()[0][:60] + "...") if thread else "(no message)"
        print(
            f"  ID:{post_id:<4} | {row['status']:<9} | {row['media_id']:<15} "
            f"| UTC:{sched_utc:<20} | {preview_tz}:{sched_local} | {snippet}"
        )

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

def manage_image(conn, post_id, thread_order=None):
    """
    任意スレッドの画像を管理する（1本目以外もOK）。
    thread_order が None の場合は一覧表示→選択させる。
    """
    # 投稿の全スレッドを取得（順序付き）
    threads = conn.execute(
        "SELECT id, thread_order, message, image_path FROM post_threads WHERE post_id = ? ORDER BY thread_order",
        (post_id,)
    ).fetchall()
    if not threads:
        print("対象の投稿にスレッドがありません。")
        return

    # スレッド選択 UI（番号未指定のとき）
    target = None
    if thread_order is None:
        print("\n--- 画像管理: スレッド選択 ---")
        for t in threads:
            head = (t["message"] or "").splitlines()[0][:40]
            mark = "📷" if t["image_path"] else "—"
            print(f"  {t['thread_order']:>2}: [{mark}] {head}")
        try:
            thread_order = int(input("画像を操作するスレッド番号を入力: ").strip())
        except Exception:
            print("キャンセルしました。")
            return

    # 指定スレッドを特定
    for t in threads:
        if t["thread_order"] == thread_order:
            target = t
            break
    if not target:
        print(f"指定のスレッド順序 {thread_order} が見つかりません。")
        return

    # この投稿の元リンク（自動スクショ用）。無い場合もある（手動投稿など）
    row = conn.execute(
        """
        SELECT c.link
          FROM posts p
     LEFT JOIN content c ON c.unique_id = p.content_unique_id
         WHERE p.id = ?
        """,
        (post_id,)
    ).fetchone()
    origin_link = row["link"] if row else None

    print(f"\n--- 画像管理 (投稿ID: {post_id}, スレッド: {thread_order}) ---")
    print(f"現在の添付画像: {target['image_path'] or 'なし'}")
    print("操作を選択してください:")
    menu_idx = []
    if origin_link:
        print("  1. スクリーンショットを自動撮影して添付（元リンク）")
        menu_idx.append("1")
    print("  2. ファイルパスを手動で指定して添付")
    print("  3. 添付画像を削除")
    menu_idx.extend(["2", "3"])

    choice = input("> ").strip()
    if choice not in menu_idx:
        print("キャンセルしました。")
        return

    new_image_path = None
    if choice == "1":
        # 自動スクショ（元リンクがある場合のみ）
        from screenshot_util import take_screenshot
        new_image_path = take_screenshot(origin_link)
    elif choice == "2":
        path = input("画像ファイルのパスを入力してください: ").strip().strip('"')
        if not os.path.exists(path):
            print(f"ファイルが見つかりません: {path}")
            return
        new_image_path = path
    elif choice == "3":
        new_image_path = ""

    conn.execute(
        "UPDATE post_threads SET image_path = ? WHERE id = ?",
        (new_image_path or None, target["id"])
    )
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
    list_posts(conn)

    while True:
        print("\n--- コマンド一覧 ---")
        print(" 基本: list | new | view [ID] | approve [ID] | delete [ID] | exit")
        print(" 編集: edit [ID] (単一) | schedule [ID] | image [ID]")
        print(" ｽﾚｯﾄﾞ: add-thread [ID] | edit-thread [ID] [順序] | del-thread [ID] [順序]")

        command_input = input("> ").strip().split()
        if not command_input: continue
        
        cmd = command_input[0]
        
        if cmd == 'exit': break
        # ... while True: の中のコマンド分岐で
        if cmd == 'list':
            # 既定は draft（従来互換）
            status_filter = 'draft'
            recent_days = None
            media_id = None
            tz_override = None
        
            # 例:
            #   list
            #   list approved
            #   list posted
            #   list all
            #   list recent
            #   list media hellog
            #   list media helwa recent --tz Asia/Tokyo
            tokens = command_input[1:]  # 'list' の後ろ
            i = 0
            allowed_status = {'draft', 'approved', 'posted', 'all'}
            while i < len(tokens):
                tok = tokens[i].lower()
        
                if tok in allowed_status:
                    status_filter = tok
                    i += 1
                    continue
        
                if tok == 'recent':
                    recent_days = 3  # ★ 直近3日固定（必要なら 'recent 7' のように拡張可）
                    # recent 指定時は「すべてのステータス」を見たいケースが多いので、
                    # ユーザーが明示しない限り all に寄せる（明示優先）
                    if status_filter == 'draft':
                        status_filter = 'all'
                    i += 1
                    continue
        
                if tok == 'media':
                    if i + 1 >= len(tokens):
                        print("エラー: 'list media' の後に media_id を指定してください（例: hellog）。")
                        break
                    media_id = tokens[i + 1]
                    i += 2
                    continue
        
                if tok == '--tz':
                    if i + 1 >= len(tokens):
                        print("エラー: '--tz' の後にタイムゾーンを指定してください（例: Asia/Tokyo）。")
                        break
                    tz_override = tokens[i + 1]
                    i += 2
                    continue
        
                # それ以外は軽くアラート
                print(f"警告: 未知のオプションを無視しました: {tokens[i]}")
                i += 1
        
            list_posts(conn,
                       status_filter=status_filter,
                       recent_days=recent_days,
                       media_id=media_id,
                       preview_tz_override=tz_override)
            continue
        
        if cmd == 'new':
            new_post(conn)
            list_posts(conn)
            continue
            
        try:
            if cmd in ['view', 'add-thread', 'schedule', 'image', 'approve', 'edit', 'delete']:
                if len(command_input) < 2:
                    raise IndexError("IDが必要です。")
                post_id = command_input[1]
                if cmd == 'view':
                    view_post_details(conn, post_id)
                elif cmd == 'add-thread':
                    add_thread(conn, post_id)
                elif cmd == 'schedule':
                    set_schedule(conn, post_id)
                elif cmd == 'image':
                    # ★ ここを拡張：順序を任意指定可
                    thread_order = int(command_input[2]) if len(command_input) >= 3 else None
                    manage_image(conn, post_id, thread_order)  # ★ 引数追加
                elif cmd == 'approve':
                    approve_post(conn, post_id)
                    print("\n承認後の下書き一覧:")
                    list_posts(conn)
            elif cmd == 'edit':
                edit_post_or_thread(conn, post_id)
            elif cmd == 'delete':
                delete_post(conn, post_id)
                print("\n削除後の下書き一覧:")
                list_posts(conn)

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
