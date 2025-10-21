# save as: record_voicy.ps1
param(
  [Parameter(Mandatory=$true)] [string]$Url,
  [Parameter(Mandatory=$true)] [int]$DurationSec,
  [Parameter(Mandatory=$true)] [string]$OutMp3
)

# 1) ブラウザでVoicyを開く（Edge例・既定プロファイル/新規Appウィンドウ）
$edge = Start-Process vivaldi.exe "--app=""$Url""" -PassThru
Start-Sleep -Seconds 10

# 2) ページにフォーカスして再生トグル（スペース等）を送る
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("e")
[System.Windows.Forms.SendKeys]::SendWait("ks")

# 3) FFmpegで仮想ケーブルの出力を録音してMP3化
#   デバイス名は `ffmpeg -list_devices true -f dshow -i dummy` で確認
$device = 'audio="CABLE Output (VB-Audio Virtual Cable)"'
$ff = "ffmpeg.exe"
$mp3args = @(
  "-y",
  "-f","dshow","-i",$device,            # 入力=VB-Cable出力
  "-ac","2","-ar","48000",              # ステレオ/48k
  "-t",$DurationSec,                    # 所要時間（秒）
  "-c:a","libmp3lame","-b:a","192k",    # MP3エンコード
  $OutMp3
)
Start-Process -FilePath $ff -ArgumentList $mp3args -NoNewWindow -Wait

# 4) ブラウザ終了
try { $edge.CloseMainWindow() | Out-Null } catch {}
Start-Sleep -Milliseconds 2000
try { Stop-Process -Id $edge.Id -Force } catch {}
