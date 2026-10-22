param([string]$Sdk='C:\Android\Sdk', [string]$Java='C:\Program Files\Microsoft\jdk-21.0.9.10-hotspot')
$ErrorActionPreference='Stop'
$env:JAVA_HOME=$Java
$root=Split-Path $PSScriptRoot -Parent
$build=Join-Path $root 'private\helper-build'
$cache=Join-Path $root 'cache'
New-Item -ItemType Directory -Force -Path $build,"$build\classes","$build\dex",$cache | Out-Null
$jar=Join-Path $Sdk 'platforms\android-35\android.jar'
$bt=Join-Path $Sdk 'build-tools\35.0.0'
& "$Java\bin\javac.exe" -source 8 -target 8 -classpath $jar -d "$build\classes" "$PSScriptRoot\ClipboardActivity.java"
if($LASTEXITCODE -ne 0){throw 'javac failed'}
$classes=@(Get-ChildItem -LiteralPath "$build\classes" -Recurse -Filter '*.class' | ForEach-Object FullName)
& "$bt\d8.bat" --lib $jar --min-api 24 --output "$build\dex" @classes
if($LASTEXITCODE -ne 0){throw 'd8 failed'}
$key=Join-Path $root 'private\helper-signing.p12'
if(-not (Test-Path -LiteralPath $key)) {
    & "$Java\bin\keytool.exe" -genkeypair -keystore $key -storepass android -keypass android -alias helper -dname 'CN=AndroidCoolNet Clipboard Helper' -keyalg RSA -validity 10000
    if($LASTEXITCODE -ne 0){throw 'keytool failed'}
}
& "$bt\aapt2.exe" link -I $jar --manifest "$PSScriptRoot\AndroidManifest.xml" -o "$build\unsigned.apk"
if($LASTEXITCODE -ne 0){throw 'aapt2 failed'}
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip=[IO.Compression.ZipFile]::Open("$build\unsigned.apk",[IO.Compression.ZipArchiveMode]::Update)
try{[void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,"$build\dex\classes.dex",'classes.dex')}finally{$zip.Dispose()}
& "$bt\zipalign.exe" -f 4 "$build\unsigned.apk" "$build\aligned.apk"
if($LASTEXITCODE -ne 0){throw 'zipalign failed'}
$apk=Join-Path $cache 'androidcoolnet-clipboard.apk'
& "$bt\apksigner.bat" sign --ks $key --ks-pass pass:android --out $apk "$build\aligned.apk"
if($LASTEXITCODE -ne 0){throw 'Signing failed'}
& "$bt\apksigner.bat" verify $apk
if($LASTEXITCODE -ne 0){throw 'Signature verification failed'}
$info=@{package='io.github.gelinzhankai.androidcoolnet.clipboard';file='androidcoolnet-clipboard.apk';sha256=(Get-FileHash -LiteralPath $apk -Algorithm SHA256).Hash.ToLowerInvariant()}
[IO.File]::WriteAllText((Join-Path $root 'config\clipboard-helper.json'), ($info | ConvertTo-Json)+"`n", [Text.UTF8Encoding]::new($false))
Get-Item -LiteralPath $apk | Select-Object Name,Length
