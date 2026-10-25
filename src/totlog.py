#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
totlog — The Outlast Trials 本机日志复盘分析器

只读 %LOCALAPPDATA%\\OPP\\Saved\\Logs\\*.log，不碰游戏进程、不碰内存、不改任何文件。
用途：把一局/一天的日志变成结构化统计（场次、时长、地图、区域、掉线、EAC 会话健康度）。

用法：
    python totlog.py report                  # 分析默认目录下所有日志
    python totlog.py report -f OPP.log       # 只分析指定文件
    python totlog.py report --json out.json --md out.md
    python totlog.py sessions                # 只看场次时间线
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Iterable

# 日志时间戳是 UTC；True 表示输出转本地时区（--utc 可关掉）
TZ_TO_LOCAL = True

# 导出时是否把用户名替换成 %USERPROFILE%（--no-redact 可关掉）
REDACT = True

# ---------------------------------------------------------------------------
# 日志行格式
# ---------------------------------------------------------------------------
# [2026.10.17-11.20.43:023][378]LogCategory: Level: message
# 时间戳格式固定为 YYYY.MM.DD-HH.MM.SS:mmm，方括号里第二段是帧号。
LINE_RE = re.compile(
    r"^\[(?P<ts>\d{4}\.\d{2}\.\d{2}-\d{2}\.\d{2}\.\d{2}:\d{3})\]"
    r"\[(?P<frame>[ \d]+)\]"
    r"(?P<cat>[A-Za-z0-9_]+):\s?"
    r"(?P<body>.*)$"
)

# 同一行里的等级前缀：Display: / Warning: / Error: / Log: / Verbose:
LEVEL_RE = re.compile(r"^(Display|Warning|Error|Log|Verbose|Fatal):\s?")

# 地图加载：RB:  >>> /Game/Maps/Resort/RE_LD_T1_B1
# 注意：>>> 是 streaming 子关卡（一个大地图会爆几百条），不是"关卡切换"。
MAP_STREAM_RE = re.compile(r">>>\s+(/Game/Maps/[A-Za-z0-9_/\.\-]+)")

# 真正的关卡切换：LogNet: Browse: /Game/Maps/Resort/Resort_Persistent?Name=Player
MAP_BROWSE_RE = re.compile(r"Browse:\s+(/Game/Maps/[A-Za-z0-9_/\.\-]+)")

# 玩家出生点：RB:  [local] BeginPlay - LastValidFloorLocation (X=562.2, Y=-1492.8, Z=387.2)
FLOOR_RE = re.compile(
    r"\[(?P<who>[^\]]+)\]\s+BeginPlay\s+-\s+LastValidFloorLocation\s+"
    r"\(X=(?P<x>-?[\d.]+),\s*Y=(?P<y>-?[\d.]+),\s*Z=(?P<z>-?[\d.]+)\)"
)

# EAC 会话
EAC_BEGIN_RE = re.compile(r"EOS_AntiCheatClient_BeginSession\s+(?P<res>SUCCESS|FAILURE)")
EAC_END_RE = re.compile(r"EOS_AntiCheatClient_EndSession\s+(?P<res>SUCCESS|FAILURE)")
EAC_MODE_RE = re.compile(r"\[BeginSession-\d+\]\s+Mode:\s*(?P<mode>\d+)")

# 引擎/构建：注意这两个前缀后面跟的是 "." 不是 ":"，别用通用的 cat: 解析
# [2026.10.13-17.07.31:001][  0]LogInit: Build: release-7-1-CL-260801
# [2026.10.13-17.07.31:001][  0]LogInit: Engine Version: 4.27.1-260801+release-7-1
BUILD_RE = re.compile(r"LogInit[:\.]\s*Build:\s+(?P<v>\S+)")
ENGINE_RE = re.compile(r"LogInit[:\.]\s*Engine Version:\s+(?P<v>\S+)")

# 服务器区域
REGION_LIST_RE = re.compile(r"Region:\s+\[(?P<r>[a-z0-9\-]+)\]\s+\((?P<dc>\d+)\s+datacenters?\)")
AUTOREGION_RE = re.compile(r"AutoRegion\s+(?P<r>[a-z0-9\-]+):\s+(?P<dc>\d+)\s+datacenters?")

