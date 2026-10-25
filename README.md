# totlog — The Outlast Trials 对局复盘工具

[![CI](https://github.com/USER/totlog/actions/workflows/ci.yml/badge.svg)](../../actions)
[![Python](https://img.shields.io/badge/python-3.8%2B-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

只读本机游戏日志，把一局/一天的对局变成结构化统计。

**不碰游戏进程，不读游戏内存，不修改任何文件，不影响其他玩家。**

```
-- EAC 会话 (4 次) ----------------------------------------
   #1  19:20:43  36s        Mode=1  建会话=OK  正常关闭
   #2  19:21:20  1m18s      Mode=1  建会话=OK  正常关闭
   #3  19:22:39  1h07m29s   Mode=1  建会话=OK  正常关闭
   #4  20:30:10  55s        Mode=1  建会话=OK  正常关闭
   联机总时长: 1h10m18s

-- 服务器区域 ----------------------------------------------
   ap-northeast-2 / eu-central-1 / us-east-1 / us-west-2 ...
   自动选择: us-east-1

-- 健康度 --------------------------------------------------
   Warning : 299    Error : 34
```

---

## 快速开始

需要 Python 3.8+，无第三方依赖。

```bash
git clone https://github.com/USER/totlog.git
cd totlog

# 直接跑（默认扫 %LOCALAPPDATA%\OPP\Saved\Logs）
python src/totlog.py report

# 导出 JSON + Markdown
python src/totlog.py report --json out/report.json --md out/report.md

# 只看场次时间线
python src/totlog.py sessions

# 指定日志
python src/totlog.py report -f path/to/OPP.log
```

PowerShell 用户：

```powershell
pwsh -File tools/report.ps1
pwsh -File tools/report.ps1 -Sessions
```

---

## 它能统计什么

| 项 | 说明 |
|----|------|
| **场次** | 每局开始时间、时长（以 EAC 会话边界为准） |
| **异常退出** | 会话未正常关闭 = 崩溃或强杀 |
| **关卡切换** | 区分真正的换图（`LogNet: Browse`）和 streaming 子关卡（`>>>`） |
| **出生点** | 每个玩家的落点坐标 |
| **服务器区域** | 连了哪些 region、自动选了哪个 |
| **健康度** | Warning / Error 计数 + 错误样本 |
| **日志构成** | 各类别行数 top N |

时间默认转本地时区（日志原始值是 **UTC**），`--utc` 可关。导出路径会把用户名替换成 `%USERPROFILE%`，`--no-redact` 可关。

---

## 为什么做这个

调研这个游戏的反作弊时，结论是"联机向的内存类功能在技术上不成立"，详见
[`docs/反作弊技术分析.md`](docs/反作弊技术分析.md)。简版：

| 路线 | 结果 | 原因 |
|------|------|------|
| 外部只读 + 外部绘制 | 读不到 | EAC 内核拦 `ReadProcessMemory` 与裸 syscall，返回 `0xC0000022` |
| stub 掉 EAC 出口 | 被踢 | 服务器收不到会话 → `Authentication timed out` |
| 注入 DLL + hook | 起不来 | 完整性校验命中 IAT hook / 多余模块 |
| 改血量耐力 | 无效 | 数值服务器权威，下一帧盖回去 |

在"联机可用"的前提下这几条是互斥的。所以退回到唯一零风险、且确实有信息增量的方向：**读本地日志**。

反作弊的完整实测证据链（Steam 披露、驱动形态、`BeginSession` 日志）在
[`docs/反作弊技术分析.md`](docs/反作弊技术分析.md)；
GitHub 现有项目的真伪盘点与投毒鉴别清单在
[`docs/github开源项目调研.md`](docs/github开源项目调研.md)。

---

## 实现时踩过的坑

这些都是实测出来的，改代码前值得先看一眼：

| 坑 | 症结 |
|----|------|
| 时间差 8 小时 | UE 日志时间戳是 **UTC** |
| 时间解析全为 None | 格式是 `2026.10.17-11.20.43:023`，**带毫秒段**；帧号字段有前导空格 |
| 引擎版本读不到 | `LogInit: Engine Version:` 这行**没有时间戳前缀**，在通用行解析里会被直接过滤掉 |
| 关卡数爆到 800+ | `>>>` 是 **streaming 子关卡**，真正的切换看 `LogNet: Browse:` |
| EAC 场次的 Mode 串味 | `Mode:` 行出现在 `BeginSession` **之前**，且 `EndSession` 不重置游标，写错会覆盖上一段 |
| 控制台乱码 | 中文 Windows 默认 GBK，得把 stdout 切 UTF-8 |

---

## 项目结构

```
totlog/
├─ src/totlog.py                 核心：日志解析 + 报告
├─ tools/
│  ├─ report.ps1                 PowerShell 包装，自动找 Python
│  └─ setup.ps1                  可选：C/C++ 便携工具链（主功能不需要）
├─ docs/
│  ├─ 反作弊技术分析.md           EAC 机制 + 本机证据 + 为什么内存类功能不成立
│  └─ github开源项目调研.md       13 个仓库真伪 + 投毒鉴别清单
├─ tests/
│  ├─ test_totlog.py             7 项单测
│  └─ fixtures/sample.log        合成日志，无任何真实用户数据
└─ out/                          报告产物（已 gitignore）
```

## 开发

```bash
python tests/test_totlog.py
```

CI 会在 Python 3.8 / 3.10 / 3.12 上跑同一套测试。

## 免责

本项目只读取本机日志文件，不修改游戏、不注入进程、不与其他玩家交互。
日志格式随游戏版本变化，字段对不上时请提 issue 并附上**脱敏后**的相关行。

## License

MIT
