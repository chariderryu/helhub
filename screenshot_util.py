import os
import re
import hashlib
from datetime import datetime
from playwright.sync_api import sync_playwright, Error as PlaywrightError

def _slug_from_url(url: str) -> str:
    """
    URLからユニークなファイル名を生成する。
    例: .../hellog/2025-10-14-1.html -> 'hellog_2025-10-14-1'
    YouTube: .../watch?v=xxxx -> 'youtube_xxxx'
    Voicy: .../channel/123/456 -> 'voicy_456'
    それ以外はURLのハッシュ値を使う。
    """
    # hellog
    m = re.search(r"/hellog/([0-9]{4}-[0-9]{2}-[0-9]{2}-\d+)\.html", url)
    if m:
        return f"hellog_{m.group(1)}"
    
    # YouTube
    m = re.search(r"youtube\.com/watch\?v=([\w-]+)", url)
    if m:
        return f"youtube_{m.group(1)}"
        
    # Voicy
    m = re.search(r"voicy\.jp/channel/\d+/(\d+)", url)
    if m:
        return f"voicy_{m.group(1)}"

    # General fallback
    return "site_" + hashlib.md5(url.encode("utf-8")).hexdigest()[:10]


def take_screenshot(url, output_dir='screenshots'):
    """
    指定されたURLのフルページスクリーンショットを撮影し、ファイルパスを返す（同期API版）。
    """
    if not url:
        return None

    print(f"\n--- スクリーンショット処理開始: {url} ---")
    os.makedirs(output_dir, exist_ok=True)

    slug = _slug_from_url(url)
    filename = f"{slug}.png"
    filepath = os.path.join(output_dir, filename)
    
    if os.path.exists(filepath):
        print(f"キャッシュが見つかりました。既存のファイルを使用します: {filepath}")
        print("--- スクリーンショット処理完了 (キャッシュ) ---\n")
        return filepath

    print("Playwrightを起動しています (同期モード)...")
    try:
        with sync_playwright() as p:
            browser = None
            try:
                browser = p.chromium.launch(
                    args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"]
                )
                context = browser.new_context(
                    viewport={'width': 1280, 'height': 800},
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
                )
                page = context.new_page()

                print(f"ページにアクセス中: {url}")
                page.goto(url, wait_until="networkidle", timeout=60000)
                page.wait_for_timeout(3000)

                print("クッキーバナーを処理しています...")
                cookie_buttons = [
                    page.locator("text=/同意|Accept|OK|承認/i"),
                    page.locator("button:has-text('同意')"),
                    page.locator("button:has-text('Accept all')")
                ]
                for button in cookie_buttons:
                    try:
                        if button.is_visible(timeout=1000):
                            button.click()
                            print("  > 同意ボタンをクリックしました。")
                            page.wait_for_timeout(1000)
                            break
                    except PlaywrightError:
                        pass # タイムアウトなどで見つからない場合は無視
                
                print("フルページスクリーンショットを撮影中...")
                page.screenshot(path=filepath, full_page=True, timeout=30000)

            except PlaywrightError as e:
                print(f"!!! Playwrightでの処理中にエラーが発生しました: {e}")
                # エラーが発生した場合はNoneを返すために再送出
                raise e
            finally:
                if browser:
                    browser.close()
                    print("Playwrightを終了しました。")

        print(f"スクリーンショットを '{filepath}' に保存しました。")
        print("--- スクリーンショット処理完了 ---\n")
        return filepath

    except Exception as e:
        print(f"!!! エラー: スクリーンショットの撮影中に予期せぬエラーが発生しました。")
        print(f"詳細: {e}")
        print("--- スクリーンショット処理失敗 ---\n")
        return None

if __name__ == '__main__':
    test_url = "https://www.youtube.com/watch?v=6WmcXHbbwmM"
    print(f"テストとして '{test_url}' のスクリーンショットを撮影します。")
    
    saved_path = take_screenshot(test_url)
    
    if saved_path:
        print(f"テスト成功。ファイルは {os.path.abspath(saved_path)} にあります。")
    else:
        print("テスト失敗。")

