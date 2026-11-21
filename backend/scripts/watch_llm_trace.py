#!/usr/bin/env python3
"""持续监控 data/llm-trace.jsonl，实时格式化输出新增记录。

用法（在 backend 目录下）：
    python3 scripts/watch_llm_trace.py              # 只看新写入的记录（类似 tail -f）
    python3 scripts/watch_llm_trace.py --from-start # 先打印历史，再持续跟进
    python3 scripts/watch_llm_trace.py --kind chat_request --grep 高考
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

SEP = "=" * 80


def render(line: str, grep: str | None, brief: bool = False) -> str | None:
    line = line.strip()
    if not line:
        return None
    if grep and grep not in line:
        return None
    try:
        record = json.loads(line)
    except json.JSONDecodeError:
        # 写入过程中被截断，或格式异常
        return f"[无法解析的行] {line[:200]}"

    head = "{ts} {kind} {rid} attempt={attempt}".format(
        ts=record.get("timestamp", "-"),
        kind=record.get("kind", "-"),
        rid=record.get("request_id", "-"),
        attempt=record.get("attempt", "-"),
    )
    if brief:
        payload = json.dumps(record.get("payload"), ensure_ascii=False)
        if len(payload) > 200:
            payload = payload[:200] + "…"
        return f"{head}\n    {payload}"
    payload = json.dumps(record.get("payload"), ensure_ascii=False, indent=2)
    return f"{SEP}\n{head}\n{payload}"


def main() -> int:
    default_file = Path(__file__).resolve().parent.parent / "data" / "llm-trace.jsonl"
    parser = argparse.ArgumentParser(description="持续监控 llm-trace.jsonl")
    parser.add_argument("--file", default=str(default_file), help="trace 文件路径")
    parser.add_argument("--from-start", action="store_true", help="先输出已有内容")
    parser.add_argument("--interval", type=float, default=0.5, help="轮询间隔秒数")
    parser.add_argument("--kind", default=None, help="只显示指定 kind 的记录")
    parser.add_argument("--grep", default=None, help="只显示包含该字符串的记录")
    parser.add_argument("--brief", action="store_true", help="每条记录只打一行摘要")
    args = parser.parse_args()

    path = Path(args.file)
    if args.kind:
        kind_filter = args.kind
    else:
        kind_filter = None

    file = None
    inode = None
    pos = 0
    buf = ""

    while True:
        try:
            stat = os.stat(path)
        except FileNotFoundError:
            # 文件还没生成，等它出现
            time.sleep(args.interval)
            continue

        # 新文件、被轮转（inode 变化）或被截断（变小）都要重新打开
        if file is None or stat.st_ino != inode or stat.st_size < pos:
            if file is not None:
                file.close()
            # 用二进制打开，保证 pos 与 st_size 是同一套字节坐标
            file = open(path, "rb")
            inode = stat.st_ino
            buf = ""
            if args.from_start:
                pos = 0
            else:
                pos = stat.st_size
                file.seek(pos)
            print(f"[watch] {path} (inode={inode}, 起点={pos})", flush=True)

        chunk = file.read()
        if not chunk:
            time.sleep(args.interval)
            continue

        pos += len(chunk)
        buf += chunk.decode("utf-8", errors="replace")
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            if kind_filter and kind_filter not in line:
                continue
            out = render(line, args.grep, args.brief)
            if out:
                print(out, flush=True)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[watch] 已停止", flush=True)
        sys.exit(0)
