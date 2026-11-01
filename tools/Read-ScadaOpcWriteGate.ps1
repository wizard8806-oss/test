param([Parameter(Mandatory=$true)][string]$Path)
# Read-only, exact-profile probe. Field236 was verified using the hash-checked
# Editor2.6.15 loader and Boolean RTTI, not guessed from a trailing byte.
# Only the reviewed localhost/InSAT profile and its one-byte gate change are
# supported. Other profiles fail closed; no configuration contents are printed.
& {
 $ErrorActionPreference='Stop'
 function Read-Bytes([string]$File) {
  $s=[IO.File]::Open($File,[IO.FileMode]::Open,[IO.FileAccess]::Read,
    ([IO.FileShare]::ReadWrite -bor [IO.FileShare]::Delete))
  try {
   if($s.Length -ne 241){throw 'PROFILE_SIZE'}
   [byte[]]$b=New-Object byte[] 241
   $p=0
   while($p -lt $b.Length){$n=$s.Read($b,$p,$b.Length-$p);if($n -le 0){throw 'READ_SHORT'};$p+=$n}
   if($s.ReadByte() -ne -1){throw 'READ_LONG'}
   return ,$b
  } finally {$s.Dispose()}
 }
 function Digest([byte[]]$Bytes) {
  $s=[Security.Cryptography.SHA256]::Create()
  try {return ([BitConverter]::ToString($s.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}
  finally {$s.Dispose()}
 }
 try {
  $raw=Read-Bytes $Path;$sha=Digest $raw
  $known=@{
   'efd91d5df93359c3320c72e185941247688b9ffad8fe3a5af196a9ed675a15fc'=$true
   'c0662185786f2204479c9ad90d2dcc2ed0dbb79d9d532942f1841f650ef498b6'=$false
  }
  if(-not $known.ContainsKey($sha)){throw 'UNREVIEWED_PROFILE'}
  if(($raw[236] -gt 1) -or (($raw[236] -eq 1) -ne $known[$sha])){throw 'FLAG_MISMATCH'}
  if((Digest (Read-Bytes $Path)) -cne $sha){throw 'SOURCE_CHANGED'}
  [pscustomobject]@{
   readerVersion=1;observedUTC=[DateTime]::UtcNow.ToString('o')
   scope='REVIEWED_FILE_PROFILE_ONLY';powerShellVersion=$PSVersionTable.PSVersion.ToString()
   fileSHA256=$sha;fileBytes=241
   computer='localhost';opcServer='InSAT.ModbusOPCServer.DA'
   connectionReadOnly=($raw[236] -eq 1);readOnlyFileOffset=236
   activeRuntimeSettingEstablished=$false;hardwareWriteTested=$false;sourceUnchanged=$true
  } | ConvertTo-Json -Depth 3
 } catch {
  [Console]::Error.WriteLine(('SCADA_OPC_WRITE_GATE_READ_FAILED exception={0} hresult=0x{1}; configuration contents omitted.' -f $_.Exception.GetType().FullName,$_.Exception.HResult.ToString('X8')))
  exit 1
 }
}
