# -*- coding: utf-8 -*-
"""
Standalone custom-commands runner.
- 読み込み元: config.json の "custom_commands"
- 使い方:
    python run_custom.py --list
    python run_custom.py hellog:all --show
    python run_custom.py hellog:fetch --arg limit=100
    python run_custom.py hellog:publish --dry-run
"""
import os
import sys
import json
import shlex
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List

# ====== Config ======
DEFAULT_CONFIG = "config.json"

# ====== Utils ======
def load_config(path: str = DEFAULT_CONFIG) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def parse_arg_kv(items: List[str]) -> Dict[str, str]:
    out = {}
    for it in items or []:
        if "=" in it:
            k, v = it.split("=", 1)
            out[k] = v
    return out

def make_ctx(config_path: str, arg_kv: Dict[str, str]) -> Dict[str, Any]:
    repo_root = str(Path(__file__).resolve().parent)
    return {
        "repo_root": repo_root,
        "config_path": str(Path(config_path).resolve()),
        "now_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "arg": arg_kv,
        "env": os.environ,  # 参照用
    }

def _subst_scalar(s: str, ctx: Dict[str, Any]) -> str:
    """{repo_root}, {config_path}, {now_utc}, {arg:key}, {env:NAME} を置換"""
    out = []
    i = 0
    while i < len(s):
        if s[i] == "{":
            j = s.find("}", i + 1)
            if j != -1:
                token = s[i:j+1]  # { ... }
                # {arg:key}
                if token.startswith("{arg:") and token.endswith("}"):
                    key = token[5:-1]
                    out.append(ctx["arg"].get(key, ""))
                    i = j + 1
                    continue
                # {env:NAME}
                if token.startswith("{env:") and token.endswith("}"):
                    key = token[5:-1]
                    out.append(os.environ.get(key, ""))
                    i = j + 1
                    continue
                # {repo_root}, {config_path}, {now_utc}
                key = token.strip("{}")
                if key in ctx:
                    out.append(str(ctx[key]))
                    i = j + 1
                    continue
        out.append(s[i])
        i += 1
    return "".join(out)

def subst(val: Any, ctx: Dict[str, Any]) -> Any:
    if isinstance(val, str):
        return _subst_scalar(val, ctx)
    if isinstance(val, list):
        return [subst(x, ctx) for x in val]
    if isinstance(val, dict):
        return {k: subst(v, ctx) for k, v in val.items()}
    return val

def flatten_steps(name: str, all_cmds: Dict[str, Any], stack=None) -> List[Dict[str, Any]]:
    """steps 内の {"ref": "other:name"} を再帰展開"""
    stack = stack or []
    if name in stack:
        raise RuntimeError(f"ref の循環参照を検出: {' -> '.join(stack + [name])}")
    node = all_cmds.get(name)
    if not node:
        raise KeyError(f"custom_commands['{name}'] が見つかりません")
    out = []
    for s in node.get("steps", []):
        if "ref" in s:
            out.extend(flatten_steps(s["ref"], all_cmds, stack + [name]))
        else:
            out.append(s)
    return out

def run_step(step: Dict[str, Any], ctx: Dict[str, Any], dry_run=False) -> None:
    """1ステップ実行: cmd (list or string), cwd, env, shell, timeout_sec, windows_only"""
    step = subst(step, ctx)
    if "ref" in step:
        return  # 参照は flatten で解決済み

    # OS制約
    if step.get("windows_only") and os.name != "nt":
        print("[custom] skip (windows_only)")
        return

    cmd = step.get("cmd")
    if not cmd:
        return
    shell = bool(step.get("shell", False))
    cwd = step.get("cwd") or ctx["repo_root"]
    timeout = step.get("timeout_sec", None)
    env = os.environ.copy()
    for k, v in (step.get("env") or {}).items():
        env[k] = subst(v, ctx) if isinstance(v, str) else v

    if isinstance(cmd, list) and not shell:
        printable = " ".join(shlex.quote(str(x)) for x in cmd)
        pop = {"args": cmd, "cwd": cwd, "env": env, "timeout": timeout}
    else:
        if isinstance(cmd, list):
            cmd = " ".join(str(x) for x in cmd)
        printable = cmd
        pop = {"args": cmd, "cwd": cwd, "env": env, "shell": True, "timeout": timeout}

    print(f"[custom] RUN: {printable}\n         cwd={cwd} timeout={timeout}")
    if dry_run:
        return

    try:
        cp = subprocess.run(**pop, check=True, text=True, capture_output=True)
        if cp.stdout:
            print(cp.stdout.rstrip())
        if cp.stderr:
            # 一部ツールは進捗をstderrに出すので警告扱いにしない
            sys.stderr.write(cp.stderr)
    except subprocess.CalledProcessError as e:
        print(f"[custom] ERROR (exit={e.returncode})")
        if e.stdout:
            print(e.stdout.rstrip())
        if e.stderr:
            sys.stderr.write(e.stderr)
        raise

# ====== Runner ======
def list_commands(cfg_path: str):
    cfg = load_config(cfg_path)
    cmds = cfg.get("custom_commands", {})
    if not cmds:
        print("(custom_commands が空です)")
        return
    print("== custom commands ==")
    for k, v in cmds.items():
        desc = v.get("description", "")
        print(f" - {k:24s} : {desc}")

def run_command(name: str, args: List[str], cfg_path: str, show=False, dry_run=False):
    cfg = load_config(cfg_path)
    cmds = cfg.get("custom_commands", {})
    if name not in cmds:
        raise SystemExit(f"custom_commands['{name}'] が見つかりません。--list で確認してください。")
    # defaults + --arg 上書き
    defaults = cmds.get(name, {}).get("defaults", {}) or {}
    passed = parse_arg_kv(args)
    ctx = make_ctx(cfg_path, {**defaults, **passed})

    steps = flatten_steps(name, cmds)
    if show or dry_run:
        print(f"== plan: {name} ==")
        for i, s in enumerate(steps, 1):
            s2 = subst(s, ctx)
            print(f"[{i}] cmd={s2.get('cmd')}  cwd={s2.get('cwd', ctx['repo_root'])}  shell={s2.get('shell', False)}")
        if dry_run:
            return

    for s in steps:
        run_step(s, ctx, dry_run=dry_run)

# ====== CLI ======
def main():
    ap = argparse.ArgumentParser(description="Run custom commands defined in config.json")
    ap.add_argument("name", nargs="?", help="custom command name (例: hellog:all)。省略で --list と同等")
    ap.add_argument("--arg", action="append", default=[], help="テンプレ引数（key=value）。複数可")
    ap.add_argument("--config", default=DEFAULT_CONFIG, help="設定ファイルパス（既定: config.json）")
    ap.add_argument("--show", action="store_true", help="解決済みステップを実行前に表示")
    ap.add_argument("--dry-run", action="store_true", help="実行せずプランだけ表示")
    ap.add_argument("--list", action="store_true", help="登録済み custom_commands を一覧表示")
    args = ap.parse_args()

    if args.list or not args.name:
        list_commands(args.config)
        return

    run_command(args.name, args.arg, args.config, show=args.show, dry_run=args.dry_run)

if __name__ == "__main__":
    main()
