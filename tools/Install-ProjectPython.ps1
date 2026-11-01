param([string]$TargetDirectory,[string]$CacheDirectory)
# Windows PowerShell5.1 / .NET Framework. Current-user toolchain only.
# No SCADA/PLC/HMI/OPC/database processes or configuration are touched here.
$ErrorActionPreference='Stop'

function Get-ProjectPythonPackage {
 $path=Join-Path $PSScriptRoot 'python-windows-package.json'
 $package=[IO.File]::ReadAllText($path,[Text.Encoding]::UTF8)|ConvertFrom-Json
 if($package.schemaVersion -ne 1 -or $package.scope -ne 'current-user' -or
    $package.architecture -ne 'amd64' -or $package.version -ne '3.13.17' -or
    $package.url -ne 'https://www.python.org/ftp/python/3.13.17/python-3.13.17-amd64.exe' -or
    $package.sha256 -cnotmatch '^[0-9a-f]{64}$' -or $package.publisher -ne 'Python Software Foundation' -or
    $package.fileName -ne 'python-3.13.17-amd64.exe' -or $package.targetFolder -ne 'Python313') {
  throw 'Unsupported project Python package specification'
 }
 return $package
}

function Assert-ProjectPythonPlatform {
 if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT -or -not [Environment]::Is64BitOperatingSystem) {
  throw 'This installer requires x64 Windows; no installation attempted'
 }
 if($env:PROCESSOR_ARCHITECTURE -ne 'AMD64' -and $env:PROCESSOR_ARCHITEW6432 -ne 'AMD64') {
  throw 'Expected an AMD64 Windows installation'
 }
 if(-not $env:LOCALAPPDATA){throw 'Current-user LOCALAPPDATA is unavailable'}
}

function Get-ProjectPythonLocalRoot { return [IO.Path]::GetFullPath($env:LOCALAPPDATA).TrimEnd([char[]]'\/') }
function Get-ProjectPythonHash([string]$Path) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
function Assert-ProjectPythonSignature([string]$Path) {
 $signature=Get-AuthenticodeSignature -LiteralPath $Path
 if([string]$signature.Status -ne 'Valid' -or -not $signature.SignerCertificate -or
    $signature.SignerCertificate.Subject -notmatch '(?:^|,\s*)(?:O|CN)=Python Software Foundation(?:,|$)') {
  throw 'Expected a valid Authenticode signature from Python Software Foundation'
 }
}

function Read-ProjectPythonRuntime([string]$PythonPath) {
 # No double quotes inside the native -c argument: Windows PS5.1 quoting.
 $probe="import hashlib,json,pathlib,struct,sys; print(json.dumps(dict(version=list(sys.version_info[:3]),release=sys.version_info.releaselevel,bits=struct.calcsize('P')*8,executable=sys.executable)))"
 $output=@(& $PythonPath '-I' '-B' '-c' $probe)
 if($LASTEXITCODE -ne 0 -or $output.Count -ne 1){throw 'Python standard-library probe failed'}
 return ($output[0]|ConvertFrom-Json)
}

function Assert-ProjectPythonRuntime($Runtime,[string]$PythonPath,[string]$ExactVersion='') {
 if(@($Runtime.version).Count -ne 3 -or $Runtime.version[0] -ne 3 -or $Runtime.version[1] -lt 10 -or
    $Runtime.release -ne 'final' -or $Runtime.bits -ne 64 -or
    -not [IO.Path]::GetFullPath([string]$Runtime.executable).Equals([IO.Path]::GetFullPath($PythonPath),[StringComparison]::OrdinalIgnoreCase)) {
  throw 'Expected a compatible stable x64 Python at the selected path'
 }
 if($ExactVersion -and ([string]::Join('.',[object[]]$Runtime.version) -ne $ExactVersion)) {
  throw 'Installed Python version does not match the verified installer'
 }
}

function Save-ProjectPythonInstaller($Package,[string]$Directory) {
 $null=[IO.Directory]::CreateDirectory($Directory)
 $installer=Join-Path $Directory $Package.fileName
 if(Test-Path -LiteralPath $installer) {
  if((Get-ProjectPythonHash $installer) -ne $Package.sha256){throw 'Cached installer checksum mismatch; file preserved'}
  Assert-ProjectPythonSignature $installer
  return $installer
 }
 $partial=$installer+'.part-'+[Guid]::NewGuid().ToString('N')+'.exe'
 $oldProtocol=[Net.ServicePointManager]::SecurityProtocol
 $ProgressPreference='SilentlyContinue'
 try {
  [Net.ServicePointManager]::SecurityProtocol=$oldProtocol -bor [Net.SecurityProtocolType]::Tls12
  Invoke-WebRequest -UseBasicParsing -Uri $Package.url -OutFile $partial
  if((Get-ProjectPythonHash $partial) -ne $Package.sha256){throw 'Downloaded installer checksum mismatch'}
  Assert-ProjectPythonSignature $partial
  [IO.File]::Move($partial,$installer)
  return $installer
 } finally {
  [Net.ServicePointManager]::SecurityProtocol=$oldProtocol
  if(Test-Path -LiteralPath $partial){Remove-Item -LiteralPath $partial -Force}
 }
}

