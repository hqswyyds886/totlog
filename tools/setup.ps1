#requires -Version 5.1
<#
  Outlast Tools - 开发环境准备（可选）

  说明：本项目的主功能 totlog.py 是纯 Python、零依赖，
        不装任何东西就能跑。这个脚本只在你打算改 C/C++ 部分时才需要。

  装的是一套便携 MinGW-w64 GCC（UCRT + POSIX + SEH）：
    - 免安装、免管理员，解压即用
    - 自带 d3d11.h 等 Windows SDK 全套头文件和库
    - 支持 C++17/20

  为什么不用 VS BuildTools：体积大（数 GB）、装完要重启终端、
  还会往系统里塞服务。便携包 100MB 解压 15 秒，够用。

  用法：
    pwsh -File tools\setup.ps1 -Check          # 只检查
    pwsh -File tools\setup.ps1                 # 装到默认位置
    pwsh -File tools\setup.ps1 -InstallDir D:\mingw64
#>
param(
    [switch]$Check,
    [string]$InstallDir = (Join-Path $env:LOCALAPPDATA 'outlast-tools\mingw64')
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

# WinLibs 发布版：GCC 16.2.0 / mingw-w64 14.0.0 / UCRT
$REL   = '16.2.0posix-23.1.3-14.0.0-ucrt-r3'
$ASSET = 'winlibs-x86_64-posix-seh-gcc-16.2.0-mingw-w64ucrt-14.0.0-r3.7z'
$URL   = "https://github.com/brechtsanders/winlibs_mingw/releases/download/$REL/$ASSET"

function Write-Step($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "[+] $m" -ForegroundColor Green }
function Write-Warn2($m){ Write-Host "[!] $m" -ForegroundColor Yellow }

$gxx = Join-Path $InstallDir 'mingw64\bin\g++.exe'

# ---------------------------------------------------------------------------
# 检查
# ---------------------------------------------------------------------------
if ($Check) {
    Write-Step "检查环境"

    if (Test-Path $gxx) {
        Write-Ok "GCC: $((& $gxx --version | Select-Object -First 1))"
    } else {
        Write-Warn2 "GCC 未安装（仅 C/C++ 开发需要）: $InstallDir"
    }

    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py -and $py.Source -notmatch 'WindowsApps') {
        Write-Ok "Python: $((& $py.Source -V 2>&1))"
    } else {
        # PATH 里没有不代表没装：官方安装器会把路径写进注册表
        $found = $null
        foreach ($rk in 'HKLM:\SOFTWARE\Python\PythonCore','HKCU:\SOFTWARE\Python\PythonCore','HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore') {
            if (-not (Test-Path $rk)) { continue }
            foreach ($v in (Get-ChildItem $rk -ErrorAction SilentlyContinue)) {
                $ip = Join-Path $v.PSPath 'InstallPath'
                if (-not (Test-Path $ip)) { continue }
                $d = (Get-ItemProperty $ip).'(default)'
                if ($d -and (Test-Path (Join-Path $d 'python.exe'))) { $found = Join-Path $d 'python.exe'; break }
            }
            if ($found) { break }
        }
        if ($found) {
            Write-Ok "Python: $((& $found -V 2>&1))  (未在 PATH，需用 -Python 指定: $found)"
        } else {
            Write-Warn2 "未找到 Python —— 主功能 totlog.py 需要 Python 3.8+"
        }
    }

    $g = Get-Command git -ErrorAction SilentlyContinue
    if ($g) { Write-Ok "git: $((& $g.Source --version))" } else { Write-Warn2 "git 未安装" }
    return
}

# ---------------------------------------------------------------------------
# 安装
# ---------------------------------------------------------------------------
if (Test-Path $gxx) {
    Write-Ok "已存在，跳过: $((& $gxx --version | Select-Object -First 1))"
    return
}

Write-Step "下载 MinGW-w64 GCC 16.2（约 107 MB）"
$tmp = Join-Path $env:TEMP 'mingw64-dl.7z'
$sw = [Diagnostics.Stopwatch]::StartNew()
& curl.exe -L --retry 3 --retry-delay 2 --progress-bar -o $tmp $URL
if ($LASTEXITCODE -ne 0) { throw "下载失败 (exit=$LASTEXITCODE)" }
Write-Ok ("下载完成 {0:N0}s / {1:N1} MB" -f $sw.Elapsed.TotalSeconds, ((Get-Item $tmp).Length / 1MB))

Write-Step "解压到 $InstallDir"
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
& tar.exe -xf $tmp -C $InstallDir
if ($LASTEXITCODE -ne 0) { throw "解压失败 (exit=$LASTEXITCODE)" }

if (Test-Path $gxx) {
    Write-Ok "完成: $((& $gxx --version | Select-Object -First 1))"
    Remove-Item $tmp -ErrorAction SilentlyContinue
} else {
    throw "解压后找不到 $gxx"
}

Write-Host ""
Write-Ok "g++ 路径: $gxx"
Write-Host "  临时加入 PATH: `$env:PATH = '$(Split-Path $gxx)';`$env:PATH"
