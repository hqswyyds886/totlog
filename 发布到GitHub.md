# 发布到 GitHub

仓库已初始化并完成提交，剩下的是推到远端。按下面做，5 分钟。

---

## 一、先在本地做最后确认

```powershell
cd C:\Users\fh\Documents\deepseek-harness\default-workspace\outlast-tools

# 1) 测试要全绿
D:\Python312\python.exe tests\test_totlog.py

# 2) 确认没有本机信息混进提交
git ls-files | Select-String 'log$|pycache|out/report'

# 3) 看看提交内容
git log --oneline
```

预期：测试 7 项通过；第 2 条只匹配到 `tests/fixtures/sample.log`（那是合成样例，故意的）。

---

## 二、创建远端仓库

### 方式 A：网页（最省事）

1. 打开 https://github.com/new
2. **Repository name** 填 `totlog`
3. **Description** 填：
   ```
   The Outlast Trials 对局复盘工具 — 只读本机日志，统计场次/关卡/区域/健康度
   ```
4. 选 **Public**
5. **不要**勾 Add README / .gitignore / license（本地已经有了，勾了会冲突）
6. Create repository

### 方式 B：命令行

```powershell
# 需要先装 gh 并登录
winget install GitHub.cli
gh auth login
gh repo create totlog --public --source=. --remote=origin --push
```

用方式 B 的话，跳过第三步。

---

## 三、推到远端

把 `YOURNAME` 换成你的 GitHub 用户名：

```powershell
cd C:\Users\fh\Documents\deepseek-harness\default-workspace\outlast-tools

git branch -M main
git remote add origin https://github.com/YOURNAME/totlog.git
git push -u origin main
```

> 首次推送会弹浏览器授权。如果你之前配过 PAT，也可以直接把 token 拼进 URL，
> 但**不要**把带 token 的 URL 存进 `git remote`——它会明文躺在 `.git/config` 里。

---

## 四、推完立刻做这 4 件事

### 1. 替换 README 里的占位符

README 顶部有两处 `USER`：

```markdown
[![CI](https://github.com/USER/totlog/actions/workflows/ci.yml/badge.svg)](../../actions)
...
git clone https://github.com/USER/totlog.git
```

改成你的用户名，然后：

```powershell
git commit -am "docs: 填入真实仓库地址"
git push
```

### 2. 加 Topics

仓库页 → 右上齿轮 → Topics，加这些（有助于被搜到）：

```
outlast-trials  unreal-engine  game-log  log-analysis  python  replay-analysis  statistics
```

### 3. 确认 CI 跑绿

推完打开 `https://github.com/YOURNAME/totlog/actions`

应该看到 6 个 job（3 个 Python 版本 × 2 个系统）。第一次跑约 1 分钟。

### 4. 发 Release

仓库页 → Releases → Create a new release

- Tag: `v0.1.0`
- Title: `v0.1.0 — 首个可用版本`
- 描述：

```markdown
## 功能

- EAC 会话统计：场次、时长、异常退出识别
- 关卡切换与 streaming 子关卡区分
- 出生点 / 服务器区域 / 健康度统计
- JSON + Markdown 导出，路径自动脱敏

## 安装

无需安装，Python 3.8+ 直接跑：

\`\`\`bash
git clone https://github.com/YOURNAME/totlog.git
cd totlog
python src/totlog.py report
\`\`\`

## 说明

只读取本机日志文件，不修改游戏、不注入进程、不与其他玩家交互。
```

---

## 五、之后更新的推法

```powershell
git add -A
git commit -m "feat: 说明这次改了什么"
git push
```

提交信息建议用 [Conventional Commits](https://www.conventionalcommits.org/)：
`feat:` / `fix:` / `docs:` / `test:` / `refactor:`。

---

## 已处理掉的发布风险

发布前扫描并清理了这些，记录在此供你复核：

| 项 | 处理 |
|----|------|
| 真实游戏日志（含对局时间、坐标） | **未提交**，只在本地 `out/`；CI 用合成 fixture |
| `C:\Users\<用户名>` 路径 | 导出时自动替换成 `%USERPROFILE%`，可用 `--no-redact` 关 |
| 本机 Steam 库路径 `D:\steam` | 文档里改成 `<SteamLib>` |
| 本机 Python 路径 `D:\Python312` | 脚本改成自动探测（PATH → py 启动器 → 注册表） |
| EAC productid / sandboxid / deploymentid | 文档里改成 `<productid>` 等占位符 |
| 投毒仓库的网盘链接与解压密码 | 改成 `<外部网盘链接>` / `<密码>`，只保留文案形状 |
| `__pycache__`（内含源文件绝对路径） | 已删，且 `.gitignore` 排除 |

### 有意保留的

- **引擎版本 `4.27.1`** 和 **反作弊是内核级 EAC** —— 这是公开事实，也是文档的核心结论，必须留
- **`tests/fixtures/sample.log`** —— 手写的合成日志，不含任何真实数据
- **GitHub 上那些仓库的 owner/name** —— 公开信息，调研结论需要可查证

---

## 如果不想公开发这些

文档里有几处内容性质偏"对抗研究"（EAC 机制拆解、为什么绕过会失败、UE 对象遍历原理）。
两种折中：

1. **拆成两个仓库**：`totlog` 只放工具，`docs/` 里的分析单独放，或写成博客
2. **仓库设为 Private**，只给自己和熟人看

工具本身是完全干净的——只读日志文件，没有任何进程交互代码。风险点只在文档的表述上。
