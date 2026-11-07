$ProgressPreference='SilentlyContinue'
$env:PYTHONUTF8='1'
python -c "import urllib.request; r=urllib.request.urlopen('https://codeload.github.com/auntunt/webuddy-pitch/tar.gz/21f4e73ef021fc12cb29ca0ee96e381a7ee8a27d',timeout=30); import shutil; f=open('C:/tmh-runner/work/webuddy-21f4e73-source.tar.gz','wb'); shutil.copyfileobj(r,f); f.close(); print('download complete')"
exit $LASTEXITCODE