# 对局内事件
ITEM_EQUIP_RE = re.compile(r"item equipped changed from (?P<a>\S+) to (?P<b>\S+)")
NPC_RE = re.compile(r"\[(?P<npc>[A-Za-z][A-Za-z0-9_\-]*_\d+_?\d*)\]")
DLSS_RE = re.compile(r"DLSS", re.I)

# 已知的"噪音"类别，报告里只统计计数不展开
NOISE_CATS = {
    "AsyncOperationLogs", "LogSlate", "LogScript", "LogStreaming",
    "LogUIActionRouter", "LogCommonInput", "LogShaderLibrary", "LogDLSSNGX",
    "LogDLSSNGXRHI", "LogDLSS", "LogRHI", "LogMemory", "LogLoad",
}

TS_FMT = "%Y.%m.%d-%H.%M.%S"

# 编码：日志是 UTF-8，但中文 Windows 控制台默认 GBK。启动时把 stdout 切到 UTF-8，
# 并把无法编码的字符替换掉，避免整份报告因为一个字符炸掉。
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


@dataclass
class LogMeta:
    path: str
    build: str = ""
    engine: str = ""
    size: int = 0
    lines: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None

    @property
    def span_seconds(self) -> float:
        if self.first_ts and self.last_ts:
            return (self.last_ts - self.first_ts).total_seconds()
        return 0.0


@dataclass
class EacSession:
    begin_ts: datetime | None = None
    end_ts: datetime | None = None
    mode: int = 0
    begin_ok: bool = False
    end_ok: bool = False

    @property
    def duration(self) -> float | None:
        if self.begin_ts and self.end_ts:
            return (self.end_ts - self.begin_ts).total_seconds()
        return None

    @property
    def closed(self) -> bool:
        return self.end_ts is not None


@dataclass
class MapLoad:
    ts: datetime | None
    path: str

    @property
    def short(self) -> str:
        # /Game/Maps/Resort/RE_LD_T1_B1 -> Resort/RE_LD_T1_B1
        p = self.path
        if p.startswith("/Game/Maps/"):
            p = p[len("/Game/Maps/"):]
        return p


@dataclass
class SpawnPoint:
    ts: datetime | None
    who: str
    x: float
    y: float
    z: float


@dataclass
class Report:
    meta: LogMeta
    eac: list[EacSession] = field(default_factory=list)
    maps: list[MapLoad] = field(default_factory=list)
    streamed: list[str] = field(default_factory=list)
    spawns: list[SpawnPoint] = field(default_factory=list)
    regions: dict[str, int] = field(default_factory=dict)
    auto_region: str = ""
    cat_counts: dict[str, int] = field(default_factory=dict)
    warnings: int = 0
    errors: int = 0
    error_samples: list[str] = field(default_factory=list)

    # ---- 派生统计 ----
    @property
    def map_sequence(self) -> list[str]:
        out, prev = [], None
        for m in self.maps:
            s = m.short
            if s != prev:
                out.append(s)
                prev = s
        return out

    @property
    def eac_unclosed(self) -> int:
        return sum(1 for e in self.eac if not e.closed)

    @property
    def eac_total_seconds(self) -> float:
        return sum(e.duration or 0.0 for e in self.eac)

    @property
    def eac_failures(self) -> int:
        return sum(1 for e in self.eac if not e.begin_ok)


# ---------------------------------------------------------------------------
# 解析
# ---------------------------------------------------------------------------

def parse_ts(s: str) -> datetime | None:
    """2026.10.17-11.20.43:023 -> datetime（UTC，丢弃毫秒）。

    UE 的日志时间戳按 UTC 落盘。国内看这是"时间对不上"的根源：
    日志写 11:19，实际是当地 19:19。默认转本地时区。
    """
    if not s:
        return None
    base = s.split(":")[0]  # 去掉毫秒段
    try:
        dt = datetime.strptime(base, TS_FMT)
    except ValueError:
        return None
    dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone() if TZ_TO_LOCAL else dt


