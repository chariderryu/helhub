#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
record_voicy.py (Selenium強化版)
- TSV対応 / タイトル正規表現 / 範囲バッチ / URL直指定
- Seleniumで再生: クリック → JS play() → キー送信、かつ再生状態(paused=false)確認
- ブラウザ選択: chrome / edge, もしくは --browser-binary で Vivaldi 等のChromium系を指定
- ウィンドウ形態: --as-app（既定ON）/ --no-as-app（通常タブ）
- 終了挙動: 既定は録音後に閉じる。--no-close-browser で閉じない / --keep-browser-on-error で失敗時も残す
- 録音: ffmpeg（dshow または wasapi） + VB-CABLE
- 録音前ウェイト: --pre-wait-sec（既定1.0s）
- 録音後: 任意の無音自動分割（pydub）
- TSVの「再生」は <a href="..."> に対応 / 「再生時間(分)」→秒に換算し係数を掛ける (--duration-mult)
"""

import argparse, csv, os, re, subprocess, sys, time, math
from typing import Dict, List, Optional, Tuple

FFMPEG_DEFAULT = r"ffmpeg.exe"
DEVICE_DEFAULT = r'CABLE Output (VB-Audio Virtual Cable)'

# ---------------- TSV/ユーティリティ ----------------

def norm_key(s: str) -> str:
    return re.sub(r"\s+", "", s.strip().lower())

def parse_duration_to_seconds(text: str) -> int:
    t = str(text).strip()
    if not t:
        raise ValueError("duration が空です")
    if t.isdigit():
        return int(t)
    parts = t.split(":")
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + int(s)
    if len(parts) == 3:
        h, m, s = parts
        return int(h) * 3600 + int(m) * 60 + int(s)
    raise ValueError("対応外のduration形式: " + text)

def sanitize_filename(name: str, maxlen: int = 80) -> str:
    invalid = r'<>:"/\\|?*'
    for ch in invalid:
        name = name.replace(ch, "_")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:maxlen]

def guess_number_from_title(title: str) -> Optional[int]:
    m = re.match(r"^\s*#\s*(\d+)", title or "", flags=re.IGNORECASE)
    return int(m.group(1)) if m else None

def load_tsv(path: str, encoding: str = "utf-8") -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    with open(path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f, delimiter="\t")
        for r in reader:
            if any(v for v in r.values()) and not str(list(r.values())[0]).lstrip().startswith("#"):
                rows.append({k: (v or "").strip() for k, v in r.items()})
    return rows

def pick_field(row: Dict[str, str], candidates: List[str]) -> Optional[str]:
    mapping = {norm_key(k): k for k in row.keys()}
    for c in candidates:
        key = mapping.get(norm_key(c))
        if key and row.get(key):
            return row[key].strip()
    return None

def extract_href(url_field: str) -> Optional[str]:
    if not url_field:
        return None
    s = url_field.strip()
    if s.startswith("http://") or s.startswith("https://"):
        return s
    m = re.search(r'href\s*=\s*["\\\']([^"\\\']+)["\\\']', s, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    m2 = re.search(r'(https?://[^\s"\']+)', s)
    if m2:
        return m2.group(1)
    return None

def parse_duration_from_row(row: Dict[str, str]) -> Optional[int]:
    min_fields = ["再生時間(分)", "分", "minutes", "mins", "min"]
    for key in row.keys():
        nk = norm_key(key)
        for cand in min_fields:
            if nk == norm_key(cand) and row.get(key):
                try:
                    minutes = float(str(row[key]).strip())
                    return int(round(minutes * 60))
                except Exception:
                    pass
    text = pick_field(row, ["duration", "長さ", "再生時間", "time", "length", "duration_sec"])
    if text:
        try:
            return parse_duration_to_seconds(text)
        except Exception:
            return None
    return None

def extract_fields(row: Dict[str, str]):
    title = pick_field(row, ["タイトル", "title"]) or ""
    play_field = pick_field(row, ["再生", "url", "URL", "リンク"]) or ""
    url = extract_href(play_field)
    if not url:
        raise ValueError("URL/再生 フィールドからリンクを抽出できません。")
    dur_sec = parse_duration_from_row(row)
    duration_text = str(dur_sec) if dur_sec is not None else None
    explicit_out = pick_field(row, ["out_mp3", "出力", "ファイル名"])
    num_text = pick_field(row, ["number", "No", "通し番号"])
    number = int(num_text) if (num_text and str(num_text).isdigit()) else guess_number_from_title(title)
    return number, title, url, duration_text, explicit_out

def build_out_path(out_dir: Optional[str], number: Optional[int], title: str, explicit: Optional[str]) -> str:
    if explicit: return explicit
    stem = f"heldio_{number:04d}" if number is not None else sanitize_filename(title or "heldio")
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        return os.path.join(out_dir, f"{stem}.mp3")
    return f"{stem}.mp3"

def select_rows(rows, number, range_spec, title_regex):
    rx = re.compile(title_regex, re.IGNORECASE) if title_regex else re.compile(r'^\s*#\s*\d+', re.IGNORECASE)
    filtered = [r for r in rows if rx.search(pick_field(r, ["タイトル", "title"]) or "")]
    if number is not None or range_spec:
        res = []
        start = end = None
        if range_spec:
            m = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", range_spec)
            if not m: raise ValueError("--range は 431-440 の形式で指定してください。")
            start, end = int(m.group(1)), int(m.group(2))
            if start > end: start, end = end, start
        for r in filtered:
            n, title, url, dur, explicit = extract_fields(r)
            if number is not None:
                if n == number: res.append(r)
            else:
                if n is not None and start <= n <= end: res.append(r)
        return res
    return filtered

# ---------------- Selenium：再生開始 ----------------

def make_driver(url: str, browser: str, binary: Optional[str], as_app: bool, autoplay_policy: bool, driver_path: Optional[str]):
    from selenium import webdriver
    if browser.lower() == "edge":
        from selenium.webdriver.edge.options import Options as EdgeOptions
        opts = EdgeOptions()
        if as_app:
            opts.add_argument(f"--app={url}")
        else:
            opts.add_argument("--start-maximized")
        if autoplay_policy:
            opts.add_argument("--autoplay-policy=no-user-gesture-required")
        return webdriver.Edge(executable_path=driver_path, options=opts) if driver_path else webdriver.Edge(options=opts)
    else:
        from selenium.webdriver.chrome.options import Options as ChromeOptions
        opts = ChromeOptions()
        if binary:
            opts.binary_location = binary  # 例: C:\Program Files\Vivaldi\Application\vivaldi.exe
        if as_app:
            opts.add_argument(f"--app={url}")
        else:
            opts.add_argument("--start-maximized")
        if autoplay_policy:
            opts.add_argument("--autoplay-policy=no-user-gesture-required")
        return webdriver.Chrome(executable_path=driver_path, options=opts) if driver_path else webdriver.Chrome(options=opts)

def open_and_start_play(url: str, browser: str = "chrome", binary: Optional[str] = None,
                        driver_path: Optional[str] = None, click_timeout: float = 12.0,
                        autoplay_policy: bool = True, as_app: bool = True, log_prefix: str = ""):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    driver = make_driver(url, browser, binary, as_app, autoplay_policy, driver_path)
    wait = WebDriverWait(driver, click_timeout)

    def navigate_if_needed():
        if not as_app:
            driver.get(url)

    def safe_click_cookie():
        try:
            for xp in [
                "//button[contains(., '同意') or contains(., '同意する') or contains(., 'Accept')]",
                "//div[contains(., 'Cookie')]/following::button[1]",
            ]:
                for btn in driver.find_elements(By.XPATH, xp):
                    try: btn.click(); time.sleep(0.2); break
                    except: pass
        except: pass

    def try_click_play_button():
        selectors = [
            (By.XPATH, "//button[contains(@aria-label, '再生') or contains(., '再生')]"),
            (By.XPATH, "//button[contains(@data-testid, 'play')]"),
            (By.CSS_SELECTOR, "button[aria-label*='再生']"),
            (By.XPATH, "//button//*[name()='svg' and contains(@aria-label,'play')]/ancestor::button[1]"),
        ]
        for by, sel in selectors:
            try:
                el = wait.until(EC.element_to_be_clickable((by, sel)))
                el.click(); return True
            except Exception:
                continue
        return False

    def try_js_play():
        try:
            played = driver.execute_script("""
                let any=false;
                const media=[...document.querySelectorAll('audio,video')];
                for (const m of media){ try{ m.muted=false; m.play(); any=true; }catch(e){} }
                return any;
            """)
            return bool(played)
        except Exception:
            return False

    def try_keys():
        try:
            body = driver.find_element(By.TAG_NAME, "body")
            body.send_keys(Keys.SPACE); time.sleep(0.4); body.send_keys("k"); return True
        except Exception:
            return False

    def is_playing():
        try:
            return bool(driver.execute_script("""
                const media=[...document.querySelectorAll('audio,video')];
                return media.some(m => m.readyState>0 && m.paused===false);
            """))
        except Exception:
            return False

    # 実処理
    navigate_if_needed()
    time.sleep(1.0)
    safe_click_cookie()

    ok = try_click_play_button() or try_js_play() or try_keys()
    # 再生状態を最大3秒ほど確認
    t0 = time.time()
    while time.time() - t0 < 3.0:
        if is_playing():
            print(f"{log_prefix}[selenium] playing confirmed")
            break
        time.sleep(0.25)
    else:
        print(f"{log_prefix}[selenium] playing not confirmed (続行します)")

    return driver

# ---------------- ffmpeg 録音 ----------------

def list_devices(ffmpeg_path: str, api: str):
    if api == "dshow":
        cmd = [ffmpeg_path, "-hide_banner", "-f", "dshow", "-list_devices", "true", "-i", "dummy"]
    else:
        cmd = [ffmpeg_path, "-hide_banner", "-f", "wasapi", "-list_devices", "true", "-i", "dummy"]
    print(" ".join(cmd))
    subprocess.run(cmd)

def run_ffmpeg_record(api: str, device_name: str, out_mp3: str, duration_sec: int, ffmpeg_path: str,
                      samplerate: int = 48000, bitrate: str = "192k") -> int:
    if api == "dshow":
        device_arg = f'audio="{device_name}"'
        args = [
            ffmpeg_path, "-y",
            "-f", "dshow", "-i", device_arg,
            "-ac", "2", "-ar", str(samplerate),
            "-t", str(int(duration_sec)),
            "-c:a", "libmp3lame", "-b:a", bitrate,
            out_mp3
        ]
    else:
        args = [
            ffmpeg_path, "-y",
            "-f", "wasapi", "-i", f"{device_name}",
            "-ac", "2", "-ar", str(samplerate),
            "-t", str(int(duration_sec)),
            "-c:a", "libmp3lame", "-b:a", bitrate,
            out_mp3
        ]
    print("[ffmpeg] " + " ".join(args))
    return subprocess.run(args).returncode

def close_driver(driver, should_close: bool):
    try:
        if should_close:
            driver.quit()
    except Exception:
        pass

# ---------------- サイレンス分割（任意） ----------------

def split_on_silence_postproc(in_mp3: str, out_prefix: Optional[str],
                              min_silence: float, pad: float,
                              thresh: Optional[float], bitrate: str,
                              min_audio: float, merge_gap: float) -> int:
    try:
        from pydub import AudioSegment
        from pydub.silence import detect_silence
        import numpy as np  # noqa
    except Exception as e:
        print("[warn] pydub/numpy 未導入のため分割をスキップします:", e); return 0
    audio = AudioSegment.from_file(in_mp3)
    dur_ms = len(audio)
    ms = int(max(0.0, min_silence) * 1000)
    pad_ms = int(max(0.0, pad) * 1000)
    min_audio_ms = int(max(0.0, min_audio) * 1000)
    merge_gap_ms = int(max(0.0, merge_gap) * 1000)
    if thresh is None:
        est = audio.dBFS + 4.0; silence_thresh = max(min(est, -18.0), -40.0)
        print(f"[split] auto threshold ≈ {silence_thresh:.1f} dBFS")
    else:
        silence_thresh = float(thresh); print(f"[split] threshold = {silence_thresh:.1f} dBFS")
    silent_ranges = detect_silence(audio, min_silence_len=ms, silence_thresh=silence_thresh)
    if silent_ranges:
        silent_ranges.sort(); merged = [list(silent_ranges[0])]
        for s, e in silent_ranges[1:]:
            if s - merged[-1][1] <= merge_gap_ms: merged[-1][1] = max(merged[-1][1], e)
            else: merged.append([s, e])
        silent_ranges = [tuple(x) for x in merged]
    segments = []; cursor = 0
    for s, e in silent_ranges:
        if s - cursor >= min_audio_ms:
            start = max(0, cursor - pad_ms); end = min(dur_ms, s + pad_ms)
            if end > start: segments.append((start, end))
        cursor = e
    if dur_ms - cursor >= min_audio_ms:
        start = max(0, cursor - pad_ms); end = dur_ms
        if end > start: segments.append((start, end))
    if not segments:
        print("[split] 対象となる無音が見つからず、分割しません。"); return 0
    if out_prefix is None:
        stem, _ = os.path.splitext(in_mp3); out_prefix = stem
    base_dir = os.path.dirname(out_prefix)
    if base_dir and not os.path.exists(base_dir): os.makedirs(base_dir, exist_ok=True)
    count = 0
    for i, (s, e) in enumerate(segments, start=1):
        chunk = audio[s:e]; out_path = f"{out_prefix}_{i:02d}.mp3"
        chunk.export(out_path, format="mp3", bitrate=bitrate)
        print(f"[split] wrote: {out_path}  [{s/1000:.2f}s → {e/1000:.2f}s]"); count += 1
    return count

# ---------------- 実行本体 ----------------

def process_one(url: str, duration_sec: int, out_mp3: str,
                browser: str, browser_binary: Optional[str], as_app: bool, driver_path: Optional[str],
                click_timeout: float, pre_wait_sec: float,
                ffmpeg_path: str, api: str, device_name: str, bitrate: str,
                do_split: bool, split_prefix: Optional[str],
                silence_min: float, silence_pad: float,
                silence_thresh: Optional[float], silence_min_audio: float,
                silence_merge_gap: float,
                close_browser: bool, keep_browser_on_error: bool) -> bool:
    print(f"[run] URL={url}  duration={duration_sec}s  out={out_mp3}  browser={browser} as_app={as_app}")
    driver = open_and_start_play(url, browser=browser, binary=browser_binary,
                                 driver_path=driver_path, click_timeout=click_timeout,
                                 autoplay_policy=True, as_app=as_app, log_prefix="[job] ")
    try:
        # 再生が走っていても少し待ってから録音開始（サイト側の遅延対策）
        time.sleep(max(0.0, pre_wait_sec))
        ret = run_ffmpeg_record(api, device_name, out_mp3, duration_sec, ffmpeg_path, bitrate=bitrate)
        ok = (ret == 0 and os.path.exists(out_mp3) and os.path.getsize(out_mp3) > 0)
        print(f"[ffmpeg] exit={ret} ok={ok}")
        if ok and do_split:
            print("[split] 録音後のサイレンス自動分割を実行します…")
            try:
                n = split_on_silence_postproc(out_mp3, split_prefix, silence_min, silence_pad,
                                              silence_thresh, bitrate, silence_min_audio, silence_merge_gap)
                print(f"[split] segments={n}")
            except Exception as e:
                print("[warn] 分割処理でエラー:", e)
        return ok
    finally:
        should_close = (close_browser if (ok or not keep_browser_on_error) else False)
        close_driver(driver, should_close)

def main():
    ap = argparse.ArgumentParser(description="VoicyをSeleniumで再生→ffmpeg録音→(任意)無音分割。Vivaldi・dshow/wasapi対応。")
    g_src = ap.add_mutually_exclusive_group(required=False)
    g_src.add_argument("--url", help="エピソードURLを直接指定（--duration-sec と --out が必要）")
    g_src.add_argument("--tsv", help="一覧TSV（ヘッダ付きを推奨）")

    ap.add_argument("--tsv-encoding", default="utf-8")
    ap.add_argument("--title-regex", default=r'^\s*#\s*\d+')
    ap.add_argument("--number", type=int)
    ap.add_argument("--range")

    ap.add_argument("--duration-sec", type=int)
    ap.add_argument("--out")
    ap.add_argument("--out-dir")

    # ブラウザ / Selenium
    ap.add_argument("--browser", choices=["chrome", "edge"], default="chrome", help="Selenium用ブラウザ種別")
    ap.add_argument("--browser-binary", help="Chromium系ブラウザの実行ファイル（例: Vivaldi の vivaldi.exe）")
    ap.add_argument("--driver-path", help="chromedriver/msedgedriver のパス（未指定ならSelenium Manager）")
    ap.add_argument("--as-app", dest="as_app", action="store_true", help="--app=URL のアプリウィンドウで開く（既定）")
    ap.add_argument("--no-as-app", dest="as_app", action="store_false", help="通常ウィンドウ+タブで開く")
    ap.set_defaults(as_app=True)
    ap.add_argument("--click-timeout", type=float, default=12.0, help="再生クリックなどの待機秒数")
    ap.add_argument("--pre-wait-sec", type=float, default=1.0, help="再生開始後、録音前の待機秒数")

    # ffmpeg / デバイス / API
    ap.add_argument("--api", choices=["dshow", "wasapi"], default="dshow", help="音声キャプチャAPI（WASAPI非対応ビルドならdshow）")
    ap.add_argument("--ffmpeg", default=FFMPEG_DEFAULT)
    ap.add_argument("--device", default=DEVICE_DEFAULT, help="録音デバイス表示名（列挙結果と完全一致）")
    ap.add_argument("--bitrate", default="192k")
    ap.add_argument("--list-devices", action="store_true", help="選択APIでデバイス一覧を表示して終了")

    # 録音後のサイレンス分割（任意、デフォルトOFF）
    ap.add_argument("--split-on-silence", action="store_true")
    ap.add_argument("--split-prefix")
    ap.add_argument("--silence-min", type=float, default=5.0)
    ap.add_argument("--silence-pad", type=float, default=0.15)
    ap.add_argument("--silence-thresh", type=float, default=None)
    ap.add_argument("--silence-min-audio", type=float, default=1.0)
    ap.add_argument("--silence-merge-gap", type=float, default=0.5)

    # その他
    ap.add_argument("--duration-mult", type=float, default=1.1, help="録音時間に掛ける係数（既定 1.1）")
    ap.add_argument("--no-close-browser", dest="close_browser", action="store_false", help="録音後にブラウザを閉じない（デバッグ用）")
    ap.add_argument("--keep-browser-on-error", action="store_true", help="失敗時もブラウザを閉じない（デバッグ用）")
    ap.add_argument("--dry-run", action="store_true")

    args = ap.parse_args()

    if args.list_devices:
        list_devices(args.ffmpeg, args.api); return

    jobs: List[Tuple[str, int, str]] = []

    if args.url:
        if args.duration_sec is None or not args.out:
            ap.error("--url を使う場合は --duration-sec と --out が必要です。")
        jobs.append((args.url, int(math.ceil(args.duration_sec * args.duration_mult)), args.out))
    elif args.tsv:
        rows = load_tsv(args.tsv, encoding=args.tsv_encoding)
        picked = select_rows(rows, args.number, args.range, args.title_regex)
        if not picked:
            print("[error] TSVから対象が見つかりませんでした。", file=sys.stderr); sys.exit(2)
        for r in picked:
            try:
                number, title, url, duration_text, explicit_out = extract_fields(r)
            except Exception as e:
                print("[warn] スキップ（必須フィールド不足）:", e); continue
            if not duration_text:
                print(f"[warn] duration が無い行をスキップ: title={title}"); continue
            try:
                duration_sec = parse_duration_to_seconds(duration_text)
            except Exception as e:
                print(f"[warn] duration解析失敗のためスキップ: {duration_text} ({e})"); continue
            out_mp3 = build_out_path(args.out_dir, number, title, explicit_out)
            jobs.append((url, int(math.ceil(duration_sec * args.duration_mult)), out_mp3))
    else:
        ap.error("--url か --tsv のいずれかを指定してください。")

    for (url, dur, outp) in jobs:
        print("="*72)
        print(f"[job] URL={url}")
        print(f"[job] duration={dur}s  out={outp}")
        if args.dry_run:
            print("[dry-run] 録音は行いません。"); continue
        ok = process_one(
            url, dur, outp,
            browser=args.browser, browser_binary=args.browser_binary, as_app=args.as_app,
            driver_path=args.driver_path, click_timeout=args.click_timeout, pre_wait_sec=args.pre_wait_sec,
            ffmpeg_path=args.ffmpeg, api=args.api, device_name=args.device, bitrate=args.bitrate,
            do_split=args.split_on_silence, split_prefix=args.split_prefix,
            silence_min=args.silence_min, silence_pad=args.silence_pad,
            silence_thresh=args.silence_thresh, silence_min_audio=args.silence_min_audio,
            silence_merge_gap=args.silence_merge_gap,
            close_browser=args.close_browser,              # ← ここが “args.close_browser”
            keep_browser_on_error=args.keep_browser_on_error
        )
        if not ok:
            print("[warn] 失敗の可能性があります。ログをご確認ください。")

if __name__ == "__main__":
    if os.name != "nt":
        print("This script is intended for Windows.", file=sys.stderr)
    main()
