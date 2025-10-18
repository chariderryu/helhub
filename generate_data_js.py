import sqlite3
import json
from datetime import datetime, timedelta

def load_config():
    """設定ファイルを読み込む"""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"!!! エラー: 'config.json' が見つからないか、JSONの書式が正しくありません。")
        print(f"詳細: {e}")
        return None

def generate_data_js():
    """config.jsonとDBからデータを取得し、hel-data.jsをゼロから生成する"""
    config = load_config()
    if not config:
        print("config.jsonを読み込めなかったため、処理を中断します。")
        return

    db_path = config.get('database_path', 'content.db')
    
    # 1. config.jsonから静的な骨格を構築
    hel_data = {
        "announcements": config.get("announcements", []),
        "newContent": [],
        "cards": []
    }
    
    # 2. データベースに接続
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 3. 「新着コンテンツ」セクションをDBから生成
    three_days_ago = (datetime.now() - timedelta(days=3)).isoformat()
    cursor.execute("""
        SELECT media_id, title, link FROM content
        WHERE published_date >= ?
        ORDER BY published_date DESC
        LIMIT 5
    """, (three_days_ago,))
    
    for row in cursor.fetchall():
        hel_data['newContent'].append({
            "media": row['media_id'],
            "title": row['title'],
            "url": row['link']
        })

    # 4. config.jsonの各メディア情報からカードを一枚ずつ構築
    for media_id, media_info in config.get('media_templates', {}).items():
        card = {
            "id": media_id,
            "title": media_info.get("title"),
            "shortTitle": media_info.get("shortTitle"),
            "icon": media_info.get("icon"),
            "bgColor": media_info.get("bgColor"),
            "description": media_info.get("description"),
            "link": media_info.get("link"),
            "contentItems": []
        }
        
        # 動的コンテンツをDBから取得 (最新5件)
        cursor.execute("""
            SELECT title, link FROM content
            WHERE media_id = ?
            ORDER BY published_date DESC
            LIMIT 5 
        """, (media_id,))
        
        dynamic_items = [{"title": row['title'], "url": row['link']} for row in cursor.fetchall()]
        
        # 固定コンテンツをconfig.jsonから取得し、isFixedフラグを付与
        fixed_items = []
        for item in media_info.get("fixedContentItems", []):
            fixed_item = item.copy()
            fixed_item["isFixed"] = True
            fixed_items.append(fixed_item)
            
        card["contentItems"] = dynamic_items + fixed_items
        
        hel_data["cards"].append(card)

    conn.close()
    
    # 5. 完成したデータをJavaScriptファイルとして書き出し
    # ★ 修正点: "export" を削除
    js_content = f"const helData = {json.dumps(hel_data, indent=4, ensure_ascii=False)};"
    
    output_filename = 'hel-data.js'
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(js_content)
        
    print(f"'{output_filename}' の生成が完了しました。")

if __name__ == '__main__':
    generate_data_js()