def parse_log(path: str) -> Report:
    meta = LogMeta(path=path)
    try:
        meta.size = os.path.getsize(path)
    except OSError:
        meta.size = 0

    rep = Report(meta=meta)
    cur_eac: EacSession | None = None

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            meta.lines += 1

            # 引擎信息必须在 LINE_RE 之前提取：
            # 早期启动行没有 [时间戳][帧号] 前缀，例如
            #   LogInit: Engine Version: 4.27.1-260801+release-7-1
            # 直接落在文件最前面，用通用行格式一过滤就没了。
            if not meta.build:
                mm = BUILD_RE.search(raw)
                if mm:
                    meta.build = mm.group("v")
            if not meta.engine:
                mm = ENGINE_RE.search(raw)
                if mm:
                    meta.engine = mm.group("v")

            m = LINE_RE.match(raw)
            if not m:
                continue

            ts = parse_ts(m.group("ts"))
            if ts:
                if meta.first_ts is None:
                    meta.first_ts = ts
                meta.last_ts = ts

            cat = m.group("cat")
            body = m.group("body").strip()

            # 类别计数
            rep.cat_counts[cat] = rep.cat_counts.get(cat, 0) + 1

            # 等级
            lv = LEVEL_RE.match(body)
            level = lv.group(1) if lv else ""
            if lv:
                body = body[lv.end():]
            if level == "Warning":
                rep.warnings += 1
            elif level in ("Error", "Fatal"):
                rep.errors += 1
                if len(rep.error_samples) < 25:
                    rep.error_samples.append(f"[{m.group('ts')}] {cat}: {body[:160]}")

            # 引擎信息已在上面处理，这里不再重复

            # EAC 会话
            # 顺序很关键：日志里是
            #   [BeginSession-003] Mode: N
            #   BeginSession SUCCESS
            #   ... 对局 ...
            #   EndSession SUCCESS
            # 所以 Mode 出现在 Begin 之前，必须先收 Mode 再收 Begin，
            # 且 Mode 只能写进"还没建会话"的那一段，否则会覆盖上一段。
            mm = EAC_MODE_RE.search(body)
            if mm:
                if cur_eac is None or cur_eac.begin_ok:
                    cur_eac = EacSession(begin_ts=ts)
                    rep.eac.append(cur_eac)
                cur_eac.mode = int(mm.group("mode"))

            mm = EAC_BEGIN_RE.search(body)
            if mm:
                # Mode 行已经开好段了就复用，别再新建
                if cur_eac is None or cur_eac.begin_ok:
                    cur_eac = EacSession(begin_ts=ts)
                    rep.eac.append(cur_eac)
                cur_eac.begin_ok = (mm.group("res") == "SUCCESS")
                if cur_eac.begin_ts is None:
                    cur_eac.begin_ts = ts

            mm = EAC_END_RE.search(body)
            if mm:
                if cur_eac is None:
                    cur_eac = EacSession()
                    rep.eac.append(cur_eac)
                cur_eac.end_ts = ts
                cur_eac.end_ok = (mm.group("res") == "SUCCESS")

            # 地图：>>> 是 streaming 子关卡，Browse 才是真正的关卡切换
            mm = MAP_STREAM_RE.search(body)
            if mm:
                rep.streamed.append(mm.group(1))
            mm = MAP_BROWSE_RE.search(body)
            if mm:
                rep.maps.append(MapLoad(ts=ts, path=mm.group(1)))

            # 出生点
            mm = FLOOR_RE.search(body)
            if mm:
                rep.spawns.append(SpawnPoint(
                    ts=ts, who=mm.group("who"),
                    x=float(mm.group("x")), y=float(mm.group("y")), z=float(mm.group("z")),
                ))

            # 区域
            if cat == "LogQos":
                mm = REGION_LIST_RE.search(body)
                if mm:
                    rep.regions[mm.group("r")] = int(mm.group("dc"))
                mm = AUTOREGION_RE.search(body)
                if mm and not rep.auto_region:
                    rep.auto_region = mm.group("r")

    return rep


def discover_logs(explicit: str | None) -> list[str]:
    if explicit:
        if os.path.isdir(explicit):
            return sorted(glob.glob(os.path.join(explicit, "*.log")))
        return [explicit]
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "OPP", "Saved", "Logs")
    if not os.path.isdir(base):
        return []
    return sorted(glob.glob(os.path.join(base, "*.log")))


