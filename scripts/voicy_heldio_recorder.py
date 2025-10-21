import csv
import re
import subprocess
import argparse
import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def parse_episodes(tsv_file, program_filter, title_prefix):
    """TSVファイルを解析し、すべての対象エピソード情報をリストで返す"""
    episodes = []
    try:
        with open(tsv_file, 'r', encoding='utf-8') as f:
            reader = csv.reader(f, delimiter='\t')
            header = next(reader)
            
            col_map = {h: i for i, h in enumerate(header)}
            required_cols = ["番組", "回", "タイトル", "再生", "再生時間(分)"]
            if not all(col in col_map for col in required_cols):
                print(f"エラー: TSVファイルに必要な列がありません。必要な列: {required_cols}")
                return []

            for row in reader:
                if len(row) < len(header): continue
                
                if row[col_map["番組"]].lower() == program_filter.lower() and \
                   row[col_map["タイトル"]].strip().startswith(title_prefix):
                    try:
                        episodes.append({
                            "episode_num": int(row[col_map["回"]]),
                            "play_link_html": row[col_map["再生"]],
                            "duration_min": int(row[col_map["再生時間(分)"]])
                        })
                    except (ValueError, IndexError):
                        print(f"スキップ:不正な行です -> {row}")
                        continue
    except FileNotFoundError:
        print(f"エラー: TSVファイルが見つかりません: {tsv_file}")
    
    return sorted(episodes, key=lambda x: x["episode_num"])

def record_episode(episode_info, duration_multiplier, output_dir, ps1_script_path):
    """単一のエピソードをブラウザで再生し、PowerShell経由で録音する"""
    url_match = re.search(r"href='(.*?)'", episode_info["play_link_html"])
    if not url_match:
        print(f"URLが見つかりません。スキップします: #{episode_info['episode_num']}")
        return
    url = url_match.group(1)

    record_duration_sec = int(episode_info["duration_min"] * 60 * duration_multiplier)
    output_filename = f"heldio_{episode_info['episode_num']:04d}_to_trim.mp3"
    output_path = os.path.join(output_dir, output_filename)
    
    print("-" * 50)
    print(f"処理開始: heldio #{episode_info['episode_num']}")
    print(f"  URL: {url}")
    print(f"  録音時間: {record_duration_sec}秒")
    print(f"  出力ファイル: {output_path}")

    if os.path.exists(output_path):
        print("  ファイルが既に存在するためスキップします。")
        return

    driver = None
    ps_process = None
    try:
        # 1. ブラウザを起動し、再生ボタンを見つける（まだクリックはしない）
        driver = webdriver.Chrome()
        driver.get(url)
        play_button_xpath = "//button[@aria-label='再生する']"
        print("  再生ボタンを待機中...")
        wait = WebDriverWait(driver, 20)
        play_button = wait.until(EC.element_to_be_clickable((By.XPATH, play_button_xpath)))

        # ========== ここを変更しました！ (録音と再生の順序を逆転) ==========
        # 2. PowerShell経由で録音を先に開始する
        ps_command = [
            "powershell", "-ExecutionPolicy", "Bypass",
            "-File", ps1_script_path,
            "-DurationSec", str(record_duration_sec),
            "-OutMp3", output_path
        ]
        print("  PowerShell経由で録音を開始します...")
        ps_process = subprocess.Popen(ps_command)

        # 3. FFmpegが録音を開始するまで少し待つ
        print("  FFmpegを初期化中...")
        time.sleep(3)  # 3秒待機

        # 4. 録音が始まったのを見計らって再生ボタンをクリック
        print("  再生ボタンをクリックします。")
        play_button.click()
        
        # 5. PowerShellの録音プロセスが完了するのを待つ
        ps_process.wait(timeout=record_duration_sec + 30)
        print(f"  録音完了: {output_path}")
        # =============================================================

    except TimeoutException:
        print("  エラー: 再生ボタンが見つかりませんでした。スキップします。")
    except subprocess.TimeoutExpired:
        print("  エラー: PowerShellスクリプトがタイムアウトしました。")
    except Exception as e:
        print(f"  予期せぬエラーが発生しました: {e}")
    finally:
        # 起動中のプロセスがあれば終了させる
        if ps_process and ps_process.poll() is None:
            ps_process.kill()
        if driver:
            driver.quit()
            print("  ブラウザを閉じました。")

def main():
    parser = argparse.ArgumentParser(description="Voicyのheldio配信回をバッチ録音します。")
    parser.add_argument("--start", type=int, help="録音を開始する配信回の番号。")
    parser.add_argument("--end", type=int, help="録音を終了する配信回の番号。")
    parser.add_argument("--target", type=int, help="指定した単一の配信回のみ録音します。")
    parser.add_argument("--tsv-file", default="C:/00work/OneDrive - keio.jp/zEtc/keioacjp/hellog/hellog-radio/list_heldio.tsv", help="配信一覧のTSVファイルパス。")
    parser.add_argument("--output-dir", default="C:/00work/zEtc/heldio_helwa/", help="MP3ファイルの保存先ディレクトリ。")
    parser.add_argument("--program-filter", default="heldio", help="TSVから抽出する番組名。")
    parser.add_argument("--title-prefix", default="#", help="TSVから抽出するタイトルの接頭辞。")
    parser.add_argument("--duration-multiplier", type=float, default=1.05, help="再生時間に対する録音時間の倍率。")
    parser.add_argument("--ps1-script-path", default="C:/00work/OneDrive - keio.jp/zEtc/keioacjp/helhub/scripts/run_ffmpeg.ps1", help="録音用PowerShellスクリプトのパス。")

    args = parser.parse_args()
    os.makedirs(args.output_dir, exist_ok=True)

    all_episodes = parse_episodes(args.tsv_file, args.program_filter, args.title_prefix)
    if not all_episodes:
        return

    if args.target:
        episodes_to_record = [ep for ep in all_episodes if ep["episode_num"] == args.target]
    else:
        start = args.start if args.start is not None else 0
        end = args.end if args.end is not None else float('inf')
        episodes_to_record = [ep for ep in all_episodes if start <= ep["episode_num"] <= end]

    if not episodes_to_record:
        print("指定された範囲に録音対象のエピソードが見つかりませんでした。")
        return
        
    for episode in episodes_to_record:
        record_episode(episode, args.duration_multiplier, args.output_dir, args.ps1_script_path)
    
    print("-" * 50)
    print("すべての処理が完了しました。")

if __name__ == "__main__":
    main()