param([Parameter(Mandatory=$true)][string]$ProjectDirectory)
# Offline 2.6.15.0 scalar-variable metadata. No application, network or write API.
# Format evidence and limitations: docs/reports/station09-metadata-reader-review-20261031.md
& {
 $ErrorActionPreference='Stop'
 $stage='LOAD_READER'; $readerVersion=1
 try {
  if(-not ('CodexScadaVariableMetadata01' -as [type])) {
   Add-Type -TypeDefinition @'
using System;
using System.IO;
using System.Text;
using System.Collections.Generic;
public sealed class CodexScadaVariableMetadata01 {
 public sealed class Tag {
  public string itemID, variableName;
  public uint serializedDataType;
  public bool external, useScaling;
  public sbyte useBit, decimalOffset;
  public double decimalMultiplier;
  public long recordStart, recordEnd, decimalOffsetPosition;
 }
 readonly BinaryReader reader;
 readonly HashSet<long> ids=new HashSet<long>();
 readonly List<Tag> tags=new List<Tag>();
 public int VariablesParsed {get; private set;}
 public int GroupsParsed {get; private set;}
 static readonly UTF8Encoding Utf8=new UTF8Encoding(false,true);
 static readonly UnicodeEncoding Wide=new UnicodeEncoding(false,false,true);
 CodexScadaVariableMetadata01(byte[] raw) {
  reader=new BinaryReader(new MemoryStream(raw,false),Utf8);
 }
 static void Need(bool value) {if(!value)throw new InvalidDataException();}
 byte B(){return reader.ReadByte();}
 bool Flag(){byte value=B();Need(value<=1);return value==1;}
 uint U(){return reader.ReadUInt32();}
 long Q(){return reader.ReadInt64();}
 double D(){return reader.ReadDouble();}
 void Single(){reader.ReadSingle();}
 string Text(bool wide) {
  uint count=U();Need(count<=65536);
  int size=checked((int)count*(wide?2:1));
  Need(size<=reader.BaseStream.Length-reader.BaseStream.Position);
  byte[] value=reader.ReadBytes(size);
  return wide?Wide.GetString(value):Utf8.GetString(value);
 }
 void Variable() {
  long start=reader.BaseStream.Position;
  string name=Text(false);long id=Q();Need(ids.Add(id));
  U(); // RegisterID (not the Modbus address).
  string address=Text(true);sbyte bit=reader.ReadSByte();uint type=U();
  bool external=Flag();U();B();Single();U();U();Text(true);
  B();U();B();Single();Text(true);Flag();B();D();D();
  // Deliberately support only the OPC DA/internal layout verified in this task.
  // UA identifier variants require a separate format validation, not a guess.
  Need(B()==0);
  bool opcDA=Flag();Q();
  for(int i=0;i<(opcDA?4:1);i++)Text(true); // Never output server/private fields.
  U();for(int i=0;i<4;i++)D();for(int i=0;i<4;i++)Q();
  Text(true);long offsetPosition=reader.BaseStream.Position;
  sbyte offset=reader.ReadSByte();bool scaling=Flag();D();D();
  VariablesParsed++;Need(VariablesParsed<=10000);
  if(address=="codex.Device1.PressureSP_Command" || address=="codex.Device1.PressureSP_x100") {
   // DecimalMultiplier is derived by the native setter, not a serialized field.
   tags.Add(new Tag {itemID=address,variableName=name,serializedDataType=type,
    external=external,useBit=bit,decimalOffset=offset,decimalMultiplier=Math.Pow(10,offset),
    useScaling=scaling,recordStart=start,recordEnd=reader.BaseStream.Position,
    decimalOffsetPosition=offsetPosition});
  }
 }
 void Group(int depth) {
  Need(depth<=32);GroupsParsed++;Need(GroupsParsed<=1000);
  // Group registration IDs can repeat in the manufacturer's demo.
  Text(false);Flag();U();uint count=U();Need(count<=10000);
  for(uint i=0;i<count;i++)Variable();
  count=U();Need(count<=1000);for(uint i=0;i<count;i++)Group(depth+1);
 }
 public static CodexScadaVariableMetadata01 Parse(byte[] raw) {
  Need(raw.Length>=12 && raw.Length<=8388608);
  var result=new CodexScadaVariableMetadata01(raw);
  try {
   result.Q();uint count=result.U();Need(count<=1000);
   for(uint i=0;i<count;i++)result.Group(0);
   Need(result.reader.BaseStream.Position==raw.Length);return result;
  } finally {result.reader.Dispose();}
 }
 public Tag[] SelectedTags(){return tags.ToArray();}
 public static byte[] ReadOnlyBytes(string path,int limit) {
  using(var stream=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.ReadWrite|FileShare.Delete)) {
   Need(stream.Length<=limit);int count=checked((int)stream.Length);byte[] value=new byte[count];int pos=0;
   while(pos<count){int got=stream.Read(value,pos,count-pos);Need(got>0);pos+=got;}
   Need(stream.ReadByte()==-1);return value;
  }
 }
}
'@
  }
  function Digest([byte[]]$Bytes) {
   $sha=[Security.Cryptography.SHA256]::Create()
   try {return ([BitConverter]::ToString($sha.ComputeHash($Bytes))).Replace('-','').ToLowerInvariant()}
   finally {$sha.Dispose()}
  }
  $stage='READ_PROJECT_VERSION'
  $directory=Get-Item -LiteralPath $ProjectDirectory
  if(-not $directory.PSIsContainer){throw 'INPUT_DIRECTORY'}
  $projectPath=Join-Path $directory.FullName 'Project.spr'
  $variablesPath=Join-Path $directory.FullName 'Variables.svr'
  $project=[CodexScadaVariableMetadata01]::ReadOnlyBytes($projectPath,1048576)
  if($project.Length -lt 16 -or [BitConverter]::ToUInt16($project,8) -ne 2 -or
     [BitConverter]::ToUInt16($project,10) -ne 6 -or [BitConverter]::ToUInt16($project,12) -ne 15 -or
     [BitConverter]::ToUInt16($project,14) -ne 0){throw 'UNSUPPORTED_VERSION'}
  $projectSHA=Digest $project
  $stage='READ_VARIABLES'
  $raw=[CodexScadaVariableMetadata01]::ReadOnlyBytes($variablesPath,8388608)
  $variablesSHA=Digest $raw
  $stage='PARSE_VARIABLES'
  $parsed=[CodexScadaVariableMetadata01]::Parse($raw)
  $tags=@($parsed.SelectedTags())
  $issues=@()
  foreach($id in @('codex.Device1.PressureSP_Command','codex.Device1.PressureSP_x100')) {
   $matches=@($tags | Where-Object {$_.itemID -ceq $id})
   if($matches.Count -ne 1){$issues+=@{itemID=$id;issue='EXPECTED_ONE_BINDING';count=$matches.Count};continue}
   $tag=$matches[0]
   if(-not $tag.external -or $tag.useBit -ne -1 -or $tag.useScaling -or $tag.decimalOffset -ne 0 -or $tag.decimalMultiplier -ne 1.0) {
    $issues+=@{itemID=$id;issue='RAW_SCALAR_SCALING_NOT_CONFIRMED'}
   }
  }
  $stage='VERIFY_SOURCE_STABLE'
  if((Digest ([CodexScadaVariableMetadata01]::ReadOnlyBytes($projectPath,1048576))) -cne $projectSHA -or
     (Digest ([CodexScadaVariableMetadata01]::ReadOnlyBytes($variablesPath,8388608))) -cne $variablesSHA){throw 'SOURCE_CHANGED'}
  [pscustomobject]@{
   readerVersion=$readerVersion;powerShellVersion=$PSVersionTable.PSVersion.ToString()
   observedUTC=[DateTime]::UtcNow.ToString('o');projectVersion='2.6.15.0'
   scope='OFFLINE_CANDIDATE_METADATA_ONLY';activeProjectEstablished=$false
   liveOPCReadPerformed=$false;hardwareCommandsSent=$false
   projectSHA256=$projectSHA;variablesSHA256=$variablesSHA;variablesBytes=$raw.Length
   variablesParsed=$parsed.VariablesParsed;groupsParsed=$parsed.GroupsParsed
   tags=$tags;issues=$issues;rawScalarScalingConfirmedInCandidate=($issues.Count -eq 0)
  } | ConvertTo-Json -Depth 6
 } catch {
  $errorType=$_.Exception.GetType().FullName
  $hresult='0x'+$_.Exception.HResult.ToString('X8')
  [Console]::Error.WriteLine("SCADA_VARIABLE_METADATA_READ_FAILED reader=$readerVersion stage=$stage exception=$errorType hresult=$hresult")
  exit 1
 }
}
