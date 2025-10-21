# save as: record_voicy.ps1
param(
  [Parameter(Mandatory=$true)] [string]$Url,
  [Parameter(Mandatory=$true)] [int]$DurationSec,
  [Parameter(Mandatory=$true)] [string]$OutMp3
)

# 1) �u���E�U��Voicy���J���iEdge��E����v���t�@�C��/�V�KApp�E�B���h�E�j
$edge = Start-Process vivaldi.exe "--app=""$Url""" -PassThru
Start-Sleep -Seconds 10

# 2) �y�[�W�Ƀt�H�[�J�X���čĐ��g�O���i�X�y�[�X���j�𑗂�
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.SendKeys]::SendWait("e")
[System.Windows.Forms.SendKeys]::SendWait("ks")

# 3) FFmpeg�ŉ��z�P�[�u���̏o�͂�^������MP3��
#   �f�o�C�X���� `ffmpeg -list_devices true -f dshow -i dummy` �Ŋm�F
$device = 'audio="CABLE Output (VB-Audio Virtual Cable)"'
$ff = "ffmpeg.exe"
$mp3args = @(
  "-y",
  "-f","dshow","-i",$device,            # ����=VB-Cable�o��
  "-ac","2","-ar","48000",              # �X�e���I/48k
  "-t",$DurationSec,                    # ���v���ԁi�b�j
  "-c:a","libmp3lame","-b:a","192k",    # MP3�G���R�[�h
  $OutMp3
)
Start-Process -FilePath $ff -ArgumentList $mp3args -NoNewWindow -Wait

# 4) �u���E�U�I��
try { $edge.CloseMainWindow() | Out-Null } catch {}
Start-Sleep -Milliseconds 2000
try { Stop-Process -Id $edge.Id -Force } catch {}
