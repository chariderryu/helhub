import os
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
import time

def take_screenshot(url, output_dir='screenshots'):
    """
    指定されたURLのページ全体のスクリーンショットを撮影し、ファイルパスを返す。
    """
    if not url:
        return None

    print(f"'{url}' のフルページスクリーンショットを撮影しています...")

    # スクリーンショットを保存するディレクトリを作成
    os.makedirs(output_dir, exist_ok=True)

    # WebDriverのオプションを設定
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    # 初期ウィンドウサイズは標準的なものに設定
    options.add_argument('window-size=1280,800')

    driver = None
    try:
        # WebDriverを自動でインストール・セットアップ
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        
        # ページにアクセス
        driver.get(url)
        
        # ページが読み込まれるのを待つ
        time.sleep(2)

        # --- ★ 修正点: ページ全体の高さを取得してウィンドウをリサイズ ---
        # JavaScriptを実行してページの完全な高さを取得
        total_height = driver.execute_script("return document.body.scrollHeight")
        
        # ブラウザの高さをページの全高に合わせて設定
        driver.set_window_size(1280, total_height)
        
        # リサイズ後にページが再描画されるのを少し待つ
        time.sleep(2)
        # --- ここまで ---

        # ファイル名を生成
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        filepath = os.path.join(output_dir, filename)
        
        # スクリーンショットを撮影
        driver.save_screenshot(filepath)
        
        print(f"スクリーンショットを '{filepath}' に保存しました。")
        return filepath

    except Exception as e:
        print(f"エラー: スクリーンショットの撮影に失敗しました。 - {e}")
        return None
    finally:
        if driver:
            driver.quit()

if __name__ == '__main__':
    # このスクリプトを直接実行した場合のテストコード
    test_url = "https://www.yahoo.co.jp/" # 縦に長いページでテスト
    print(f"テストとして '{test_url}' のスクリーンショットを撮影します。")
    saved_path = take_screenshot(test_url)
    if saved_path:
        print(f"テスト成功。ファイルは {saved_path} にあります。")
    else:
        print("テスト失敗。")

