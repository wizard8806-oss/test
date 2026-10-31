& {
$ErrorActionPreference='Stop'
$xmlDirectory=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'Automatika\RadioServicePilot01'
$xmlPath=Join-Path $xmlDirectory 'Run-Radio-Service-Collector-01.ps1'
$xmlTemp=$null
function XmlRepairHash([byte[]]$Bytes){
 $h=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($h.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}
 finally{$h.Dispose()}
}
try{
 [byte[]]$xmlBytes=[IO.File]::ReadAllBytes($xmlPath)
 $xmlHash=XmlRepairHash $xmlBytes
 if($xmlHash -eq 'd09c645ace7a060f5d78e9d8b026ba61245f8607e9c07e772deeea5165d18502'){
  $xmlText=[Text.Encoding]::UTF8.GetString($xmlBytes)
  $xmlOld="Add-Type -TypeDefinition @'"
  $xmlNew=@'
$svcTypeOptions=@{}
if($PSVersionTable.PSVersion.Major -lt 6){
 $svcTypeOptions.ReferencedAssemblies=@('System.dll','System.Core.dll','System.Xml.dll')
}
Add-Type @svcTypeOptions -TypeDefinition @'
'@
  $xmlNew=$xmlNew.Replace("`r`n","`n")
  if([regex]::Matches($xmlText,[regex]::Escape($xmlOld)).Count -ne 1){throw 'Patch context does not match; original preserved'}
  [byte[]]$xmlFixed=[Text.Encoding]::UTF8.GetBytes($xmlText.Replace($xmlOld,$xmlNew))
  if((XmlRepairHash $xmlFixed) -ne 'e334ef94c55230352441ba44471598faa2212e4dcfa7217a46d2f9d952624585'){throw 'Patch checksum mismatch; original preserved'}
  $xmlBackup=$xmlPath+'.before-xml-fix.bak'
  if([IO.File]::Exists($xmlBackup) -and (XmlRepairHash ([IO.File]::ReadAllBytes($xmlBackup))) -ne $xmlHash){throw 'Backup differs; existing files preserved'}
  $xmlTemp=$xmlPath+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
  [IO.File]::WriteAllBytes($xmlTemp,$xmlFixed)
  if([IO.File]::Exists($xmlBackup)){[IO.File]::Replace($xmlTemp,$xmlPath,[NullString]::Value)}
  else{[IO.File]::Replace($xmlTemp,$xmlPath,$xmlBackup)}
  $xmlTemp=$null
 }elseif($xmlHash -ne 'e334ef94c55230352441ba44471598faa2212e4dcfa7217a46d2f9d952624585'){
  throw 'Collector file changed; original preserved'
 }
 if((XmlRepairHash ([IO.File]::ReadAllBytes($xmlPath))) -ne 'e334ef94c55230352441ba44471598faa2212e4dcfa7217a46d2f9d952624585'){throw 'Fixed file verification failed'}
 Write-Host 'READY: XML assembly reference fixed. Starting Service collector.' -ForegroundColor Green
 & ([scriptblock]::Create([IO.File]::ReadAllText($xmlPath,[Text.Encoding]::UTF8))) -StationId 'station-001' -ConfigPath (Join-Path $xmlDirectory 'stations.json')
}catch{Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red}
finally{if($xmlTemp -and [IO.File]::Exists($xmlTemp)){[IO.File]::Delete($xmlTemp)}}
};
