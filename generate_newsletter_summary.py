import sqlite3
import json
from datetime import datetime, timedelta

def load_config():
    """設定ファイルを読み込む"""
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_newsletter_summary():
    """指定された期間の最新コンテンツをまとめたテキストファイルを生成する"""
    config = load_config()
    db_path = config.get('database_path', 'content.db')
    settings = config.get('helmaga_generator', {})
    
    days_to_summarize = settings.get('days_to_summarize', 7)
    output_filename = settings.get('output_filename', 'newsletter_summary.md')
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 集計期間を計算
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days_to_summarize)
    
    # 期間内のコンテンツを媒体ごとに取得
    cursor.execute("""
        SELECT media_id, title, link
        FROM content
        WHERE published_date >= ? AND published_date <= ?
        ORDER BY media_id, published_date DESC
    """, (start_date.isoformat(), end_date.isoformat()))
    
    all_content = cursor.fetchall()
    conn.close()

    if not all_content:
        print(f"過去{days_to_summarize}日間に新しいコンテンツはありませんでした。")
        return

    # 媒体ごとにコンテンツをグループ化
    content_by_media = {}
    for item in all_content:
        media_id = item['media_id']
        if media_id not in content_by_media:
            content_by_media[media_id] = []
        content_by_media[media_id].append(item)

    # Markdown形式でファイルを出力
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(f"# 今週のhel活 ({end_date.strftime('%Y-%m-%d')} 生成)\n")
        f.write(f"（過去{days_to_summarize}日間の新着コンテンツ）\n\n")
        f.write("====================\n\n")
        
        # config.json の media_templates の順序で出力
        for media_id, media_info in config.get('media_templates', {}).items():
            if media_id in content_by_media:
                media_title = media_info.get('title', media_id)
                f.write(f"## ▽ {media_title}\n")
                for item in content_by_media[media_id]:
                    f.write(f"- [{item['title']}]({item['link']})\n")
                f.write("\n")
                
    print(f"メールマガジン原稿 '{output_filename}' の生成が完了しました。")


if __name__ == '__main__':
    generate_newsletter_summary()

