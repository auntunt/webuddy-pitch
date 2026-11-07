$ProgressPreference='SilentlyContinue'
Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" | ForEach-Object {
 if($_.ProcessId -ne $PID -and $_.CommandLine -match '-EncodedCommand\s+([A-Za-z0-9+/=]+)') {
  $text=[Text.Encoding]::Unicode.GetString([Convert]::FromBase64String($Matches[1]))
  if($text.Contains("webuddy-full-a9ce6f20-20261107") -and $text.Contains('full source transfer incomplete')) {
   Write-Output "Stop superseded waiting script PID=$($_.ProcessId)"
   Stop-Process -Id $_.ProcessId -ErrorAction Stop
  }
 }
}
