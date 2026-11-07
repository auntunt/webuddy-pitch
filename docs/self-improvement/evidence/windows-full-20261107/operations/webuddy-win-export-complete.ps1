$ErrorActionPreference='Stop';$ProgressPreference='SilentlyContinue';[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
$p='C:\tmh-runner\work\webuddy-full-e282afab-proof-20261107'
Get-Content "$p\supplement\run.json"
$out='C:\tmh-runner\work\webuddy-full-e282afab-complete-20261107.tar.gz'
tar -czf $out -C $p run.json dependencies.txt launch.py complete-timeouts.py supplement shard0 shard1 shard2 shard3 shard4 shard5 shard6 shard7 shard0-driver.log shard1-driver.log shard2-driver.log shard3-driver.log shard4-driver.log shard5-driver.log shard6-driver.log shard7-driver.log
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
Get-Item $out | Select-Object Name,Length | ConvertTo-Json
Get-FileHash $out -Algorithm SHA256 | Select-Object Hash | ConvertTo-Json
