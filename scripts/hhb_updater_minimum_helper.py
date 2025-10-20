from datetime import datetime
import re

# 元スクリプトのファイルパス
SCRIPT_PATH = "hellog_uploader_minimum.winscpscript"

# 今日の日付を "YYYY-MM-DD" 形式で取得
today_str = datetime.now().strftime("%Y-%m-%d")

# 日付付きファイル名を見つけるための正規表現パターン
pattern = re.compile(r"\d{4}-\d{2}-\d{2}(-1)?\.html")

# ファイルを読み込んで行ごとに処理
with open(SCRIPT_PATH, "r", encoding="utf-8") as f:
    lines = f.readlines()

# 5行目と6行目（インデックス4と5）の日付を置換
for i in [4, 5]:
    lines[i] = re.sub(pattern,
                      lambda m: f"{today_str}{m.group(1) or ''}.html",
                      lines[i])

# 上書き保存
with open(SCRIPT_PATH, "w", encoding="utf-8") as f:
    f.writelines(lines)

print(f"? {SCRIPT_PATH} の日付を {today_str} に更新しました。")
