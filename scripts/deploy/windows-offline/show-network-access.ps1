# Print this bundle's loopback and authenticated LAN links. Parameters come from
# the bundle config and TMH_TOKEN; no address is hardcoded.
param(
  [string]$Config = (Join-Path $PSScriptRoot 'config.json'),
  [string]$Address = ''
)
$settings = if (Test-Path -LiteralPath $Config) { Get-Content -Raw -Encoding UTF8 -LiteralPath $Config | ConvertFrom-Json } else { [pscustomobject]@{} }
$port = if ($settings.port) { [int]$settings.port } elseif ($env:TMH_PORT) { [int]$env:TMH_PORT } else { 8790 }
$token = $env:TMH_TOKEN
if (-not $token -and $settings.environment -and $settings.environment.TMH_TOKEN) { $token = $settings.environment.TMH_TOKEN }
if (-not $Address) {
  $Address = (Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    Select-Object -First 1 -ExpandProperty IPAddress)
}
$query = if ($token) { '?token=' + $token } else { '' }
"Loopback:  http://127.0.0.1:$port/"
if ($Address) { "LAN:       http://${Address}:$port/$query" }
if ($settings.environment -and $settings.environment.TMH_PUBLIC_URL) { "Public:    $($settings.environment.TMH_PUBLIC_URL)$query" }
if (-not $token -and $settings.host -and $settings.host -notin @('127.0.0.1', 'localhost', '::1')) {
  'WARN: a non-loopback listener without TMH_TOKEN is refused by the server'
}
