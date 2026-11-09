# Open this bundle's TCP port to the local subnet only. Run in Administrator PowerShell.
param(
  [int]$Port = 8790,
  [string]$Address = ''
)
$ErrorActionPreference = 'Stop'
$config = Join-Path $env:LOCALAPPDATA 'Webuddy\config.json'
if (Test-Path -LiteralPath $config) { $settings = Get-Content -LiteralPath $config -Raw | ConvertFrom-Json; if ($settings.port) { $Port = [int]$settings.port } }
$rule = 'Webuddy LAN'
Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
$params = @{ DisplayName = $rule; Direction = 'Inbound'; Action = 'Allow'; Protocol = 'TCP'; LocalPort = $Port; RemoteAddress = 'LocalSubnet'; Profile = @('Private','Domain'); Program = (Join-Path $PSScriptRoot 'runtime\python\python.exe') }
if ($Address) { $params['LocalAddress'] = $Address }
New-NetFirewallRule @params | Out-Null
"Firewall rule '$rule': inbound TCP $Port from LocalSubnet$(if ($Address) { " on $Address" })"
