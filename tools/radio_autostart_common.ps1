# Shared by the staged Windows radio package. Loading this file performs no work.
function Assert-RadioAutoWindows {
 if([Environment]::OSVersion.Platform -ne [PlatformID]::Win32NT){throw 'RADIOAUTO_WINDOWS_REQUIRED'}
}
function Assert-RadioAutoAdministrator {
 Assert-RadioAutoWindows
 if(-not [Environment]::Is64BitProcess){throw 'RADIOAUTO_64BIT_POWERSHELL_REQUIRED'}
 $identity=[Security.Principal.WindowsIdentity]::GetCurrent()
 $principal=[Security.Principal.WindowsPrincipal]::new($identity)
 if(-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)){throw 'RADIOAUTO_ADMINISTRATOR_REQUIRED'}
}
function Assert-RadioAutoOrdinaryPath([string]$Path){
 $item=[IO.Path]::GetFullPath($Path)
 while($item){
  if(Test-Path -LiteralPath $item){
   if(((Get-Item -LiteralPath $item -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0){throw 'RADIOAUTO_REPARSE_POINT'}
  }
  $parent=[IO.Path]::GetDirectoryName($item)
  if($parent -eq $item){break};$item=$parent
 }
}
function Get-RadioAutoHash([string]$Path){
 Assert-RadioAutoOrdinaryPath $Path
 return (Get-FileHash -LiteralPath $Path -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
}
function Get-RadioAutoConfig([string]$Path,[string]$StationId){
 Assert-RadioAutoOrdinaryPath $Path
 if((Get-Item -LiteralPath $Path -ErrorAction Stop).Length -gt 131072){throw 'RADIOAUTO_CONFIG_TOO_LARGE'}
 $config=[IO.File]::ReadAllText($Path,[Text.Encoding]::UTF8)|ConvertFrom-Json
 if($config.Schema -ne 1 -or @($config.Groups).Count -ne 1 -or @($config.Stations).Count -ne 1){throw 'RADIOAUTO_SINGLE_STATION_REQUIRED'}
 if(@($config.PSObject.Properties.Name|Where-Object {$_ -notin @('Schema','Groups','Stations')}).Count){throw 'RADIOAUTO_CONFIG_UNKNOWN_FIELDS'}
 $group=$config.Groups[0];$station=$config.Stations[0]
 if(@($group.PSObject.Properties.Name|Where-Object {$_ -notin @('Id','Server','Port','Login')}).Count -or
    @($station.PSObject.Properties.Name|Where-Object {$_ -notin @('Id','Name','GroupId','Imei','RadioDataDirectory','PollMilliseconds','EquipmentProfile','ExpectedPlcMapVersion')}).Count){throw 'RADIOAUTO_CONFIG_UNKNOWN_FIELDS'}
 if($StationId -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$' -or $station.Id -cne $StationId -or $station.GroupId -cne $group.Id -or
    $group.Id -cne 'teleofis-service-9336' -or $group.Server -ine 'hub.m2m24.ru' -or [int]$group.Port -ne 7000 -or [long]$group.Login -ne 9336){throw 'RADIOAUTO_SERVICE9336_REQUIRED'}
 if($station.Imei -notmatch '^[0-9]{15}$' -or [int]$station.PollMilliseconds -lt 5000 -or [int]$station.PollMilliseconds -gt 3600000 -or
    -not [IO.Path]::IsPathRooted([string]$station.RadioDataDirectory)){throw 'RADIOAUTO_STATION_INVALID'}
 Assert-RadioAutoOrdinaryPath ([string]$station.RadioDataDirectory)
 return $config
}
function New-RadioAutoPrivateDirectory([string]$Path){
 Assert-RadioAutoAdministrator;Assert-RadioAutoOrdinaryPath $Path
 if(Test-Path -LiteralPath $Path){throw 'RADIOAUTO_EXISTING_DIRECTORY_PRESERVED'}
 $null=[IO.Directory]::CreateDirectory($Path)
 $acl=[Security.AccessControl.DirectorySecurity]::new();$acl.SetAccessRuleProtection($true,$false)
 $acl.SetOwner([Security.Principal.SecurityIdentifier]::new('S-1-5-32-544'))
 foreach($sid in @('S-1-5-18','S-1-5-32-544')){
  $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new([Security.Principal.SecurityIdentifier]::new($sid),'FullControl','ContainerInherit, ObjectInherit','None','Allow'))
 }
 Set-Acl -LiteralPath $Path -AclObject $acl -ErrorAction Stop
 Assert-RadioAutoPrivateAcl $Path
}
function Assert-RadioAutoPrivateAcl([string]$Path){
 $actual=Get-Acl -LiteralPath $Path -ErrorAction Stop
 if((Get-Item -LiteralPath $Path -Force).PSIsContainer -and -not $actual.AreAccessRulesProtected){throw 'RADIOAUTO_PRIVATE_ACL_FAILED'}
 foreach($rule in $actual.Access){
  if($rule.AccessControlType -ne 'Allow' -or $rule.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value -notin @('S-1-5-18','S-1-5-32-544')){throw 'RADIOAUTO_PRIVATE_ACL_FAILED'}
 }
}
function Protect-RadioAutoSecret([Security.SecureString]$Value){
 Assert-RadioAutoWindows;Add-Type -AssemblyName System.Security
 $pointer=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value);$raw=$null
 try{
  $raw=[Text.Encoding]::UTF8.GetBytes([Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer))
  $protected=[Security.Cryptography.ProtectedData]::Protect($raw,[Text.Encoding]::UTF8.GetBytes('Automatika.RadioAutostart03'),[Security.Cryptography.DataProtectionScope]::LocalMachine)
  return [Convert]::ToBase64String($protected)
 }finally{
  [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
  if($null -ne $raw){[Array]::Clear($raw,0,$raw.Length)}
 }
}
function Read-RadioAutoSecret([string]$Path,[string]$Name){
 Assert-RadioAutoWindows;Assert-RadioAutoOrdinaryPath $Path;Add-Type -AssemblyName System.Security
 if($Name -notin @('Cloud','Modem') -or (Get-Item -LiteralPath $Path -ErrorAction Stop).Length -gt 65536){throw 'RADIOAUTO_CREDENTIAL_FORMAT'}
 $record=[IO.File]::ReadAllText($Path,[Text.Encoding]::UTF8)|ConvertFrom-Json
 if($record.Schema -ne 1 -or $record.Scope -cne 'LocalMachine'){throw 'RADIOAUTO_CREDENTIAL_FORMAT'}
 $raw=$null;$characters=$null;$result=[Security.SecureString]::new()
 try{
  $raw=[Security.Cryptography.ProtectedData]::Unprotect([Convert]::FromBase64String([string]$record.$Name),[Text.Encoding]::UTF8.GetBytes('Automatika.RadioAutostart03'),[Security.Cryptography.DataProtectionScope]::LocalMachine)
  # Passwords accepted by the existing modem transport are ASCII; a cloud
  # password may be Unicode. Decode only in memory, never to a file or log.
  $characters=[Text.Encoding]::UTF8.GetChars($raw)
  foreach($character in $characters){$result.AppendChar($character)}
  $result.MakeReadOnly();return $result
 }catch{$result.Dispose();throw 'RADIOAUTO_CREDENTIAL_UNPROTECT_FAILED'}
 finally{
  if($null -ne $raw){[Array]::Clear($raw,0,$raw.Length)}
  if($null -ne $characters){[Array]::Clear($characters,0,$characters.Length)}
 }
}
function Write-RadioAutoFailure([string]$Path,[string]$Code,$Failure){
 $kind=$null;$number=$null
 if($null -ne $Failure){$base=$Failure.GetBaseException();$kind=$base.GetType().FullName;$number=('0x{0:X8}' -f $base.HResult)}
 if($Code -notmatch '^[A-Z][A-Z0-9_]{0,79}$'){$Code='RADIOAUTO_LOCAL_FAILURE'}
 $report=[ordered]@{UTC=[DateTime]::UtcNow.ToString('o');PID=$PID;Code=$Code;ExceptionType=$kind;HResult=$number}
 try{[IO.File]::WriteAllText($Path,($report|ConvertTo-Json -Compress),[Text.UTF8Encoding]::new($false))}catch{}
 Write-Host ('ERROR: '+$Code+'; type='+$kind+'; HResult='+$number) -ForegroundColor Red
}
function Get-RadioAutoTaskXml([string]$Root,[string]$PowerShell,[string]$StationId){
 foreach($value in @($Root,$PowerShell,$StationId)){if($value -match '["\r\n]'){throw 'RADIOAUTO_TASK_ARGUMENT_INVALID'}}
 if($StationId -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$'){throw 'RADIOAUTO_STATION_INVALID'}
 $arguments='-NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "'+(Join-Path $Root 'Run-Radio-Service-Collector-03.ps1')+'" -StationId "'+$StationId+'" -ConfigPath "'+(Join-Path $Root 'stations.json')+'" -CredentialPath "'+(Join-Path $Root 'credentials.json')+'" -DiagnosticPath "'+(Join-Path $Root 'last-error.json')+'"'
 $command=[Security.SecurityElement]::Escape($PowerShell);$argsXml=[Security.SecurityElement]::Escape($arguments);$working=[Security.SecurityElement]::Escape($Root)
 return @"
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
 <RegistrationInfo><Description>Automatika radio Service9336, single-station pilot03</Description></RegistrationInfo>
 <Triggers><BootTrigger><Enabled>true</Enabled><Delay>PT30S</Delay></BootTrigger></Triggers>
 <Principals><Principal id="RadioSystem"><UserId>S-1-5-18</UserId><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
 <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowHardTerminate>true</AllowHardTerminate><StartWhenAvailable>true</StartWhenAvailable><RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable><IdleSettings><StopOnIdleEnd>false</StopOnIdleEnd><RestartOnIdle>false</RestartOnIdle></IdleSettings><AllowStartOnDemand>true</AllowStartOnDemand><Enabled>false</Enabled><Hidden>true</Hidden><RunOnlyIfIdle>false</RunOnlyIfIdle><WakeToRun>false</WakeToRun><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><Priority>7</Priority><RestartOnFailure><Interval>PT1M</Interval><Count>3</Count></RestartOnFailure></Settings>
 <Actions Context="RadioSystem"><Exec><Command>$command</Command><Arguments>$argsXml</Arguments><WorkingDirectory>$working</WorkingDirectory></Exec></Actions>
</Task>
"@
}
