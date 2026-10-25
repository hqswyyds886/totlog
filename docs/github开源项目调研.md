# GitHub 开源项目调研

> 实测时间：2026-10 / 检索方式：GitHub Search API + 仓库页直读
> 检索词：`outlast trials` / `outlasttrials` / `OutlastTrials cheat` / `outlast trials mod` / `Outlast Trials SDK` / `outlast trials esp`

---

## 总览

| 仓库 | 语言 | 最后更新 | 真伪 | 用途 |
|------|------|---------|------|------|
| [AIN-sch/outlast-trials-cheat](https://github.com/AIN-sch/outlast-trials-cheat) | C++ | 2026-10 | ✅ **真分析笔记** | EAC 行为实测 + SDK dump 记录 |
| [Smyka/Lathe](https://github.com/Smyka/Lathe) | C# | 2026-05 | ✅ 真 | Mod 管理器 & 工具 |
| [xidenlz/Outlast-TrialsSDK](https://github.com/xidenlz/Outlast-TrialsSDK) | C++ | 2024-12 | ✅ 真（但过期） | SDK dump |
| [IceCubesYo/Outlast-trials-SDK-Dump](https://github.com/IceCubesYo/Outlast-trials-SDK-Dump) | C | 2023-05 | ✅ 真（但过期） | SDK dump |
| [antoniomalheirs/OutlastTrials-Audio-Mod](https://github.com/antoniomalheirs/OutlastTrials-Audio-Mod) | — | 2026-07 | ✅ 真 | 葡萄牙语配音 mod |
| [antoniomalheirs/OutlastTrials-Hud-UI-Mod](https://github.com/antoniomalheirs/OutlastTrials-Hud-UI-Mod) | — | 2026-08 | ✅ 真 | HUD/UI 重排（UAssetAPI + Repak） |
| [QuackInE/Outlast-Trials-VR](https://github.com/QuackInE/Outlast-Trials-VR) | Lua | 2026-07 | ✅ 真 | VR mod |
| [DetectiveFl/TOT-Mod-Tool-core](https://github.com/DetectiveFl/TOT-Mod-Tool-core) | C# | 2026-08 | ✅ 真 | Mod 生成辅助 |
| **Ondolphige/The-Outlast-Trials-Ultimate-Assistant** | Python | 2026-10 | ❌ **投毒** | 网盘加密包 + 关杀软 |
| shadrianwest/TrialsMod | — | 2025-06 | ❌ 空壳 | 无代码 |
| dinkfield931/TrialsMod | — | 2025-06 | ❌ 空壳 | 无代码 |
| rankinescalevalois9303/outlast-trials-hack-... | — | 2026-10 | ❌ SEO 垃圾 | 关键词堆砌 |
| sandals891joggers/The-Outlast-Trials-Ultimate-Mod-Suite | — | 2026-10 | ❌ SEO 垃圾 | 关键词堆砌 |

**结论：能真正拿来用的只有两类——研究笔记（懂原理）和 Mod 管理器（改本地资源）。没有任何一个可用的、开源的、联机向功能性项目。**

---

## 重点：AIN-sch/outlast-trials-cheat

这是唯一值得读的仓库。作者写的是分析笔记，README 原话：

> 先说丑话：这是我自己留的分析笔记，起因就是想看看 EAC 到底在干什么。不是外挂，也不教开挂。被踢被封别找我，联机排位别用。

### 他实测出来的关键事实

**1. EAC 正常运行时，外部读内存被内核拦死**

```
ReadProcessMemory            → err=5
NtReadVirtualMemory (ntdll)  → 0xC0000022
裸 syscall（自己拼 stub）      → 0xC0000022
NtQueryVirtualMemory         → 放行
EnumProcessModulesEx / Module32 / PEB 查询 → 全被拦
OpenProcess(PROCESS_ALL_ACCESS) → 成功（提权后）
```

他的原话：

> 连裸 syscall 都被拒，那拦截就在内核里，用户态怎么绕都没用。提权也没用 —— 句柄给你了，读的时候不给。

**这一条直接否定了"外部只读 + 外部绘制 = 完全无风险"这个最常见的方案。** 在本作上，它压根读不到东西。

**2. stub 掉 EAC 出口 → 联机被踢**

> 你已被踢出服务器。
> Authentication timed out (1/3)

**3. 注入带 hook 的 DLL → 游戏直接起不来**

> 我拿一个带 hook 的 DLL 试过，游戏直接起不来。

**4. 数值由服务器权威**

> 血量、耐力、位置这些字段是服务器说了算的。你本地改了，服务器下一帧就盖回去，看起来像"改了没反应"。

**5. 崩溃上报要单独拦**

`CrashReportClient.exe` 崩的时候上传 minidump，里面带完整模块列表。

### 这份笔记的坑（必须知道）

作者写的引擎是 **UE 5.5**，但本机日志实测是 **4.27.1**（`release-7-1-CL-260801`）。

他给的 offset：

```
GNames  (FNamePool)  RVA = 0x6EB2C00
GObjects             RVA = 0x6F21838
```

**这是他那个版本的 RVA，不是你的。** 游戏一更新就全废。他在 README 里自己也说了"游戏更新挺勤，版本一更偏移就得重看"。

同理，他给的那张常用偏移表（`ARBPawn::Health = 0x5418` 之类）也只对他那个 build 成立。

### 他踩过、值得记的坑

| 坑 | 症结 |
|----|------|
| Dumper-7 报 `Could not find GNames!` | 特征码对不上，别硬改特征码，直接配 `GNamesOffset` |
| FNamePool 索引理解错 | 以为是"第几个 entry"→ 名字全错、内存飙到 9G。实际是**块内字节偏移 ÷ 2** |
| `GetPrivateProfileIntA` 不认十六进制 | 配 `0x6EB2C00` 读出来是 0，得用 `strtoul(..., 16)` |
| `.bat` 里 `/Fo"路径\"` | 结尾反斜杠吃掉引号，整条命令失效 |
| 游戏一崩什么都不剩 | 加阶段日志（写文件）+ `__try/__except` |
| 提权是必须的 | EAC 驱动会把普通权限进程的读内存权限剥掉 |

---

## 反面样本：怎么认出投毒仓库

以 `Ondolphige/The-Outlast-Trials-Ultimate-Assistant` 为例，特征非常标准：

**仓库文件列表只有两个文件：**
```
README.md
helper.py
```

**README 里写着（原文节选）：**

```
### [DOWNLOAD ZIP ARCHIVE (LATEST VERSION)](<外部网盘链接>)
Archive password: <密码>
...

3. Run Assistant.exe as Administrator.
...
> Antivirus warning? This is a false positive because the tool
> interacts with game memory. Add the file to your exceptions list.
```

> 链接和密码这里刻意隐去。这类仓库寿命很短，账号被封后链接就失效，但脚手架会被原样复制到下一个"外挂项目"上。**记住的是这几句文案的形状，不是那串字符。**

**逐条对照：**

| 信号 | 说明 |
|------|------|
| 功能列表写得极全（ESP/Aimbot/无限耐力/改 FOV…12 项） | 越全越假，真项目不会一次给你 12 个功能还免费 |
| 真正的东西在**网盘加密包**里 | 仓库里没有可编译源码，代码审查无从谈起 |
| 让你**关杀软加例外** | 唯一目的就是让 payload 能落地 |
| 要求**以管理员运行** | 提权后能干的事就不只是游戏了 |
| 塞一堆 **SEO 关键词** | "The Outlast Trials trainer, hack 2026" —— 这是给搜索引擎看的，不是给人看的 |
| 作者账号只发这一个仓库 | 一次性账号，骗完就换 |

**这条 README 里的 `helper.py` 是"透明度道具"** —— 让你以为"有源码所以安全"，但真正运行的是网盘里那个 exe。这类包常见载荷：浏览器 cookie/密码窃取、Steam 会话劫持、剪贴板替换（换掉你的加密货币地址）、远控。

---

## 给"想自己搞"的人的结论

1. **别下载任何网盘包**。这个生态里 90% 是投毒，且专门盯着"想做外挂的人"——因为这些人会主动关杀软。
2. **真想学原理，读 AIN-sch 那份笔记**，它是真实测出来的，而且把失败路径也写了（这比成功路径值钱）。
3. **想做工具就做本地向的**：Mod 管理器、战绩统计、日志复盘。这些不需要碰 EAC，也就没有对抗成本。
4. **偏移是易腐品**。任何给你"固定 offset"的项目，在游戏更新后都是废纸。要长期可用，必须自己会 dump。
