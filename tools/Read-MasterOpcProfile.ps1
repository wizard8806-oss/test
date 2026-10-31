param(
 [Parameter(Mandatory=$true)][string]$Path,
 [ValidatePattern('^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$')]
 [string]$ItemPrefix='codex.Device1'
)
# Offline metadata only. No OPC/Modbus connection, process or configuration change.
# Preserve repeated JSON members; ConvertFrom-Json can discard/reject them in PS5.
& {
 $ErrorActionPreference='Stop'
 $archive=$null; $inputStream=$null; $jsonReader=$null; $bodyStream=$null
 try {
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  Add-Type -AssemblyName System.Runtime.Serialization
  $source=Get-Item -LiteralPath $Path
  if($source.PSIsContainer -or $source.Length -gt 67108864){throw 'INPUT_LIMIT'}
  [byte[]]$raw=[IO.File]::ReadAllBytes($source.FullName)
  $sha=[Security.Cryptography.SHA256]::Create()
  try{$digest=([BitConverter]::ToString($sha.ComputeHash($raw))).Replace('-','').ToLowerInvariant()}
  finally{$sha.Dispose()}
  $inputStream=[IO.MemoryStream]::new($raw)
  $archive=[IO.Compression.ZipArchive]::new($inputStream,[IO.Compression.ZipArchiveMode]::Read,$true)
  $entries=@($archive.Entries | Where-Object {$_.FullName.EndsWith('.mbc',[StringComparison]::OrdinalIgnoreCase)})
  if($entries.Count -ne 1 -or $entries[0].Length -gt 4194304){throw 'MBC_LIMIT'}
  $entryStream=$entries[0].Open(); $bodyStream=[IO.MemoryStream]::new()
  try {
   $buffer=New-Object byte[] 4096
   while(($read=$entryStream.Read($buffer,0,$buffer.Length)) -gt 0){
    $bodyStream.Write($buffer,0,$read)
    if($bodyStream.Length -gt 4194304){throw 'MBC_LIMIT'}
   }
  } finally {$entryStream.Dispose()}
  [byte[]]$body=$bodyStream.ToArray()
  try {$json=[Text.UTF8Encoding]::new($false,$true).GetString($body)}
  catch {$json=[Text.Encoding]::GetEncoding(1251).GetString($body)}
  $json=$json.TrimStart([char]0xfeff)
  # The dictionary reader can tolerate truncated JSON. Validate syntax first,
  # without deserializing to a dictionary that would collapse duplicate keys.
  if(-not ('CodexMbpJsonSyntax01' -as [type])) {
   Add-Type -TypeDefinition @'
using System;
public sealed class CodexMbpJsonSyntax01 {
 readonly string text; int pos;
 CodexMbpJsonSyntax01(string value){text=value;}
 void Bad(){throw new FormatException();}
 void White(){while(pos<text.Length && (text[pos]==' '||text[pos]=='\t'||text[pos]=='\r'||text[pos]=='\n'))pos++;}
 bool Take(char c){if(pos<text.Length&&text[pos]==c){pos++;return true;}return false;}
 void Need(char c){if(!Take(c))Bad();}
 void StringValue(){
  Need('"');
  while(pos<text.Length){
   char c=text[pos++];if(c=='"')return;if(c<32)Bad();
   if(c!='\\')continue;
   if(pos>=text.Length)Bad();c=text[pos++];
   if(c=='u'){
    for(int i=0;i<4;i++){
     if(pos>=text.Length)Bad();char h=text[pos++];
     if(!((h>='0'&&h<='9')||(h>='a'&&h<='f')||(h>='A'&&h<='F')))Bad();
    }
   }else if("\"\\/bfnrt".IndexOf(c)<0)Bad();
  }
  Bad();
 }
 void Digits(){int start=pos;while(pos<text.Length&&text[pos]>='0'&&text[pos]<='9')pos++;if(start==pos)Bad();}
 void Number(){
  Take('-');if(!Take('0')){if(pos>=text.Length||text[pos]<'1'||text[pos]>'9')Bad();Digits();}
  if(Take('.'))Digits();
  if(Take('e')||Take('E')){if(!Take('+'))Take('-');Digits();}
 }
 void Literal(string expected){
  if(pos+expected.Length>text.Length||String.CompareOrdinal(text,pos,expected,0,expected.Length)!=0)Bad();
  pos+=expected.Length;
 }
 void Value(int depth){
  if(depth>64)Bad();White();if(pos>=text.Length)Bad();char c=text[pos];
  if(c=='{'){
   pos++;White();if(Take('}'))return;
   do{White();StringValue();White();Need(':');Value(depth+1);White();if(Take('}'))return;Need(',');}while(true);
  }
  if(c=='['){
   pos++;White();if(Take(']'))return;
   do{Value(depth+1);White();if(Take(']'))return;Need(',');}while(true);
  }
  if(c=='"'){StringValue();return;}
  if(c=='t'){Literal("true");return;}if(c=='f'){Literal("false");return;}if(c=='n'){Literal("null");return;}
  Number();
 }
 public static bool IsCompleteObject(string value){
  try{var p=new CodexMbpJsonSyntax01(value);p.White();if(p.pos>=value.Length||value[p.pos]!='{')return false;
   p.Value(0);p.White();return p.pos==value.Length;
  }catch(FormatException){return false;}
 }
}
'@
  }
  if(-not [CodexMbpJsonSyntax01]::IsCompleteObject($json)){throw 'INVALID_JSON'}
  $quotas=[Xml.XmlDictionaryReaderQuotas]::new()
  $quotas.MaxDepth=64; $quotas.MaxStringContentLength=4194304
  $quotas.MaxArrayLength=4194304; $quotas.MaxNameTableCharCount=131072
  $jsonReader=[Runtime.Serialization.Json.JsonReaderWriterFactory]::CreateJsonReader([Text.Encoding]::UTF8.GetBytes($json),$quotas)
  $document=[Xml.XmlDocument]::new(); $document.XmlResolver=$null; $document.Load($jsonReader)
  $wanted=@('PressureSP_Command','PressureSP_x100','PlcAliveCounter','MapVersion',
   'StationMode','PressurePV_x100','PressureSourceOK','Vfd1FreqRaw','Vfd1FreqState',
   'SpFeedbackVersion','SpConfirmedDrive','SpConfirmed_x100','SpApplyPhase',
   'SpApplyError','SpApplyDetail','SpApplyFlags')
  $allowed=@('Address','Region','Type','TypeInDevice','Access','Enabled','TegCalculation','KoffA','KoffB')
  $tags=[Collections.Generic.List[object]]::new()
  $issues=[Collections.Generic.List[object]]::new()
  function Visit-ProfileNode([Xml.XmlElement]$node,[string]$parent) {
   $names=@(); $categories=@()
   foreach($child in $node.get_ChildNodes()) {
    if($child -isnot [Xml.XmlElement]){continue}
    if($child.get_LocalName() -eq 'NameInTree'){$names+=@($child.get_InnerText())}
    if($child.get_LocalName() -eq 'Category'){$categories+=@($child.get_InnerText())}
   }
   if($names.Count -gt 1 -or $categories.Count -gt 1){throw 'AMBIGUOUS_NODE'}
   $current=$parent
   if($names.Count -eq 1 -and $names[0]){
    if($parent){$current=$parent+'.'+$names[0]}else{$current=$names[0]}
   }
   if($categories.Count -eq 1 -and $categories[0] -eq 'Teg' -and $names.Count -eq 1 -and $wanted -ccontains $names[0]) {
    $id=$ItemPrefix+'.'+$names[0]
    if($current -ceq $id -or $current.EndsWith('.'+$id,[StringComparison]::Ordinal)) {
     $fields=[ordered]@{}
     foreach($key in $allowed) {
      $values=[Collections.Generic.List[object]]::new()
      foreach($child in $node.get_ChildNodes()) {
       if($child -isnot [Xml.XmlElement] -or $child.get_LocalName() -cne $key){continue}
       $kind=$child.GetAttribute('type')
       if($key -eq 'TegCalculation' -and $child.get_InnerText() -notmatch '^(?i:true|false|0|1)$'){
        $issues.Add([ordered]@{itemID=$id;field=$key;issue='NON_FLAG_CALCULATION_OMITTED'});continue
       }
       if($kind -notin @('string','number','boolean','null') -or $child.get_InnerText().Length -gt 256){
        $issues.Add([ordered]@{itemID=$id;field=$key;issue='NON_SCALAR_OR_OVERLONG_FIELD_OMITTED'});continue
       }
       if($kind -eq 'null'){$values.Add($null)}else{$values.Add($child.get_InnerText())}
      }
      if($values.Count -eq 1){$fields[$key]=$values[0]}
      elseif($values.Count -gt 1){
       $fields[$key]=$values.ToArray()
       $issues.Add([ordered]@{itemID=$id;field=$key;issue='REPEATED_FIELD_NOT_COLLAPSED'})
      }
     }
     $tags.Add([ordered]@{itemID=$id;fields=$fields})
    }
   }
   foreach($child in $node.get_ChildNodes()) {
    if($child -is [Xml.XmlElement]){Visit-ProfileNode $child $current}
   }
  }
  Visit-ProfileNode $document.get_DocumentElement() ''
  foreach($name in $wanted) {
   $id=$ItemPrefix+'.'+$name
   if(@($tags | Where-Object {$_.itemID -ceq $id}).Count -gt 1){
    $issues.Add([ordered]@{itemID=$id;issue='REPEATED_TAG_NOT_COLLAPSED'})
   }
  }
  [ordered]@{
   schema=1; observedUTC=[DateTime]::UtcNow.ToString('o'); sourceName=$source.Name
   sourceSHA256=$digest; itemPrefix=$ItemPrefix; tags=$tags.ToArray(); issues=$issues.ToArray()
   scope='OFFLINE_CANDIDATE_METADATA_ONLY'; activeConfigurationEstablished=$false
   liveOPCReadPerformed=$false; hardwareCommandsSent=$false
   limitations=@('No live values/quality/freshness.','No active-file inference from existence.',
    'Raw type/region/access fields need verified enum interpretation.',
    'Calculation bodies are omitted; missing fields do not prove disabled calculation.',
    'MasterOPC coefficients do not establish SCADA offset/multiplier.')
  } | ConvertTo-Json -Depth 12
 } catch {
  # Do not print parser errors: they can quote sensitive configuration contents.
  [Console]::Error.WriteLine('MASTEROPC_PROFILE_READ_FAILED: unsupported, ambiguous, inaccessible or oversized input; no configuration contents printed.')
  exit 1
 } finally {
  if($jsonReader){$jsonReader.Dispose()}; if($bodyStream){$bodyStream.Dispose()}
  if($archive){$archive.Dispose()}; if($inputStream){$inputStream.Dispose()}
 }
}
