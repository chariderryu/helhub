# �t�@�C����: run_ffmpeg.ps1
param(
  # Python����n�����^�����ԁi�b�j
  [Parameter(Mandatory=$true)] [int]$DurationSec,
  # Python����n�����o��MP3�t�@�C���̃t���p�X
  [Parameter(Mandatory=$true)] [string]$OutMp3
)

# 3) FFmpeg�ŉ��z�P�[�u���̏o�͂�^������MP3��
#    �f�o�C�X���� `ffmpeg -list_devices true -f dshow -i dummy` �Ŋm�F
$device = 'audio="CABLE Output (VB-Audio Virtual Cable)"'
$ff = "ffmpeg.exe" # ffmpeg.exe��PATH���ʂ��Ă��邱�Ƃ�O��Ƃ��܂�
$mp3args = @(
  "-y",
  "-f","dshow","-i",$device,         # ����=VB-Cable�o��
  "-ac","2","-ar","48000",           # �X�e���I/48k
  "-t",$DurationSec,                 # ���v���ԁi�b�j
  "-c:a","libmp3lame","-b:a","192k", # MP3�G���R�[�h
  $OutMp3
)
# �R���\�[���E�B���h�E��\�������AFFmpeg�̏������I���܂őҋ@���܂�
Start-Process -FilePath $ff -ArgumentList $mp3args -NoNewWindow -Wait
