& {
$ErrorActionPreference='Stop'
$serviceTarget=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'Automatika\RadioServicePilot01'
$serviceBundle=@'
__BUNDLE__
'@
function ServiceInstallHash([byte[]]$Bytes){
 $h=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($h.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}
 finally{$h.Dispose()}
}
try{
 [byte[]]$bundle=[Convert]::FromBase64String($serviceBundle)
 if((ServiceInstallHash $bundle) -ne '__BUNDLE_SHA__'){throw 'Transfer checksum mismatch. Copy the complete block again.'}
 Add-Type -AssemblyName System.IO.Compression
 $mem=[IO.MemoryStream]::new($bundle)
 $zip=[IO.Compression.ZipArchive]::new($mem,[IO.Compression.ZipArchiveMode]::Read,$false)
 $payload=@{}
 try{
  if($zip.Entries.Count -ne 2){throw 'Invalid service bundle'}
  foreach($entry in $zip.Entries){
   if($entry.FullName -notin @('Run-Radio-Service-Collector-01.ps1','stations.json') -or $payload.ContainsKey($entry.FullName) -or $entry.Length -gt 131072){throw 'Invalid service bundle entry'}
   $stream=$entry.Open();$part=[IO.MemoryStream]::new()
   try{$stream.CopyTo($part);$payload[$entry.FullName]=$part.ToArray()}
   finally{$stream.Dispose();$part.Dispose()}
  }
 }finally{$zip.Dispose();$mem.Dispose()}
 foreach($name in $payload.Keys){
  $path=Join-Path $serviceTarget $name
  if(Test-Path -LiteralPath $path){
   if(-not (Test-Path -LiteralPath $path -PathType Leaf) -or (ServiceInstallHash ([IO.File]::ReadAllBytes($path))) -ne (ServiceInstallHash $payload[$name])){throw ('Existing file differs; preserved: '+$path)}
  }
 }
 $null=[IO.Directory]::CreateDirectory($serviceTarget)
 foreach($name in $payload.Keys){
  $path=Join-Path $serviceTarget $name
  if(-not (Test-Path -LiteralPath $path)){
   $temp=$path+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
   try{[IO.File]::WriteAllBytes($temp,$payload[$name]);[IO.File]::Move($temp,$path)}
   finally{if([IO.File]::Exists($temp)){[IO.File]::Delete($temp)}}
  }
  if((ServiceInstallHash ([IO.File]::ReadAllBytes($path))) -ne (ServiceInstallHash $payload[$name])){throw 'Installed file verification failed'}
 }
 Write-Host ('SAVED: '+$serviceTarget) -ForegroundColor Green
 $collector=Join-Path $serviceTarget 'Run-Radio-Service-Collector-01.ps1'
 $config=Join-Path $serviceTarget 'stations.json'
 & ([scriptblock]::Create([IO.File]::ReadAllText($collector,[Text.Encoding]::UTF8))) -StationId 'station-001' -ConfigPath $config
}catch{Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red}
};
