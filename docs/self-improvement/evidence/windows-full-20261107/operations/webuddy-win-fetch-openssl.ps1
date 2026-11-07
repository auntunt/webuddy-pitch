$ProgressPreference='SilentlyContinue'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
Set-Location C:\tmh-runner\work\webuddy-windows-full-21f4e73-20261107
git -c http.sslBackend=openssl -c credential.helper= -c http.lowSpeedLimit=1024 -c http.lowSpeedTime=30 fetch --depth=1 https://github.com/auntunt/webuddy-pitch.git 21f4e73ef021fc12cb29ca0ee96e381a7ee8a27d
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
git checkout --detach FETCH_HEAD
exit $LASTEXITCODE
