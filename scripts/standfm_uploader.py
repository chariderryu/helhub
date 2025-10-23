import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

# --- 設定項目 ---
# 各ファイルパスは、ご自身の環境に合わせて変更してください。
# Windowsのパスは先頭にrを付けるか、\を\\に置き換えてください。
AUDIO_FILE_PATH = r"C:\00work\zEtc\heldio_helwa\heldio_0462.mp3"
IMAGE_FILE_PATH = r"C:\path\to\your\image\462.png" # 放送画像のパスを指定

BROADCAST_TITLE = "#462. Wassail! 健康でいたければ酒を飲め！？"
BROADCAST_DESCRIPTION = "#heldio #英語史 #英語教育 #英語学習 #hel活 #英語史をお茶の間に #古英語"

# 予約設定
SCHEDULE_DATE_OPTION_ID = "react-select-6-option-24" # 例: '25日'のID。日付ごとに変わる可能性あり
SCHEDULE_TIME = "09:30"
# ----------------

# 1. ブラウザを起動し、stand.fmを開く
driver = webdriver.Chrome()
driver.maximize_window()
driver.get("https://stand.fm/")

# 手動でログインを行うための待機時間
input("ブラウザでstand.fmへのログインを完了し、何かキーを押してEnterキーを押してください...")
print("ログインを確認しました。自動操作を開始します。")

try:
    # 2. 右上のアカウントアイコンをクリック
    settings_icon = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="root"]/div/div/div/div/div[1]/div/div[3]/div[3]/div/img'))
    )
    settings_icon.click()
    print("✅ アカウントアイコンをクリックしました。")

    # 3. 「放送の投稿」をクリック
    post_broadcast_link = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//*[@id="root"]/div/div/div/div/div[1]/div/div[4]/div[9]/a/div'))
    )
    post_broadcast_link.click()
    print("✅ 「放送の投稿」をクリックしました。")

    # 4. 音源ファイルをアップロード
    audio_upload_input = WebDriverWait(driver, 15).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="root"]/div/div/div/div/div[2]/div/div[2]/div/div/div/div[2]/div[1]/div[2]/div/input'))
    )
    audio_upload_input.send_keys(AUDIO_FILE_PATH)
    print("✅ 音源ファイルをアップロードしました。")

    # 5. 放送画像をアップロード
    image_upload_input = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.XPATH, '//*[@id="root"]/div/div/div/div/div[2]/div/div[2]/div/div/div/div[2]/div[2]/div[1]/div[2]/input'))
    )
    image_upload_input.send_keys(IMAGE_FILE_PATH)
    print("✅ 放送画像をアップロードしました。")

    # 6. タイトルを入力
    title_input = WebDriverWait(driver, 10).until(
        EC.visibility_of_element_located((By.XPATH, '//*[@id="root"]/div/div/div/div/div[2]/div/div[2]/div/div/div/div[2]/div[3]/div[1]/div[2]/input'))
    )
    title_input.send_keys(BROADCAST_TITLE)
    print("✅ タイトルを入力しました。")

    # 7. 公開範囲を「全員に公開」に設定
    # (デフォルトが「全員に公開」のため、このスクリプトでは操作を省略しますが、必要であればコメントを外してください)
    # driver.find_element(By.XPATH, '...').click()
    # WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, 'react-select-2-option-0'))).click()
    # print("✅ 公開範囲を設定しました。")

    # 8. カテゴリを「ナレッジ・学習」に設定
    driver.find_element(By.XPATH, '//*[@id="root"]/div/div/div/div/div[2]/div/div[2]/div/div/div/div[2]/div[7]/div[2]/div/div').click()
    WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, 'react-select-3-option-1'))).click()
    print("✅ カテゴリを設定しました。")

    # 9. 予約日時を設定
    # 日付を選択
    driver.find_element(By.XPATH, '//*[@id="root"]/div/div/div/div/div[2]/div/div[2]/div/div/div/div[2]/div[8]/div/div[5]').click()
    WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, SCHEDULE_DATE_OPTION_ID))).click()
    
    # 時間を入力
    time_input = driver.find_element(By.XPATH, '//*[@id="root"]/div/div/div/div/div[2]/div/div[2]/div/div/div/div[2]/div[8]/div/input')
    time_input.send_keys(SCHEDULE_TIME)
    print(f"✅ 予約日時を「{SCHEDULE_DATE_OPTION_ID}の{SCHEDULE_TIME}」に設定しました。")

    # 10. 露骨な表現を「いいえ」に設定
    driver.find_element(By.XPATH, '//*[@id="root"]/div/div/div/div/div[2]/div/div[2]/div/div/div/div[2]/div[10]/div[2]/div/div').click()
    WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, 'react-select-7-option-1'))).click()
    print("✅ 露骨な表現を設定しました。")
    
    # 11. 放送の説明を入力
    description_textarea = driver.find_element(By.XPATH, '//*[@id="root"]/div/div/div/div/div[2]/div/div[2]/div/div/div/div[2]/div[11]/div[1]/div[2]/textarea')
    description_textarea.send_keys(BROADCAST_DESCRIPTION)
    print("✅ 放送の説明を入力しました。")

    # 12. 「予約投稿する」ボタンをクリック
    # ページを少し下にスクロールしてボタンを見つけやすくする
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1) # スクロール待機

    submit_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '//div[text()="予約投稿する"]'))
    )
    submit_button.click()
    print("✅ 「予約投稿する」ボタンをクリックしました。")

    # 13. 最終確認ダイアログのボタンをクリック
    confirm_button = WebDriverWait(driver, 10).until(
        EC.element_to_be_clickable((By.XPATH, '/html/body/div[5]/div/div/div/div/div/div[3]/div/div'))
    )
    confirm_button.click()
    print("✅ 最終確認を行い、予約を完了しました。")

    print("\n🎉 すべての処理が正常に完了しました！")

except Exception as e:
    print(f"\nエラーが発生しました: {e}")
    # エラー発生時にスクリーンショットを保存するとデバッグに便利です
    driver.save_screenshot('error_screenshot.png')
    print("エラー発生時のスクリーンショットを'error_screenshot.png'として保存しました。")

finally:
    # 30秒待ってからブラウザを閉じる（確認のため）
    print("30秒後にブラウザを自動的に閉じます。")
    time.sleep(30)
    driver.quit()
