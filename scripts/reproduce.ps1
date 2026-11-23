# 一键复现：01 率定 -> 02 分析 -> 03 图件 -> 04 报告 -> 05 自检
# 用法（在项目根目录 xaj-calibration 下）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\reproduce.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File scripts\reproduce.ps1 -SkipBackup
# PowerShell 7 亦可：pwsh -File scripts\reproduce.ps1
param([switch]$SkipBackup)

$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here
Set-Location $root

function Resolve-Python {
    $cands = @()
    if ($env:DSH_PY) { $cands += $env:DSH_PY }
    $bundled = Join-Path $env:USERPROFILE ".dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
    if (Test-Path $bundled) { $cands += $bundled }
    $cands += "python"

    foreach ($c in $cands) {
        $ok = $false
        try {
            $out = & $c -c "import sys,pandas,numpy,docx,PIL;print(sys.version.split()[0])" 2>&1
            $ok = ($LASTEXITCODE -eq 0)
        } catch {
            $ok = $false
        }
        if ($ok) { return @{ exe = $c; ver = "$out".Trim() } }
    }
    throw "找不到同时装有 pandas/numpy/python-docx/Pillow 的 Python。请 pip install pandas numpy python-docx pillow，或设置 `$env:DSH_PY 指向可用解释器。"
}

$py = Resolve-Python
Write-Host "解释器: $($py.exe)  (Python $($py.ver))" -ForegroundColor Cyan

if (-not $SkipBackup) {
    $stamp = Get-Date -Format "MMdd-HHmmss"
    $bak = Join-Path $root "_repro_backup\$stamp"
    New-Item -ItemType Directory -Force $bak | Out-Null
    foreach ($d in @("outputs", "report")) {
        if (Test-Path (Join-Path $root $d)) { Move-Item (Join-Path $root $d) (Join-Path $bak $d) }
    }
    Write-Host "旧产物已移到 _repro_backup\$stamp" -ForegroundColor DarkGray
}

$steps = @(
    @("01_calibrate.py", "率定（DE 96 240 次评价 + Nelder-Mead 精修）", "约 2 分钟"),
    @("02_analysis.py",  "异参同效与单因子敏感性分析",                  "约 20 秒"),
    @("03_figures.py",   "生成 7 张报告图",                            "约 10 秒"),
    @("04_report.py",    "生成 Word 报告",                             "约 10 秒")
)

foreach ($s in $steps) {
    $t0 = Get-Date
    Write-Host "`n>>> $($s[0])  $($s[1])  （$($s[2])）" -ForegroundColor Yellow
    & $py.exe "scripts\$($s[0])"
    if ($LASTEXITCODE -ne 0) { throw "$($s[0]) 失败，退出码 $LASTEXITCODE" }
    $sec = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
    Write-Host "<<< $($s[0]) 完成，耗时 $sec s" -ForegroundColor Green
}

Write-Host "`n>>> 05_verify.py  复现自检" -ForegroundColor Yellow
& $py.exe "scripts\05_verify.py"
if ($LASTEXITCODE -ne 0) { throw "复现自检未通过，请把上面的 FAIL 行发我。" }
Write-Host "`n复现完成：outputs\ 与 report\ 已是最新产物。" -ForegroundColor Cyan