def redact_path(p: str) -> str:
    """把导出的路径里的用户名替换成 %USERNAME%。

    报告会贴到 issue / 截图里，`C:\\Users\\<真名>\\...` 这种泄露没必要带出去。
    """
    home = os.environ.get("USERPROFILE") or ""
    local = os.environ.get("LOCALAPPDATA") or ""
    out = p
    if REDACT:
        if local:
            out = out.replace(local, "%LOCALAPPDATA%")
        if home:
            out = out.replace(home, "%USERPROFILE%")
    return out


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------

def fmt_dur(sec: float | None) -> str:
    if sec is None:
        return "-"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h{m:02d}m{s:02d}s"
    if m:
        return f"{m}m{s:02d}s"
    return f"{s}s"


def print_report(rep: Report) -> None:
    m = rep.meta
    name = os.path.basename(m.path)
    print("=" * 72)
    print(f"日志: {name}")
    print(f"  大小      : {m.size/1024/1024:.2f} MB / {m.lines} 行")
    print(f"  引擎      : {m.engine or '未识别'}")
    print(f"  构建      : {m.build or '未识别'}")
    if m.first_ts and m.last_ts:
        print(f"  覆盖时间  : {m.first_ts} → {m.last_ts}  (跨度 {fmt_dur(m.span_seconds)})")
    print()

    # EAC
    print(f"-- EAC 会话 ({len(rep.eac)} 次) " + "-" * 40)
    if not rep.eac:
        print("   无 EAC 会话记录（可能未进入联机，或日志被截断）")
    for i, e in enumerate(rep.eac, 1):
        dur = fmt_dur(e.duration)
        state = "正常关闭" if e.closed else "未关闭(异常退出/仍在进行)"
        ok = "OK" if e.begin_ok else "失败"
        print(f"   #{i}  开始 {e.begin_ts}  时长 {dur:>10}  Mode={e.mode}  建会话={ok}  {state}")
    if rep.eac_unclosed:
        print(f"   [!] {rep.eac_unclosed} 次会话未正常关闭 —— 常见于崩溃/强杀进程")
    print(f"   联机总时长: {fmt_dur(rep.eac_total_seconds)}")
    print()

    # 地图
    seq = rep.map_sequence
    print(f"-- 关卡切换 ({len(rep.maps)} 次) / streaming 子关卡 {len(set(rep.streamed))} 个 " + "-" * 6)
    if not seq:
        print("   本段日志没有关卡切换（可能只停在主菜单）")
    for i, s in enumerate(seq[:40], 1):
        print(f"   {i:>3}. {s}")
    if len(seq) > 40:
        print(f"   ... 还有 {len(seq)-40} 个")
    print()

    # 出生点
    if rep.spawns:
        print(f"-- 出生点采样 ({len(rep.spawns)} 条) " + "-" * 33)
        for s in rep.spawns[:10]:
            print(f"   {s.who:<28} X={s.x:>9.1f} Y={s.y:>9.1f} Z={s.z:>7.1f}")
        if len(rep.spawns) > 10:
            print(f"   ... 还有 {len(rep.spawns)-10} 条")
        print()

    # 区域
    if rep.regions:
        print("-- 服务器区域 " + "-" * 48)
        for r, dc in sorted(rep.regions.items()):
            print(f"   {r:<22} {dc} 个数据中心")
        if rep.auto_region:
            print(f"   自动选择: {rep.auto_region}")
        print()

    # 健康度
    print("-- 健康度 " + "-" * 52)
    print(f"   Warning : {rep.warnings}")
    print(f"   Error   : {rep.errors}")
    if rep.error_samples:
        print("   错误样本:")
        for s in rep.error_samples[:10]:
            print(f"     {s}")
    print()

    top = sorted(rep.cat_counts.items(), key=lambda kv: -kv[1])[:12]
    print("-- 日志构成 top12 " + "-" * 43)
    for cat, n in top:
        print(f"   {cat:<28} {n}")
    print()


