import subprocess
import sys
import json
import os
import tempfile
from dotenv import load_dotenv

# .envファイルから環境変数を読み込む
load_dotenv()

def load_config():
    """設定ファイルを読み込む"""
    with open('config.json', 'r', encoding='utf-8') as f:
        return json.load(f)

def run_script(script_name):
    """指定されたPythonスクリプトを実行する"""
    print(f"\n--- '{script_name}' を実行中... ---")
    try:
        result = subprocess.run(
            [sys.executable, script_name], 
            check=True, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            errors='replace'
        )
        print(result.stdout)
        if result.stderr:
            print("--- エラー出力 ---")
            print(result.stderr)
        print(f"--- '{script_name}' の実行完了 ---")
    except subprocess.CalledProcessError as e:
        print(f"エラー: '{script_name}' の実行に失敗しました。")
        print(e.stdout)
        print(e.stderr)
        raise

def upload_via_winscp():
    """WinSCPを使用してファイルをアップロードする（クリーンセッション版）"""
    print("\n--- WinSCPによるファイルアップロードを開始... ---")
    config = load_config()
    settings = config.get('winscp_settings', {})

    winscp_path = settings.get('winscp_executable_path')
    if not winscp_path or not os.path.exists(winscp_path):
        print(f"エラー: config.jsonに指定されたWinSCPの実行ファイルが見つかりません (パス: {winscp_path})。")
        print("アップロードをスキップします。")
        return

    protocol = settings.get('protocol', 'sftp')
    remote_dir = settings.get('remote_directory')
    host = os.getenv('WINSCP_HOST_NAME')
    user = os.getenv('WINSCP_USER_NAME')
    password = os.getenv('WINSCP_PASSWORD')

    if not all([host, user, password, remote_dir]):
        print("エラー: WinSCP設定（ホスト名, ユーザー名, パスワード, リモートディレクトリ）が不足しています。")
        print(".envファイルとconfig.jsonの設定を確認してください。")
        print("アップロードをスキップします。")
        return

    script_dir = os.path.dirname(os.path.abspath(__file__))

    script_content = []
    script_content.append(f'option batch abort')
    script_content.append(f'option confirm off')
    script_content.append(f'lcd "{script_dir}"')
    script_content.append(f'open {protocol}://{user}:{password}@{host}/ -hostkey="*"')

    files_to_upload = ['index.html', 'hel-data.js', 'README.md']
    for file in files_to_upload:
        if os.path.exists(file):
            script_content.append(f'put "{file}" "{remote_dir}"')
        else:
            print(f"警告: アップロード対象のファイル '{file}' が見つかりません。")

    script_content.append('exit')
    
    temp_script_path = ''
    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as temp_script:
            temp_script.write('\n'.join(script_content))
            temp_script_path = temp_script.name

        print("WinSCPコマンドを実行します...")
        
        # ★ 修正点: /ini=nul を追加して、保存済み設定を無視する
        command = [winscp_path, "/ini=nul", f"/script={temp_script_path}", "/log=winscp.log"]
        
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        print("--- WinSCP ログ ---")
        print(result.stdout)
        if result.stderr:
            print("--- WinSCP エラーログ ---")
            print(result.stderr)
        print("--- ファイルアップロード完了 ---")

    except subprocess.CalledProcessError as e:
        print("エラー: WinSCPでのアップロードに失敗しました。")
        print("--- WinSCP ログ (エラー) ---")
        print(e.stdout)
        print(e.stderr)
        print("---")
        print("考えられる原因:")
        print("1. .envファイルのホスト名, ユーザー名, パスワードが間違っている。")
        print("2. サーバー側のファイアウォールで接続が拒否されている。")
        print("3. remote_directoryのパスが間違っている、または書き込み権限がない。")
        
        if os.path.exists('winscp.log'):
            print("\n詳細な接続ログが winscp.log ファイルに出力されています。")
        
        raise
    finally:
        if os.path.exists(temp_script_path):
            os.remove(temp_script_path)

def main():
    """メインの処理"""
    try:
        run_script('fetch_feeds.py')
        run_script('generate_data_js.py')
        upload_via_winscp()
        print("\nすべての更新・アップロード処理が正常に完了しました。")
    except Exception:
        print(f"\n処理が中断されました。エラーログを確認してください。")

if __name__ == '__main__':
    main()

