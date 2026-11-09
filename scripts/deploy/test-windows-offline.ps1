param(
    [Parameter(Mandatory=$true)][string]$Archive,
    [Parameter(Mandatory=$true)][string]$Evidence
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Evidence = [IO.Path]::GetFullPath($Evidence)
New-Item -ItemType Directory -Path $Evidence -ErrorAction Stop | Out-Null
# Use Unicode without depending on the Windows PowerShell script file's code page.
$label = 'Webuddy ' + [char]0x79bb + [char]0x7ebf + ' test'
$dest = Join-Path $Evidence $label
Expand-Archive -LiteralPath $Archive -DestinationPath $dest
$root = Join-Path $dest 'Webuddy'
$python = Join-Path $root 'runtime\python\python.exe'
$tag = 'Webuddy-Offline-Smoke-' + [Guid]::NewGuid().ToString('N')
$rules = @()
try {
    $programs = @($python) + @(Get-ChildItem (Join-Path $root 'tools') -Filter '*.exe' -Recurse | ForEach-Object FullName)
    $programs += @(Get-Command node.exe,git.exe -ErrorAction SilentlyContinue | ForEach-Object Source)
    $claude = Get-Command claude.cmd -ErrorAction SilentlyContinue
    if ($claude) {
        $npm = Join-Path (Split-Path $claude.Source) 'node_modules\@anthropic-ai'
        if (Test-Path $npm) {
            $programs += @(Get-ChildItem $npm -Filter '*.exe' -Recurse | ForEach-Object FullName)
        }
    }
    $i = 0
    foreach ($program in ($programs | Select-Object -Unique)) {
        $name = $tag + '-' + $i
        New-NetFirewallRule -DisplayName $name -Name $name -Direction Outbound -Action Block -Program $program -Profile Any | Out-Null
        $rules += $name
        $i++
    }
    Write-Output "FIREWALL_RULES=$($rules.Count)"
    & $python -B (Join-Path $PSScriptRoot 'test-windows-offline.py') $root --expect-network-blocked
    if ($LASTEXITCODE -ne 0) {throw "Offline smoke failed: $LASTEXITCODE"}
    $receipt = Get-ChildItem -LiteralPath $dest -Filter receipt.json -Recurse | Select-Object -First 1
    if (-not $receipt) {throw 'Smoke receipt missing'}
    Copy-Item -LiteralPath $receipt.FullName -Destination (Join-Path $Evidence 'receipt.json')
} finally {
    foreach ($name in $rules) {Remove-NetFirewallRule -Name $name}
    if (Get-NetFirewallRule -Name "$tag*" -ErrorAction SilentlyContinue) {throw 'Test firewall rules remain'}
    Write-Output 'TEST_FIREWALL_RULES_REMOVED'
}
