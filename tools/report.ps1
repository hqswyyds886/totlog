#requires -Version 5.1
<#
  Outlast Tools - 日志复盘

  包装 src\totlog.py，自动找 Python，输出到 out\。

  用法：
    pwsh -File tools\report.ps1
    pwsh -File tools\report.ps1 -Utc
    pwsh -File tools\report.ps1 -Log 'C:\path\to\OPP.log'
    pwsh -File tools\report.ps1 -Sessions
#>
param(
    [switch]$Utc,
    [string]$Log,
    [switch]$Sessions,
    [string]$Python
)

$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$script = Join-Path $root 'src\totlog.py'
$outDir = Join-Path $root 'out'
New-Item -ItemType Directory -Force -Path $outDir | Out-Null

# 找 Python：-Python 参数 > PATH > py 启动器 > 常见安装位置
function Resolve-Python {
    param([string]$Explicit)
    if ($Explicit) {
        if (Test-Path $Explicit) { return $Explicit }
        throw "指定的 Python 不存在: $Explicit"
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch 'WindowsApps') { return $cmd.Source }
    $cmd = Get-Command python3 -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -notmatch 'WindowsApps') { return $cmd.Source }
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }
    # 最后兜底：python.exe 的注册表记录（官方安装器会写）
    $regKeys = @(
        'HKLM:\SOFTWARE\Python\PythonCore',
        'HKCU:\SOFTWARE\Python\PythonCore',
        'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore'
    )
    foreach ($rk in $regKeys) {
        if (-not (Test-Path $rk)) { continue }
        foreach ($ver in (Get-ChildItem $rk -ErrorAction SilentlyContinue)) {
            $ip = Join-Path $ver.PSPath 'InstallPath'
            if (-not (Test-Path $ip)) { continue }
            $dir = (Get-ItemProperty $ip).'(default)'
            if (-not $dir) { continue }
            $exe = Join-Path $dir 'python.exe'
            if (Test-Path $exe) { return $exe }
            # 有些安装只在 InstallPath 下存 ExecutablePath
            $exe2 = (Get-ItemProperty $ip -ErrorAction SilentlyContinue).ExecutablePath
            if ($exe2 -and (Test-Path $exe2)) { return $exe2 }
        }
    }
    return $null
}

$py = Resolve-Python -Explicit $Python
if (-not $py) {
    throw "找不到 Python 3。装一个 Python 3.8+ 并确保 python 在 PATH 里，或用 -Python 指定路径。"
}

$env:PYTHONIOENCODING = 'utf-8'

$argv = @($script)
if ($Sessions) { $argv += 'sessions' } else { $argv += 'report' }
if ($Log) { $argv += @('-f', $Log) }
if ($Utc) { $argv += '--utc' }
if (-not $Sessions) {
    $argv += @('--json', (Join-Path $outDir 'report.json'))
    $argv += @('--md',   (Join-Path $outDir 'report.md'))
}

& $py @argv
exit $LASTEXITCODE
