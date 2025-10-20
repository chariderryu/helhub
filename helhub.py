import argparse
import subprocess
import sys
import os

# 各スクリプトのメイン関数をインポート
from setup_database import setup_database
from fetch_feeds import process_feeds
from generate_data_js import generate_data_js
from manage_posts_cli import main as manage_posts_main # ★ インポート方法を変更
from post_to_x import post_scheduled_tweets
from update_and_upload import main as update_and_upload_main
from generate_newsletter_summary import generate_newsletter_summary

# --- ラッパー関数 ---
# これらは、argparse が引数なしで呼び出せるようにするためのものです。
def run_setup_database(args):
    setup_database()

def run_fetch_feeds(args):
    process_feeds()

def run_generate_data_js(args):
    generate_data_js()

def run_manage_posts(args):
    manage_posts_main() # ★ 呼び出す関数名を変更

def run_post_scheduled_tweets(args):
    post_scheduled_tweets()

def run_update_and_upload(args):
    update_and_upload_main()

def run_generate_newsletter_summary(args):
    generate_newsletter_summary()

def run_custom_hellog_command(args):
    """ユーザー定義のカスタムコマンドを実行するサンプル"""
    # config.jsonからパスを取得するか、ここに直接記述します
    custom_command_path = "C:/bin/hidemaru/Hidemaru.exe"
    
    if not os.path.exists(custom_command_path):
        print(f"エラー: カスタムコマンド '{custom_command_path}' が見つかりません。")
        return

    # 引数を組み立てて実行
    command = [custom_command_path]
    if args.title:
        command.extend(["--title", args.title])
    
    print(f"カスタムコマンドを実行します: {' '.join(command)}")
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError:
        print(f"エラー: '{custom_command_path}' を実行できませんでした。パスを確認してください。")
    except subprocess.CalledProcessError as e:
        print(f"カスタムコマンドの実行に失敗しました: {e}")

def main():
    """コマンドラインインターフェースを定義し、実行するメイン関数"""
    parser = argparse.ArgumentParser(
        description="HEL Hub 自動化・管理ツール",
        formatter_class=argparse.RawTextHelpFormatter
    )
    subparsers = parser.add_subparsers(dest="command", required=True, help="実行するコマンド")

    # init-db コマンド
    parser_init = subparsers.add_parser("init-db", help="データベースを初期化します。")
    parser_init.set_defaults(func=run_setup_database)

    # fetch コマンド
    parser_fetch = subparsers.add_parser(
        "fetch", 
        help="RSSフィードを取得し、正規表現フィルタを適用してDBと投稿下書きを更新します。",
        description=(
            "設定ファイル(config.json)に従って全メディアのRSSフィードを取得します。\n"
            "取得したコンテンツはDBに保存され、'filtering_rules' (正規表現を含む) に基づいて\n"
            "フィルタリングされた後、Xへの投稿下書きが自動で作成されます。"
        ),
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser_fetch.set_defaults(func=run_fetch_feeds)

    # generate-js コマンド
    parser_gen_js = subparsers.add_parser("generate-js", help="DBからウェブサイト用のhel-data.jsを生成します。")
    parser_gen_js.set_defaults(func=run_generate_data_js)

    # update-web コマンド
    parser_update_web = subparsers.add_parser("update-web", help="ウェブサイトの更新とアップロードを全自動で行います。 (fetch -> generate-js -> upload)")
    parser_update_web.set_defaults(func=run_update_and_upload)

    # manage-posts コマンド
    parser_manage = subparsers.add_parser("manage-posts", help="Xへの投稿を下書きの確認、編集、承認、予約など対話形式で管理します。")
    parser_manage.set_defaults(func=run_manage_posts)
    
    # post-now コマンド
    parser_post = subparsers.add_parser("post-now", help="予約日時を過ぎた承認済みの投稿をXへ投稿します。")
    parser_post.set_defaults(func=run_post_scheduled_tweets)

    # generate-news コマンド
    parser_news = subparsers.add_parser("generate-news", help="DBからメルマガ用の原稿(markdown)を生成します。")
    parser_news.set_defaults(func=run_generate_newsletter_summary)

    # hellog カスタムコマンド (サンプル)
    parser_hellog = subparsers.add_parser("hellog", help="hellog関連のカスタムコマンドを実行します。")
    hellog_subparsers = parser_hellog.add_subparsers(dest="hellog_command", required=True)
    parser_hellog_new = hellog_subparsers.add_parser("open", help="hellog をオープンします。")
    parser_hellog_new.add_argument("--title", type=str, help="記事のタイトル")
    parser_hellog.set_defaults(func=run_custom_hellog_command)

    args = parser.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()