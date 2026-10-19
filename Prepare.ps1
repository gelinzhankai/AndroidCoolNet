param([string]$DownloadProxy)
$ErrorActionPreference='Stop'
[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12
$root=$PSScriptRoot
$cache=Join-Path $root 'cache'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
function Get-VerifiedFile([string]$Url,[string]$Name,[string]$SHA256) {
    $path=Join-Path $cache $Name
    if (-not (Test-Path -LiteralPath $path)) {
        $opts=@{Uri=$Url;OutFile=$path;UseBasicParsing=$true}
        if($DownloadProxy){$opts.Proxy=$DownloadProxy}
        Invoke-WebRequest @opts
    }
    if((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $SHA256){throw "Hash mismatch: $Name"}
    return $path
}
$zip=Get-VerifiedFile 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip' 'python-3.12.10-embed-amd64.zip' '4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3'
$wheel=Get-VerifiedFile 'https://files.pythonhosted.org/packages/86/bf/899e81e4cce32febab4fb42bb97dcdf66bc135272882d1987881a4b519e9/pyyaml-6.0.3-cp312-cp312-win_amd64.whl' 'pyyaml-6.0.3-cp312-cp312-win_amd64.whl' '5fcd34e47f6e0b794d17de1b4ff496c00986e1c83f7ab2fb8fcfe9616ff7477b'
$runtime=Join-Path $root 'runtime'
if(-not (Test-Path -LiteralPath (Join-Path $runtime 'python.exe'))){Expand-Archive -LiteralPath $zip -DestinationPath $runtime}
Add-Type -AssemblyName System.IO.Compression.FileSystem
if(-not (Test-Path -LiteralPath (Join-Path $runtime 'yaml'))){[IO.Compression.ZipFile]::ExtractToDirectory($wheel,$runtime)}
[IO.File]::WriteAllText((Join-Path $runtime 'python312._pth'),"python312.zip`r`n.`r`n..`r`n",[Text.Encoding]::ASCII)
& (Join-Path $runtime 'python.exe') -X utf8 -c 'import yaml; print("Portable runtime ready; PyYAML " + yaml.__version__)'
if($LASTEXITCODE -ne 0){throw 'Runtime verification failed'}
Write-Output 'Ready. Run install.cmd. ADB must be available on PATH or in platform-tools.'