def report_to_dict(rep: Report) -> dict:
    m = rep.meta
    return {
        "log": redact_path(m.path),
        "size_bytes": m.size,
        "lines": m.lines,
        "engine": m.engine,
        "build": m.build,
        "first_ts": m.first_ts.isoformat() if m.first_ts else None,
        "last_ts": m.last_ts.isoformat() if m.last_ts else None,
        "span_seconds": m.span_seconds,
        "eac_sessions": [
            {
                "begin": e.begin_ts.isoformat() if e.begin_ts else None,
                "end": e.end_ts.isoformat() if e.end_ts else None,
                "duration": e.duration,
                "mode": e.mode,
                "begin_ok": e.begin_ok,
                "closed": e.closed,
            }
            for e in rep.eac
        ],
        "maps": [{"ts": m2.ts.isoformat() if m2.ts else None, "path": m2.path} for m2 in rep.maps],
        "map_sequence": rep.map_sequence,
        "spawns": [asdict(s) | {"ts": s.ts.isoformat() if s.ts else None} for s in rep.spawns],
        "regions": rep.regions,
        "auto_region": rep.auto_region,
        "warnings": rep.warnings,
        "errors": rep.errors,
        "category_counts": rep.cat_counts,
    }


def print_sessions(rep: Report) -> None:
    print(f"# {os.path.basename(rep.meta.path)}")
    for i, e in enumerate(rep.eac, 1):
        dur = fmt_dur(e.duration)
        print(f"  第{i}局  {e.begin_ts}  {dur}")
    if not rep.eac:
        print("  (无场次)")


def md_report(reps: Iterable[Report]) -> str:
    lines = ["# The Outlast Trials 对局复盘", ""]
    for rep in reps:
        m = rep.meta
        lines += [f"## {os.path.basename(m.path)}", ""]
        lines.append(f"- 引擎：`{m.engine or '未识别'}`")
        lines.append(f"- 构建：`{m.build or '未识别'}`")
        if m.first_ts and m.last_ts:
            lines.append(f"- 时间：{m.first_ts} → {m.last_ts}（{fmt_dur(m.span_seconds)}）")
        lines.append(f"- EAC 会话：{len(rep.eac)} 次，合计 {fmt_dur(rep.eac_total_seconds)}")
        lines.append(f"- 告警 {rep.warnings} / 错误 {rep.errors}")
        lines.append("")
        if rep.map_sequence:
            lines.append("| # | 关卡 |")
            lines.append("|---|------|")
            for i, s in enumerate(rep.map_sequence[:60], 1):
                lines.append(f"| {i} | `{s}` |")
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="totlog", description="The Outlast Trials 日志复盘分析器（只读）")
    ap.add_argument("cmd", choices=["report", "sessions"], nargs="?", default="report")
    ap.add_argument("-f", "--file", help="指定日志文件或目录（默认扫 %%LOCALAPPDATA%%\\OPP\\Saved\\Logs）")
    ap.add_argument("--json", help="导出 JSON 到指定路径")
    ap.add_argument("--md", help="导出 Markdown 到指定路径")
    ap.add_argument("--utc", action="store_true", help="按 UTC 显示时间（默认转本地时区）")
    ap.add_argument("--no-redact", action="store_true", help="导出时保留完整路径（默认把用户名替换成 %%USERPROFILE%%）")
    args = ap.parse_args(argv)

    global TZ_TO_LOCAL, REDACT
    if args.utc:
        TZ_TO_LOCAL = False
    if args.no_redact:
        REDACT = False

    paths = discover_logs(args.file)
    if not paths:
        print("找不到日志。", file=sys.stderr)
        print(r"默认路径: %LOCALAPPDATA%\OPP\Saved\Logs\OPP.log", file=sys.stderr)
        print("跑一下游戏再试，或用 -f 指定文件。", file=sys.stderr)
        return 1

    reps = [parse_log(p) for p in paths]

    if args.cmd == "sessions":
        for r in reps:
            print_sessions(r)
    else:
        for r in reps:
            print_report(r)

    if args.json:
        outdir = os.path.dirname(os.path.abspath(args.json))
        os.makedirs(outdir, exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump([report_to_dict(r) for r in reps], fh, ensure_ascii=False, indent=2)
        print(f"[+] JSON -> {args.json}")

    if args.md:
        outdir = os.path.dirname(os.path.abspath(args.md))
        os.makedirs(outdir, exist_ok=True)
        with open(args.md, "w", encoding="utf-8") as fh:
            fh.write(md_report(reps))
        print(f"[+] Markdown -> {args.md}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
