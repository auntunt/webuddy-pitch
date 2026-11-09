param(
    [Parameter(Mandatory=$true)][string]$JavaHome,
    [ValidateSet('compile','test','package')][string]$Goal='test'
)
$ErrorActionPreference='Stop'
if(-not (Test-Path (Join-Path $JavaHome 'bin/java.exe'))){throw 'Java 8 home does not contain bin/java.exe'}
$env:JAVA_HOME=$JavaHome
$env:PATH=(Join-Path $JavaHome 'bin')+';'+$env:PATH
& java -version
& mvn -B -f jshERP-boot/pom.xml '-Dmaven.test.failure.ignore=false' '-DfailIfNoTests=true' $Goal
exit $LASTEXITCODE