function Start-ProjectPythonInstaller([string]$Installer,[string]$Directory,[string]$LogPath) {
 # All paths are arguments, never executable command text. No admin launch verb.
 $arguments=@('/quiet','InstallAllUsers=0','PrependPath=0','AssociateFiles=0',
  'Include_launcher=0','InstallLauncherAllUsers=0','Include_pip=0','Include_test=0',
  'Include_doc=0','Include_tcltk=0','Include_dev=0','Include_debug=0','Include_symbols=0',
  'Include_exe=1','Include_lib=1','CompileAll=0',
  ('TargetDir="'+$Directory+'"'),'/log',('"'+$LogPath+'"'))
 $process=Start-Process -FilePath $Installer -ArgumentList $arguments -Wait -PassThru
 return [int]$process.ExitCode
}

function Install-ProjectPython([string]$TargetDirectory,[string]$CacheDirectory) {
 Assert-ProjectPythonPlatform
 $package=Get-ProjectPythonPackage
 $localRoot=Get-ProjectPythonLocalRoot
 if(-not $TargetDirectory){$TargetDirectory=Join-Path $localRoot ('Programs\Python\'+$package.targetFolder)}
 if(-not $CacheDirectory){$CacheDirectory=Join-Path $localRoot 'CodexDownloads\ProjectPython'}
 $target=[IO.Path]::GetFullPath($TargetDirectory).TrimEnd([char[]]'\/')
 $cache=[IO.Path]::GetFullPath($CacheDirectory).TrimEnd([char[]]'\/')
 foreach($path in @($target,$cache)) {
  if($path.Contains('"') -or -not $path.StartsWith($localRoot+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
   throw 'Use a current-user LOCALAPPDATA directory without quote characters'
  }
 }
 if($target.Equals($cache,[StringComparison]::OrdinalIgnoreCase) -or
    $cache.StartsWith($target+[IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) {
  throw 'Keep the installer cache outside the Python target directory'
 }
 $python=Join-Path $target 'python.exe'
 if(Test-Path -LiteralPath $python -PathType Leaf) {
  Assert-ProjectPythonSignature $python
  $runtime=Read-ProjectPythonRuntime $python
  Assert-ProjectPythonRuntime $runtime $python
  return [pscustomobject]@{pythonPath=$python;version=([string]::Join('.',[object[]]$runtime.version));installed=$false;reused=$true;pathChangeRequested=$false}
 }
 if(Test-Path -LiteralPath $target){throw 'Python target directory already exists; preserved without install'}
 $installer=Save-ProjectPythonInstaller $package $cache
 # Recheck the same file immediately before handing it to Windows.
 if((Get-ProjectPythonHash $installer) -ne $package.sha256){throw 'Installer changed after verification'}
 Assert-ProjectPythonSignature $installer
 $log=Join-Path $cache ('install-'+[DateTime]::UtcNow.ToString('yyyyMMddTHHmmssZ')+'.log')
 $exitCode=Start-ProjectPythonInstaller $installer $target $log
 if($exitCode -notin @(0,3010)){throw ('Python installer failed, exit code '+$exitCode+'; no automatic retry or uninstall')}
 if(-not (Test-Path -LiteralPath $python -PathType Leaf)){throw 'Installer did not create the expected interpreter; inspect the local installer log'}
 Assert-ProjectPythonSignature $python
 $runtime=Read-ProjectPythonRuntime $python
 Assert-ProjectPythonRuntime $runtime $python $package.version
 return [pscustomobject]@{pythonPath=$python;version=([string]::Join('.',[object[]]$runtime.version));installed=$true;reused=$false;installerSHA256=$package.sha256;installerExitCode=$exitCode;restartSuggested=($exitCode -eq 3010);pathChangeRequested=$false;installerLog=$log}
}

if($MyInvocation.InvocationName -ne '.') {
 Install-ProjectPython -TargetDirectory $TargetDirectory -CacheDirectory $CacheDirectory | ConvertTo-Json -Depth 5
}
