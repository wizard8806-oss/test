& {
$ErrorActionPreference='Stop'
$groupDirectory=Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'Automatika\RadioServicePilot01'
$groupTemp=$null
function GroupSplitHash([byte[]]$Bytes){
 $h=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($h.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}
 finally{$h.Dispose()}
}
try{
 $oldPath=Join-Path $groupDirectory 'Run-Radio-Service-Collector-01.ps1'
 [byte[]]$oldBytes=[IO.File]::ReadAllBytes($oldPath)
 if((GroupSplitHash $oldBytes) -ne '__OLD_SHA__'){throw 'Original collector differs; existing files preserved'}
 $text=[Text.Encoding]::UTF8.GetString($oldBytes)
 $beforeCatch=@'
__BEFORE_CATCH__
'@
 $afterCatch=@'
__AFTER_CATCH__
'@
 $beforeFatal=@'
__BEFORE_FATAL__
'@
 $afterFatal=@'
__AFTER_FATAL__
'@
 $beforeCatch=$beforeCatch.Replace("`r`n","`n");$afterCatch=$afterCatch.Replace("`r`n","`n")
 $beforeFatal=$beforeFatal.Replace("`r`n","`n");$afterFatal=$afterFatal.Replace("`r`n","`n")
 if([regex]::Matches($text,[regex]::Escape($beforeCatch)).Count -ne 1 -or [regex]::Matches($text,[regex]::Escape($beforeFatal)).Count -ne 1){throw 'Collector patch does not match'}
 [byte[]]$newBytes=[Text.Encoding]::UTF8.GetBytes($text.Replace($beforeCatch,$afterCatch).Replace($beforeFatal,$afterFatal))
 if((GroupSplitHash $newBytes) -ne '__NEW_SHA__'){throw 'New collector checksum mismatch'}
 $newPath=Join-Path $groupDirectory 'Run-Radio-Service-Collector-02.ps1'
 if([IO.File]::Exists($newPath) -and (GroupSplitHash ([IO.File]::ReadAllBytes($newPath))) -ne '__NEW_SHA__'){throw 'New collector file differs; preserved'}
 $configPath=Join-Path $groupDirectory 'stations.json'
 [byte[]]$configBytes=[IO.File]::ReadAllBytes($configPath)
 $config=[Text.Encoding]::UTF8.GetString($configBytes)|ConvertFrom-Json
 if($config.Schema -ne 1 -or @($config.Groups).Count -ne 1 -or @($config.Stations).Count -ne 1){throw 'Expected the single-station pilot configuration; preserved'}
 $station=$config.Stations[0];$connection=$config.Groups[0]
 if($station.Id -ne 'station-001' -or $station.Imei -ne '863906061228379' -or $station.GroupId -ne $connection.Id){throw 'Station configuration differs; preserved'}
 $inputId=(Read-Host 'NEW ServiceDiag group ID (not Main7058)').Trim()
 [long]$newLogin=0
 if($inputId -notmatch '^[1-9][0-9]{0,15}$' -or -not [long]::TryParse($inputId,[ref]$newLogin) -or $newLogin -eq 7058){throw 'A separate Service group ID is required; files preserved'}
 $lockPath=Join-Path ([string]$station.RadioDataDirectory) 'collector.lock'
 $probe=$null
 try{$probe=[IO.File]::Open($lockPath,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}
 catch{throw 'Stop the existing radio collector before changing the group'}
 finally{if($null -ne $probe){$probe.Dispose()}}
 if(-not [IO.File]::Exists($newPath)){
  $groupTemp=$newPath+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
  [IO.File]::WriteAllBytes($groupTemp,$newBytes);[IO.File]::Move($groupTemp,$newPath);$groupTemp=$null
 }
 $connection.Id='teleofis-service-'+[string]$newLogin
 $connection.Login=$newLogin;$connection.Server='hub.m2m24.ru';$connection.Port=7000
 $station.GroupId=$connection.Id
 [byte[]]$updated=[Text.Encoding]::UTF8.GetBytes(($config|ConvertTo-Json -Depth 12))
 $backup=$configPath+'.before-service-group-'+[Guid]::NewGuid().ToString('N')+'.bak'
 $groupTemp=$configPath+'.'+[Guid]::NewGuid().ToString('N')+'.tmp'
 [IO.File]::WriteAllBytes($groupTemp,$updated);[IO.File]::Replace($groupTemp,$configPath,$backup);$groupTemp=$null
 Write-Host ('READY: Service group '+$newLogin+'. Starting collector02.') -ForegroundColor Green
 & ([scriptblock]::Create([IO.File]::ReadAllText($newPath,[Text.Encoding]::UTF8))) -StationId 'station-001' -ConfigPath $configPath
}catch{Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red}
finally{if($groupTemp -and [IO.File]::Exists($groupTemp)){[IO.File]::Delete($groupTemp)}}
};
