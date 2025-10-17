@echo off
REM このバッチファイルがあるディレクトリに移動
cd /d %~dp0

REM 仮想環境がある場合は、ここで有効化する (例)
REM call .venv\Scripts\activate

echo HEL Hub 自動更新スクリプトを開始します...

REM 統合管理ツール helhub.py を使ってウェブサイトの更新とアップロードを実行
python helhub.py update-web

echo スクリプトの実行が完了しました。
pause

