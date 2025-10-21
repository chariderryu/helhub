# normalize_scheduled_at.py
import sqlite3, json
from datetime import datetime, timezone

def parse_utcish(s):
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        # naive は UTC とみなして救済
        dt = dt.replace(tzinfo=timezone.utc)
    return dt

def iso_utc(dt):
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

conn = sqlite3.connect("content.db")
rows = conn.execute("SELECT id, scheduled_at FROM posts WHERE scheduled_at IS NOT NULL").fetchall()
fixed = 0
for _id, s in rows:
    try:
        dt = parse_utcish(s)
        if dt:
            norm = iso_utc(dt)
            if norm != s:
                conn.execute("UPDATE posts SET scheduled_at = ? WHERE id = ?", (norm, _id))
                fixed += 1
    except Exception:
        # 破損データ等はスキップ or ログ
        pass
conn.commit()
print(f"normalized: {fixed}")
