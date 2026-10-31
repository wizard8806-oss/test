# PART 1: recover only the reviewed packet from this window's in-memory history.
function ScadaRetryHash([byte[]]$bytes) {
 $sha=[Security.Cryptography.SHA256]::Create()
 try { ([BitConverter]::ToString($sha.ComputeHash($bytes))).Replace('-','').ToLowerInvariant() }
 finally { $sha.Dispose() }
}
$scadaRetryCode=$null
$scadaRetryReady=$null
foreach($entry in @(Get-History | Sort-Object Id -Descending)) {
 $match=[regex]::Match($entry.CommandLine,'(?s)\$clickPacked\s*=\s*@''\r?\n(.*?)\r?\n''@')
 if(-not $match.Success -or $match.Groups[1].Length -gt 20000) { continue }
 $stream=$null; $gzip=$null; $output=$null
 try {
  $stream=[IO.MemoryStream]::new([Convert]::FromBase64String($match.Groups[1].Value))
  $gzip=[IO.Compression.GZipStream]::new($stream,[IO.Compression.CompressionMode]::Decompress)
  $output=[IO.MemoryStream]::new()
  $buffer=New-Object byte[] 4096
  while(($count=$gzip.Read($buffer,0,$buffer.Length)) -gt 0) {
   $output.Write($buffer,0,$count)
   if($output.Length -gt 16384) { throw 'Packet too large' }
  }
  $bytes=$output.ToArray()
  if((ScadaRetryHash $bytes) -eq 'c0dd106e3fd82b338f561f9ab5322297a5b2b2d417118c98d3140c0d9239b3dc') {
   $scadaRetryCode=[Text.Encoding]::UTF8.GetString($bytes); break
  }
 } catch { } finally {
  if($gzip) { $gzip.Dispose() }; if($stream) { $stream.Dispose() }; if($output) { $output.Dispose() }
 }
}
if($scadaRetryCode) { Write-Host 'PART 1 OK' -ForegroundColor Green }
else { Write-Host 'Original packet not found. Use the same PowerShell window.' -ForegroundColor Red }

# PART 2: change exactly one line and verify the complete corrected installer.
$scadaRetryReady=$null
try {
 if(-not $scadaRetryCode) { throw 'PART 1 required' }
 $old=@'
 if(@($rows|Select-Object -ExpandProperty Id -Unique).Count -ne 7 -or @($rows|Select-Object -ExpandProperty Name -Unique).Count -ne 7){throw 'Duplicate script names or IDs'}
'@
 $new=@'
 $clickSeenIDs=@{};$clickSeenNames=@{}
 foreach($row in $rows){
  $clickIDKey=[string]$row['Id'];$clickNameKey=[string]$row['Name']
  if($clickSeenIDs.ContainsKey($clickIDKey) -or $clickSeenNames.ContainsKey($clickNameKey)){throw 'Duplicate script names or IDs'}
  $clickSeenIDs[$clickIDKey]=$true;$clickSeenNames[$clickNameKey]=$true
 }
'@
 $old=$old.Replace("`r`n","`n"); $new=$new.Replace("`r`n","`n")
 if([regex]::Matches($scadaRetryCode,[regex]::Escape($old)).Count -ne 1) { throw 'Patch mismatch' }
 $fixed=$scadaRetryCode.Replace($old,$new)
 if((ScadaRetryHash ([Text.Encoding]::UTF8.GetBytes($fixed))) -ne 'a176ed6d0a5fdcb6d3a8d7de61c3d0093190c10e2ad8e4b217e4022c658b60d7') { throw 'Checksum mismatch' }
 $scadaRetryReady=[scriptblock]::Create($fixed)
 Write-Host 'PART 2 OK' -ForegroundColor Green
} catch { Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red }

# PART 3: start the verified installer; it creates09 and preserves08.
if($scadaRetryReady) { & $scadaRetryReady }
else { Write-Host 'STOP: complete parts 1 and 2 first.' -ForegroundColor Red }
