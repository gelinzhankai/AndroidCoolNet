param([string]$Sdk='C:\Android\Sdk',[string]$Java='C:\Program Files\Microsoft\jdk-21.0.9.10-hotspot')
$ErrorActionPreference='Stop'
$env:JAVA_HOME=$Java
$build=Join-Path $PSScriptRoot 'artifacts\probe-build'
New-Item -ItemType Directory -Path $build,(Join-Path $build 'classes'),(Join-Path $build 'dex') -Force | Out-Null
$jar=Join-Path $Sdk 'platforms\android-35\android.jar'
$bt=Join-Path $Sdk 'build-tools\35.0.0'
& "$Java\bin\javac.exe" -source 8 -target 8 -classpath $jar -d "$build\classes" "$PSScriptRoot\probe\ProbeActivity.java"
if($LASTEXITCODE -ne 0){throw 'javac failed'}
$classes=@(Get-ChildItem -LiteralPath "$build\classes" -Recurse -Filter '*.class' | ForEach-Object FullName)
& "$bt\d8.bat" --lib $jar --min-api 24 --output "$build\dex" @classes
if($LASTEXITCODE -ne 0){throw 'd8 failed'}
$key=Join-Path $build 'test-only.p12'
if(-not (Test-Path -LiteralPath $key)) {
    & "$Java\bin\keytool.exe" -genkeypair -keystore $key -storepass android -keypass android -alias test -dname 'CN=Local Emulator Test Only' -keyalg RSA -validity 30
}
Add-Type -AssemblyName System.IO.Compression.FileSystem
foreach($kind in @('allowed','excluded')) {
    $package=if($kind -eq 'allowed'){'com.google.androidsetupprobe'}else{'test.androidsetup.excluded'}
    $manifest="<manifest xmlns:android=`"http://schemas.android.com/apk/res/android`" package=`"$package`" android:versionCode=`"1`" android:versionName=`"1`"><uses-sdk android:minSdkVersion=`"24`" android:targetSdkVersion=`"35`"/><uses-permission android:name=`"android.permission.INTERNET`"/><application android:label=`"Local $kind probe`" android:theme=`"@android:style/Theme.Material.Light.NoActionBar`" android:usesCleartextTraffic=`"true`"><activity android:name=`"test.probe.ProbeActivity`" android:exported=`"true`"/></application></manifest>"
    [IO.File]::WriteAllText("$build\$kind-manifest.xml",$manifest)
    & "$bt\aapt2.exe" link -I $jar --manifest "$build\$kind-manifest.xml" -o "$build\$kind-unsigned.apk"
    if($LASTEXITCODE -ne 0){throw 'aapt2 failed'}
    $zip=[IO.Compression.ZipFile]::Open("$build\$kind-unsigned.apk",[IO.Compression.ZipArchiveMode]::Update)
    try{[void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,"$build\dex\classes.dex",'classes.dex')}finally{$zip.Dispose()}
    & "$bt\zipalign.exe" -f 4 "$build\$kind-unsigned.apk" "$build\$kind-aligned.apk"
    & "$bt\apksigner.bat" sign --ks $key --ks-pass pass:android --out "$build\$kind.apk" "$build\$kind-aligned.apk"
    if($LASTEXITCODE -ne 0){throw 'Signing failed'}
}
Write-Output "Probes: $build"
