param(
 [ValidateSet('Prepare','Enable','Disable','Remove')][string]$Mode='Prepare',
 [string]$SourceConfigPath='C:\ProgramData\Automatika\RadioServicePilot01\stations.json',
 [string]$StationId='station-001',
 [switch]$PublicationVerified
)
$ErrorActionPreference='Stop'
$radioPins=__RADIOAUTOPINS__
$radioPayload=@{}
foreach($name in $radioPins.Keys){
 $radioSource=Join-Path $PSScriptRoot $name
 if((Get-Item -LiteralPath $radioSource -ErrorAction Stop).Length -gt 262144){throw 'RADIOAUTO_PACKAGE_TOO_LARGE'}
 $radioBytes=[IO.File]::ReadAllBytes($radioSource);$radioHash=[Security.Cryptography.SHA256]::Create()
 try{$radioDigest=([BitConverter]::ToString($radioHash.ComputeHash($radioBytes))).Replace('-','').ToLowerInvariant()}finally{$radioHash.Dispose()}
 if($radioDigest -cne $radioPins[$name]){throw 'RADIOAUTO_PACKAGE_HASH_MISMATCH'}
 $radioPayload[$name]=$radioBytes
}
. ([scriptblock]::Create([Text.Encoding]::UTF8.GetString($radioPayload['Radio-Autostart.Common.ps1'])))
Assert-RadioAutoAdministrator
$radioRoot=Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'AutomatikaRadioAutostart03'
$radioTaskName='Automatika-Radio-Service03'
$radioConfig=Join-Path $radioRoot 'stations.json'
$radioCredential=Join-Path $radioRoot 'credentials.json'
$radioPowerShell=Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
Assert-RadioAutoOrdinaryPath $radioRoot
if($Mode -eq 'Prepare'){
 if(Get-ScheduledTask -TaskName $radioTaskName -TaskPath '\' -ErrorAction SilentlyContinue){throw 'RADIOAUTO_EXISTING_TASK_PRESERVED'}
 if(Test-Path -LiteralPath $radioRoot){throw 'RADIOAUTO_EXISTING_DIRECTORY_PRESERVED'}
 $radioSourceConfigHash=Get-RadioAutoHash $SourceConfigPath
 $radioParsed=Get-RadioAutoConfig $SourceConfigPath $StationId
 New-RadioAutoPrivateDirectory $radioRoot
 $radioCloud=$null;$radioModem=$null
 try{
  foreach($name in $radioPins.Keys){[IO.File]::WriteAllBytes((Join-Path $radioRoot $name),$radioPayload[$name])}
  foreach($name in $radioPins.Keys){if((Get-RadioAutoHash (Join-Path $radioRoot $name)) -cne $radioPins[$name]){throw 'RADIOAUTO_COPIED_FILE_MISMATCH'}}
  [IO.File]::Copy($SourceConfigPath,$radioConfig,$false)
  if((Get-RadioAutoHash $radioConfig) -cne $radioSourceConfigHash -or (Get-RadioAutoHash $SourceConfigPath) -cne $radioSourceConfigHash){throw 'RADIOAUTO_SOURCE_CONFIG_CHANGED'}
  $radioCloud=Read-Host 'M2M24 Service9336 password (local encrypted storage)' -AsSecureString
  $radioModem=Read-Host 'TELEOFIS modem password (local encrypted storage)' -AsSecureString
  $radioStore=[ordered]@{Schema=1;Scope='LocalMachine';Cloud=(Protect-RadioAutoSecret $radioCloud);Modem=(Protect-RadioAutoSecret $radioModem)}
  [IO.File]::WriteAllText($radioCredential,($radioStore|ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false))
  $radioState=[ordered]@{Schema=1;StationId=$StationId;ConfigSHA256=(Get-RadioAutoHash $radioConfig);RuntimeHashes=$radioPins;TaskName=$radioTaskName}
  [IO.File]::WriteAllText((Join-Path $radioRoot 'installation.json'),($radioState|ConvertTo-Json -Depth 4),[Text.UTF8Encoding]::new($false))
  $radioXml=Get-RadioAutoTaskXml $radioRoot $radioPowerShell $StationId
  Register-ScheduledTask -TaskName $radioTaskName -TaskPath '\' -Xml $radioXml -User 'SYSTEM' -ErrorAction Stop|Out-Null
  Write-Host ('PREPARED_DISABLED: '+$radioTaskName+'; '+$radioRoot)
 }finally{
  if($null -ne $radioCloud){$radioCloud.Dispose()};if($null -ne $radioModem){$radioModem.Dispose()}
 }
 return
}
foreach($name in $radioPins.Keys){
 if((Get-RadioAutoHash (Join-Path $radioRoot $name)) -cne $radioPins[$name]){throw 'RADIOAUTO_INSTALLED_FILE_CHANGED'}
}
Assert-RadioAutoPrivateAcl $radioRoot
foreach($name in @('Run-Radio-Service-Collector-03.ps1','Radio-Autostart.Common.ps1','stations.json','credentials.json','installation.json')){
 Assert-RadioAutoPrivateAcl (Join-Path $radioRoot $name)
}
$radioState=[IO.File]::ReadAllText((Join-Path $radioRoot 'installation.json'))|ConvertFrom-Json
if($radioState.StationId -cne $StationId -or $radioState.ConfigSHA256 -cne (Get-RadioAutoHash $radioConfig)){throw 'RADIOAUTO_INSTALLED_CONFIG_CHANGED'}
$radioParsed=Get-RadioAutoConfig $radioConfig $StationId
$radioTask=Get-ScheduledTask -TaskName $radioTaskName -TaskPath '\' -ErrorAction Stop
$radioExpected=[xml](Get-RadioAutoTaskXml $radioRoot $radioPowerShell $StationId)
$radioNs=[Xml.XmlNamespaceManager]::new($radioExpected.NameTable);$radioNs.AddNamespace('t',$radioExpected.DocumentElement.NamespaceURI)
$radioExpectedArgs=$radioExpected.SelectSingleNode('//t:Exec/t:Arguments',$radioNs).InnerText
$radioPrincipalSid=[string]$radioTask.Principal.UserId
if($radioPrincipalSid -notmatch '^S-1-'){
 try{$radioPrincipalSid=[Security.Principal.NTAccount]::new($radioPrincipalSid).Translate([Security.Principal.SecurityIdentifier]).Value}
 catch{throw 'RADIOAUTO_UNEXPECTED_TASK_PRESERVED'}
}
if(@($radioTask.Actions).Count -ne 1 -or $radioTask.Actions[0].Execute -ine $radioPowerShell -or
   $radioTask.Actions[0].Arguments -cne $radioExpectedArgs -or $radioTask.Actions[0].WorkingDirectory -ine $radioRoot -or
   $radioPrincipalSid -cne 'S-1-5-18'){throw 'RADIOAUTO_UNEXPECTED_TASK_PRESERVED'}
if($Mode -eq 'Enable'){
 if(-not $PublicationVerified){throw 'RADIOAUTO_PUBLICATION_VALIDATION_REQUIRED'}
 if($radioTask.State -eq 'Running'){Write-Host 'ALREADY_RUNNING';return}
 # The collector also takes this lock before opening any cloud connection.
 $radioOutput=[string]$radioParsed.Stations[0].RadioDataDirectory
 if(-not [IO.Directory]::Exists($radioOutput)){throw 'RADIOAUTO_OUTPUT_DIRECTORY_MISSING'}
 $radioLock=[IO.File]::Open((Join-Path $radioOutput 'collector.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
 $radioLock.Dispose()
 Enable-ScheduledTask -TaskName $radioTaskName -TaskPath '\' -ErrorAction Stop|Out-Null
 Start-ScheduledTask -TaskName $radioTaskName -TaskPath '\' -ErrorAction Stop
 Write-Host 'START_REQUESTED: verify PID, seq and status; this is not a runtime PASS'
 return
}
Disable-ScheduledTask -TaskName $radioTaskName -TaskPath '\' -ErrorAction Stop|Out-Null
if($radioTask.State -eq 'Running'){
 $radioStop=Join-Path ([string]$radioParsed.Stations[0].RadioDataDirectory) 'radio.stop'
 [IO.File]::WriteAllText($radioStop,'',[Text.UTF8Encoding]::new($false))
 $radioWait=[Diagnostics.Stopwatch]::StartNew()
 do{
  Start-Sleep -Milliseconds 250
  $radioTask=Get-ScheduledTask -TaskName $radioTaskName -TaskPath '\' -ErrorAction Stop
 }while($radioTask.State -eq 'Running' -and $radioWait.Elapsed.TotalSeconds -lt 90)
 if($radioTask.State -eq 'Running'){throw 'RADIOAUTO_STOP_PENDING_TASK_DISABLED'}
}
if($Mode -eq 'Remove'){
 Unregister-ScheduledTask -TaskName $radioTaskName -TaskPath '\' -Confirm:$false -ErrorAction Stop
 Write-Host 'TASK_REMOVED: runtime/credentials and station files preserved for rollback'
}else{Write-Host 'TASK_DISABLED: runtime and station files preserved'}
