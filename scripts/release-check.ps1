# scripts/release-check.ps1 - pre-release local checks (Windows PowerShell 5.1+ / PowerShell 7).
# ASCII only on purpose: Windows PowerShell 5.1 reads .ps1 as ANSI unless a BOM is present, so a
# UTF-8 Chinese string here could break parsing on a machine without the BOM. Docs stay in Chinese.
#
# Steps: env + version consistency -> pytest collect-only -> CI fast gate -> key suites
#        -> optional pip install smoke -> ops CLI tests (if present).
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/release-check.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/release-check.ps1 -InstallSmoke
#   $env:PYTHON='C:\Python312\python.exe'; ... -File scripts/release-check.ps1
# Exit code: 0 all passed (SKIP allowed); 1 any FAIL.
[CmdletBinding()]
param(
    [switch]$InstallSmoke,
    [switch]$SkipNode
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
if (-not $env:NO_PROXY) { $env:NO_PROXY = '127.0.0.1,localhost,::1' }
if (-not $env:no_proxy) { $env:no_proxy = $env:NO_PROXY }

$Python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$script:Pass = 0
$script:Fail = 0
$script:Skip = 0
$script:Failures = @()
$script:LastOk = $false

function Write-Head([string]$Text) {
    Write-Host ''
    Write-Host "== $Text"
}

function Show-Tail([object[]]$Output, [int]$Lines = 30) {
    if (-not $Output) { return }
    $tail = @($Output | Select-Object -Last $Lines)
    foreach ($line in $tail) { Write-Host "    $line" }
}

function Add-Result([string]$Name, [string]$State, [double]$Seconds, [string]$Detail) {
    switch ($State) {
        'PASS' { $script:Pass++; Write-Host ('  [PASS] {0} ({1:N1}s) {2}' -f $Name, $Seconds, $Detail) }
        'SKIP' { $script:Skip++; Write-Host ('  [SKIP] {0} - {1}' -f $Name, $Detail) }
        default {
            $script:Fail++
            $script:Failures += "$Name - $Detail"
            Write-Host ('  [FAIL] {0} ({1:N1}s) {2}' -f $Name, $Seconds, $Detail)
        }
    }
}

function Invoke-Step([string]$Name, [string[]]$PyArgs, [switch]$AllowSkip) {
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    $output = @()
    try {
        $output = @(& $Python @PyArgs 2>&1)
        $code = $LASTEXITCODE
    }
    catch {
        $output = @("$($_.Exception.Message)")
        $code = 1
    }
    $sw.Stop()
    $seconds = $sw.Elapsed.TotalSeconds
    $script:LastOk = ($code -eq 0)
    if ($code -eq 0) {
        $last = @($output | Where-Object { "$_".Trim() -ne '' } | Select-Object -Last 1)
        $detail = if ($last.Count -gt 0) { "$($last[0])".Trim() } else { 'ok' }
        Add-Result $Name 'PASS' $seconds $detail
    }
    elseif ($AllowSkip) {
        Add-Result $Name 'SKIP' $seconds "exit $code"
    }
    else {
        Add-Result $Name 'FAIL' $seconds "exit $code"
        Show-Tail $output
    }
    return $output
}

Write-Host "release-check: $Root"
Write-Host "python: $Python  ($(& $Python --version 2>&1))"
Write-Host "node:   $(if (Get-Command node -ErrorAction SilentlyContinue) { & node --version } else { 'not found' })"
Write-Host "git:    $(if (Get-Command git -ErrorAction SilentlyContinue) { (& git --version) } else { 'not found' })"

# 1) Version consistency: pyproject.toml and tmh/__init__.py must agree.
Write-Head 'version consistency'
$pyprojectText = Get-Content -Raw -LiteralPath (Join-Path $Root 'pyproject.toml')
$initText = Get-Content -Raw -LiteralPath (Join-Path (Join-Path $Root 'tmh') '__init__.py')
$m1 = [regex]::Match($pyprojectText, '(?m)^version\s*=\s*"([^"]+)"')
$m2 = [regex]::Match($initText, '__version__\s*=\s*"([^"]+)"')
$vPy = if ($m1.Success) { $m1.Groups[1].Value } else { '' }
$vTmh = if ($m2.Success) { $m2.Groups[1].Value } else { '' }
if ($vPy -and $vTmh -and ($vPy -eq $vTmh)) {
    Add-Result 'version consistency' 'PASS' 0 "version $vPy"
}
else {
    Add-Result 'version consistency' 'FAIL' 0 "pyproject='$vPy' tmh='$vTmh'"
}

# 2) git >= 2.38 (platform branch/worktree operations need a modern git).
Write-Head 'git version'
$gitVersionText = ''
if (Get-Command git -ErrorAction SilentlyContinue) { $gitVersionText = (& git --version 2>&1) }
if ($gitVersionText -match '(\d+)\.(\d+)') {
    $gitMajor = [int]$Matches[1]
    $gitMinor = [int]$Matches[2]
    if (($gitMajor -gt 2) -or (($gitMajor -eq 2) -and ($gitMinor -ge 38))) {
        Add-Result 'git >= 2.38' 'PASS' 0 "git $gitMajor.$gitMinor"
    }
    else {
        Add-Result 'git >= 2.38' 'FAIL' 0 "git $gitMajor.$gitMinor is older than 2.38"
    }
}
else {
    Add-Result 'git >= 2.38' 'FAIL' 0 'git not found or version unreadable'
}

# 3) Full collection: imports work and nothing fails to collect.
Write-Head 'pytest collect-only'
Invoke-Step 'pytest collect-only' @('-m', 'pytest', '--collect-only', '-q', '-p', 'no:cacheprovider', 'tests') | Out-Null

# 4) CI fast gate (keep in sync with .github/workflows/ci.yml).
Write-Head 'CI fast gate'
$fastGate = @(
    'tests/test_command.py', 'tests/test_gates.py', 'tests/test_golang.py', 'tests/test_jpa.py',
    'tests/test_lessons.py', 'tests/test_filelock.py', 'tests/test_comment_drafts.py'
)
Invoke-Step 'fast gate' (@('-m', 'pytest', '-q', '-p', 'no:cacheprovider') + $fastGate) | Out-Null

# 5) Key suites for this release.
Write-Head 'key suites'
$keySuites = @(
    'tests/test_context_pack.py', 'tests/test_org_knowledge.py', 'tests/test_habits.py', 'tests/test_g4_local_pilot.py'
)
Invoke-Step 'key suites' (@('-m', 'pytest', '-q', '-p', 'no:cacheprovider') + $keySuites) | Out-Null

# 6) Isolated installed CLI, project install/refresh and offline install smoke.
if ($InstallSmoke) {
    Write-Head 'pip install . smoke'
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("tmh-install-smoke-" + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Force -Path $tmp | Out-Null
    try {
        Invoke-Step 'pip install .' @('-m', 'pip', 'install', '.', '--no-deps', '--no-build-isolation', '--target', $tmp, '--disable-pip-version-check', '-q') | Out-Null
        if ($script:LastOk) {
            Invoke-Step 'installed functional smoke' @('-I', '-X', 'utf8', (Join-Path $Root 'scripts/installed-smoke.py'), $tmp) | Out-Null
        }
        else {
            Add-Result 'installed functional smoke' 'SKIP' 0 'install failed'
        }
    }
    finally {
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
}
else {
    Write-Head 'pip install . smoke'
    Add-Result 'pip install .' 'SKIP' 0 'not enabled; pass -InstallSmoke'
}

# 7) ops CLI tests (optional; outside this repo, may live in ../ops).
if (-not $SkipNode) {
    Write-Head 'ops CLI tests'
    $node = Get-Command node -ErrorAction SilentlyContinue
    $opsDir = $null
    foreach ($candidate in @((Join-Path $Root 'ops'), (Join-Path (Split-Path -Parent $Root) 'ops'))) {
        if (Test-Path (Join-Path $candidate 'tests')) { $opsDir = $candidate; break }
    }
    if (-not $node) {
        Add-Result 'node --test ops' 'SKIP' 0 'node not installed'
    }
    elseif (-not $opsDir) {
        Add-Result 'node --test ops' 'SKIP' 0 'no ops/tests found (deploy machines usually omit ops)'
    }
    else {
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        Push-Location $opsDir
        try {
            $nodeOut = @(& node --test 'tests/*.test.mjs' 2>&1)
            $nodeCode = $LASTEXITCODE
        }
        finally {
            Pop-Location
        }
        $sw.Stop()
        $passLine = @($nodeOut | Where-Object { "$_" -match 'pass \d+' } | Select-Object -Last 1)
        if ($nodeCode -eq 0) {
            $detail = if ($passLine.Count -gt 0) { "$($passLine[0])".Trim() } else { 'ok' }
            Add-Result 'node --test ops' 'PASS' $sw.Elapsed.TotalSeconds $detail
        }
        else {
            Add-Result 'node --test ops' 'FAIL' $sw.Elapsed.TotalSeconds "exit $nodeCode"
            Show-Tail $nodeOut
        }
    }
}

# Summary.
Write-Head 'summary'
Write-Host ("  PASS {0}  FAIL {1}  SKIP {2}" -f $script:Pass, $script:Fail, $script:Skip)
if ($script:Fail -gt 0) {
    Write-Host ''
    Write-Host '  failed:'
    foreach ($f in $script:Failures) { Write-Host "   - $f" }
    Write-Host ''
    Write-Host 'RELEASE CHECK: FAIL'
    exit 1
}
Write-Host ''
Write-Host 'RELEASE CHECK: PASS'
exit 0
