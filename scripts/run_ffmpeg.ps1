# ファイル名: run_ffmpeg.ps1
param(
  # Pythonから渡される録音時間（秒）
  [Parameter(Mandatory=$true)] [int]$DurationSec,
  # Pythonから渡される出力MP3ファイルのフルパス
  [Parameter(Mandatory=$true)] [string]$OutMp3
)

# 3) FFmpegで仮想ケーブルの出力を録音してMP3化
#    デバイス名は `ffmpeg -list_devices true -f dshow -i dummy` で確認
$device = 'audio="CABLE Output (VB-Audio Virtual Cable)"'
$ff = "ffmpeg.exe" # ffmpeg.exeにPATHが通っていることを前提とします
$mp3args = @(
  "-y",
  "-f","dshow","-i",$device,         # 入力=VB-Cable出力
  "-ac","2","-ar","48000",           # ステレオ/48k
  "-t",$DurationSec,                 # 所要時間（秒）
  "-c:a","libmp3lame","-b:a","192k", # MP3エンコード
  $OutMp3
)
# コンソールウィンドウを表示せず、FFmpegの処理が終わるまで待機します
Start-Process -FilePath $ff -ArgumentList $mp3args -NoNewWindow -Wait
