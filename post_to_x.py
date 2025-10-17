import sqlite3
import json
import tweepy
from datetime import datetime

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

def update_post_status(conn, post_id, status, error_message=None):
    """投稿のステータスを更新する"""
    conn.execute("UPDATE posts SET status = ?, error_message = ? WHERE id = ?", (status, error_message, post_id))
    conn.commit()

def post_scheduled_tweets():
    """予約された投稿を実行する"""
    config = load_config()
    x_config = config.get('x_api_credentials', {})
    
    # APIキーが設定されているかチェック
    if 'YOUR_API_KEY' in x_config.get('api_key', ''):
        print("エラー: config.jsonにXのAPI認証情報が設定されていません。")
        return

    try:
        # Tweepy v2 (OAuth 1.0a)
        auth = tweepy.OAuth1UserHandler(
            x_config['api_key'], x_config['api_key_secret'],
            x_config['access_token'], x_config['access_token_secret']
        )
        api_v1 = tweepy.API(auth)
        
        # Tweepy v2 (OAuth 2.0) - Client for tweet posting
        client = tweepy.Client(
            consumer_key=x_config['api_key'],
            consumer_secret=x_config['api_key_secret'],
            access_token=x_config['access_token'],
            access_token_secret=x_config['access_token_secret']
        )
        print("X APIへの認証に成功しました。")

    except Exception as e:
        print(f"エラー: X APIへの認証に失敗しました。- {e}")
        return

    conn = get_db_connection()
    now = datetime.now().isoformat(timespec='seconds')

    # 投稿すべき投稿を取得
    posts_to_send = conn.execute("""
        SELECT id FROM posts
        WHERE status = 'approved' AND scheduled_at <= ?
        ORDER BY scheduled_at
    """, (now,)).fetchall()

    if not posts_to_send:
        print("現在投稿すべきツイートはありません。")
        conn.close()
        return

    print(f"{len(posts_to_send)}件の投稿を処理します...")

    for post_row in posts_to_send:
        post_id = post_row['id']
        print(f"\n投稿ID: {post_id} を処理中...")

        threads = conn.execute(
            "SELECT * FROM post_threads WHERE post_id = ? ORDER BY thread_order", (post_id,)
        ).fetchall()

        last_tweet_id = None
        try:
            for i, thread in enumerate(threads):
                message = thread['message']
                image_path = thread['image_path']
                media_ids = []
                
                # 画像がある場合はアップロード
                if image_path:
                    try:
                        print(f"  > 画像をアップロード中: {image_path}")
                        media = api_v1.media_upload(filename=image_path)
                        media_ids.append(media.media_id_string)
                        print(f"  > 画像アップロード成功 (Media ID: {media.media_id_string})")
                    except Exception as e:
                        raise Exception(f"画像のアップロードに失敗しました: {e}")

                # ツイートを投稿
                print(f"  > ツイート {i+1}/{len(threads)} を投稿中...")
                
                response = client.create_tweet(
                    text=message,
                    in_reply_to_tweet_id=last_tweet_id,
                    media_ids=media_ids if media_ids else None
                )
                
                new_tweet_id = response.data['id']
                print(f"  > 投稿成功 (Tweet ID: {new_tweet_id})")
                last_tweet_id = new_tweet_id

            # すべて成功したらステータスを更新
            update_post_status(conn, post_id, 'posted')
            print(f"投稿ID: {post_id} の処理が正常に完了しました。")

        except Exception as e:
            error_message = str(e)
            print(f"エラー: 投稿ID {post_id} の処理中にエラーが発生しました。- {error_message}")
            update_post_status(conn, post_id, 'error', error_message)
            
    conn.close()
    print("\nすべての処理が完了しました。")


if __name__ == '__main__':
    post_scheduled_tweets()

