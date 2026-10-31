& {
$ErrorActionPreference='Stop'
$continuePatch=@'
H4sIAAAAAAACA91WaY/aMBD9K1YUCbsLUWCBkI1Q72OrHqs91A8EtY49gLdgU8d0u0L899oh5VrabqXe+UCC7cy8efP8nN7cU2PuHXmovPBzJWTthJoRwr3H
8qPQSk5Amv7R0VMwT+xi0G4WV15eP1Js5ubyCiGociYm0zHUzhjlFDXS9ESrS2AmT1OmOHx6ywUdvg0bFVJN5Y9newT5e6OmRaadeKn0qp6Eq3+giovcPmk1
EGMosq1yp+mfpG9R3ZXBQGnsi26Y+ALVxgYd2oeDAzJf53aXL3jX10BtmuDU3o6laTcxSXxJJ9B1I7YKBnl+ZrSQQ1SuTfwJGLr15oNrAzmuR/uaeUssGpjS
/MxQbbr+dJn3WE5nJjhRuTBCyd8B/iaVqxIuXQmXRQk+UzNp7D9Xhz8WEvLgPucYfzUtIYu99eYH3XvzY1uJ4MkrB7yAn7wsMDqkyQsXvVsmOVf3tabXeDPa
Yg/nvwh0L7NU9fr9EnxBXPcVXNVeZ07saDltxSysiPH+LtY2O03IToKiPKv/h2p6jX3biWpvrOSwv/lSdTN9OR9uryumghcgh2ZEfirxyWsthkLS8bL4zXw7
PdmWkhhgXJL80G7gZzQfuY5oIKgmAVWi8LBJWZRRGNABr4fNDo3bcRaxZtgBmjUgbsURpXUaNlpZxlm9E0KzHYeMhS0etg8rZG5GWl1ZU7LOIFVuBEPOKhAb
UTkEnqBczTQDNNVgbewj8EoJeC80TblQJTYIWSs6jNo8bnbqcT1stCOedWgryuJ2Zn8ygHrMO+2s0cjCThPCzoDHlALYYsJmvbXGduqi/gCsXl4I0grCWSVO
vXcy9arlqBOiERO7i4tWERKcazHBS9Cpl4Ht0zsbyorGCc/xcjHl1ECyMVogWg2D5EHqreCeu+i3gLu1//7yTn+X0qLzXyi1kJWZUMNGqILvCpKmWbGr+UxD
muYHN1m0o3eSNcbHn6bWGYDv4RutIv0fIth7DANlI+xcAgm58p4bh9+VFsaW8Mbd8NrJgmNOkmJwx5+X64t4gXOvZCfChk8HztK+ci7fCpxtwSoPqsEH+5G1
wdpag/YDbP4NGFu+SRKmpBFyBos/wMSi/xn5aRQwOAsAAA==
'@
function ContinueUnpack([string]$Packed){
 $m=[IO.MemoryStream]::new([Convert]::FromBase64String($Packed))
 $z=[IO.Compression.GZipStream]::new($m,[IO.Compression.CompressionMode]::Decompress)
 $o=[IO.MemoryStream]::new()
 try{$z.CopyTo($o);return [Text.Encoding]::UTF8.GetString($o.ToArray())}
 finally{$z.Dispose();$m.Dispose();$o.Dispose()}
}
function ContinueHash([string]$Value){
 $h=[Security.Cryptography.SHA256]::Create()
 try{return ([BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($Value)))).Replace('-','').ToLowerInvariant()}
 finally{$h.Dispose()}
}
try{
 $entry=Get-History | Where-Object {$_.CommandLine -match '(?m)^\$processPacked=@''\r?$'} | Select-Object -Last 1
 if(-not $entry){throw 'Previous installation block not found. Use the same PowerShell window.'}
 $match=[regex]::Match($entry.CommandLine,'(?ms)^\$processPacked=@''\r?\n(.*?)\r?\n''@')
 if(-not $match.Success){throw 'Previous installation block is incomplete'}
 $continuedCode=ContinueUnpack $match.Groups[1].Value
 if((ContinueHash $continuedCode) -ne 'ad60d2f46b6eee6c3d0bb57c7e7166981ff353c7b98f5d05c1f4b0870cd6665f'){throw 'Previous installer checksum does not match; nothing changed'}
 $changes=ConvertFrom-Json (ContinueUnpack $continuePatch)
 foreach($change in $changes){
  if([regex]::Matches($continuedCode,[regex]::Escape($change.old)).Count -ne 1){throw 'Patch context does not match; nothing changed'}
  $continuedCode=$continuedCode.Replace([string]$change.old,[string]$change.new)
 }
 if((ContinueHash $continuedCode) -ne 'c99f54fc7d69eb27ad129658fb2ac5333e2ac29eea551d31370516af5221eff3'){throw 'Updated installer checksum mismatch; nothing changed'}
 & ([scriptblock]::Create($continuedCode))
}catch{Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red}
};
