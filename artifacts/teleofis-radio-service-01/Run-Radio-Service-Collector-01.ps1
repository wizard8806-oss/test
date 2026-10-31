param([string]$StationId='station-001',[string]$ConfigPath='C:\ProgramData\Automatika\stations.json')
& {
$ErrorActionPreference='Stop'
if(-not ('TeleofisRadioService01' -as [type])){
$svcTypeOptions=@{}
if($PSVersionTable.PSVersion.Major -lt 6){
 $svcTypeOptions.ReferencedAssemblies=@('System.dll','System.Core.dll','System.Xml.dll')
}
Add-Type @svcTypeOptions -TypeDefinition @'
using System;
using System.IO;
using System.Net.Sockets;
using System.Text;
using System.Xml;
using System.Globalization;
using System.Collections.Generic;
using System.Diagnostics;
public sealed class RadioServiceFailure01 : Exception {
 public readonly int State; public readonly bool Fatal;
 public RadioServiceFailure01(string code,int state,bool fatal) : base(code) {State=state;Fatal=fatal;}
}
public sealed class TeleofisRadioService01 : IDisposable {
 TcpClient client; NetworkStream stream;
 readonly byte[] input=new byte[4096]; int pos,count;
 readonly List<byte> outer=new List<byte>(); bool inside,escaped;
 public long DeviceId {get;private set;}
 public string TargetImei {get;private set;}
 public TeleofisRadioService01(string imei){
  if(imei==null||!System.Text.RegularExpressions.Regex.IsMatch(imei,"^[0-9]{15}$"))throw new RadioServiceFailure01("CONFIG_IMEI_INVALID",4,true);
  TargetImei=imei;
 }
 public static int OuterCrc(byte[] a,int n){
  int c=0;for(int i=0;i<n;i++){c^=a[i];for(int k=0;k<8;k++)c=(c>>1)^((c&1)!=0?0xA001:0);}return c;
 }
 public static int InnerCrc(byte[] a,int n){
  int c=65535;for(int i=0;i<n;i++){c^=a[i]<<8;for(int k=0;k<8;k++)c=((c<<1)^((c&32768)!=0?4129:0))&65535;}return c;
 }
 public static byte[] CloudFrame(long did,int command,byte[] data){
  var a=new List<byte>();a.AddRange(BitConverter.GetBytes(did));a.Add((byte)command);a.Add((byte)(command>>8));a.AddRange(data);
  int c=OuterCrc(a.ToArray(),a.Count);a.Add((byte)c);a.Add((byte)(c>>8));var b=new List<byte>();b.Add(171);
  foreach(byte x in a){if(x==171||x==205||x==239){b.Add(239);b.Add((byte)(x^255));}else b.Add(x);}b.Add(205);return b.ToArray();
 }
 static byte[] ModemFrame(int action,int cmd,byte[] data){
  if(!((action==4&&cmd==78&&data.Length<=32)||(action==0&&(cmd==123||cmd==131||cmd==148)&&data.Length==0)))
   throw new RadioServiceFailure01("REQUEST_NOT_ALLOWED",3,true);
  var a=new List<byte>(new byte[]{1,(byte)action,(byte)cmd,(byte)(cmd>>8),(byte)data.Length});a.AddRange(data);
  int c=InnerCrc(a.ToArray(),a.Count);a.Add((byte)c);a.Add((byte)(c>>8));var b=new List<byte>();b.Add(192);
  foreach(byte x in a){if(x==192){b.Add(196);b.Add(193);}else if(x==194){b.Add(196);b.Add(195);}else if(x==196){b.Add(196);b.Add(196);}else b.Add(x);}b.Add(194);return b.ToArray();
 }
 public static byte[] GroupXml(long login,string password){
  using(var m=new MemoryStream()){
   var settings=new XmlWriterSettings();settings.Encoding=new UTF8Encoding(false);settings.Indent=false;
   using(var w=XmlWriter.Create(m,settings)){
    w.WriteStartDocument(true);w.WriteStartElement("groupInfo");w.WriteElementString("login",login.ToString(CultureInfo.InvariantCulture));
    w.WriteElementString("password",password);w.WriteEndElement();w.WriteEndDocument();
   }return m.ToArray();
  }
 }
 public void Connect(string server,int port){
  Dispose();client=new TcpClient();client.NoDelay=true;
  try{
   var pending=client.BeginConnect(server,port,null,null);
   try{if(!pending.AsyncWaitHandle.WaitOne(5000))throw new IOException();client.EndConnect(pending);}
   finally{pending.AsyncWaitHandle.Close();}
   stream=client.GetStream();stream.ReadTimeout=100;stream.WriteTimeout=3000;
  }catch{Dispose();throw new RadioServiceFailure01("CLOUD_CONNECT_FAILED",4,false);}
 }
 void Send(byte[] b){try{stream.Write(b,0,b.Length);}catch{throw new RadioServiceFailure01("CLOUD_SEND_FAILED",4,false);}}
 int ReadByte(){
  if(pos<count)return input[pos++];
  try{count=stream.Read(input,0,input.Length);pos=0;if(count==0)throw new RadioServiceFailure01("CLOUD_CONNECTION_CLOSED",4,false);return input[pos++];}
  catch(IOException e){var se=e.InnerException as SocketException;if(se!=null&&(se.SocketErrorCode==SocketError.TimedOut||se.SocketErrorCode==SocketError.WouldBlock))return -1;throw new RadioServiceFailure01("CLOUD_READ_FAILED",4,false);}
 }
 byte[] Receive(Stopwatch timer,int timeout){
  while(timer.ElapsedMilliseconds<timeout){
   int x=ReadByte();if(x<0)continue;
   if(x==171){outer.Clear();inside=true;escaped=false;continue;}if(!inside)continue;
   if(escaped){if(x!=84&&x!=50&&x!=16)throw new RadioServiceFailure01("CLOUD_BAD_ESCAPE",3,false);x^=255;escaped=false;}
   else if(x==239){escaped=true;continue;}
   else if(x==205){
    inside=false;byte[] a=outer.ToArray();int n=a.Length;
    if(n<12)throw new RadioServiceFailure01("CLOUD_BAD_LENGTH",3,false);
    if(OuterCrc(a,n-2)!=(a[n-2]|a[n-1]<<8))throw new RadioServiceFailure01("CLOUD_BAD_CRC",3,false);return a;
   }
   outer.Add((byte)x);if(outer.Count>131072)throw new RadioServiceFailure01("CLOUD_FRAME_TOO_LARGE",3,false);
  }return null;
 }
 static string Field(XmlNode n,string name){
  string value=null;foreach(XmlNode c in n.ChildNodes){if(c.NodeType!=XmlNodeType.Element||c.LocalName!=name)continue;
   if(value!=null)throw new RadioServiceFailure01("CLOUD_LIST_DUPLICATE_FIELD",3,true);value=c.InnerText;}
  return value;
 }
 long SelectTarget(byte[] a){
  try{
   var settings=new XmlReaderSettings();settings.DtdProcessing=DtdProcessing.Prohibit;settings.XmlResolver=null;settings.MaxCharactersInDocument=131072;
   var doc=new XmlDocument();doc.XmlResolver=null;
   using(var m=new MemoryStream(a,10,a.Length-12))using(var r=XmlReader.Create(m,settings)){doc.Load(r);}
   if(doc.DocumentElement==null||doc.DocumentElement.LocalName!="deviceList")throw new FormatException();
   int all=0,matches=0;long selected=0;
   foreach(XmlNode d in doc.DocumentElement.ChildNodes){
    if(d.NodeType!=XmlNodeType.Element||d.LocalName!="devices")continue;all++;
    if(Field(d,"imei")!=TargetImei)continue;matches++;
    if(!long.TryParse(Field(d,"id"),NumberStyles.None,CultureInfo.InvariantCulture,out selected)||selected<=0)throw new FormatException();
    if(Field(d,"enabled")=="false")throw new RadioServiceFailure01("TARGET_DISABLED",4,true);
   }
   if(all==0)throw new RadioServiceFailure01("CLOUD_LIST_EMPTY_CHECK_GROUP_ACCESS",4,true);
   if(matches==0)throw new RadioServiceFailure01("TARGET_NOT_IN_GROUP",4,true);
   if(matches!=1)throw new RadioServiceFailure01("TARGET_IMEI_AMBIGUOUS",4,true);
   return selected;
  }catch(RadioServiceFailure01){throw;}catch{throw new RadioServiceFailure01("CLOUD_BAD_DEVICE_LIST",3,true);}
 }
 public void Login(long login,string password){
  byte[] xml=GroupXml(login,password);try{Send(CloudFrame(0,1,xml));}finally{Array.Clear(xml,0,xml.Length);}
  var timer=Stopwatch.StartNew();byte[] a;
  while((a=Receive(timer,10000))!=null){int cmd=a[8]|a[9]<<8;
   if(cmd==5)throw new RadioServiceFailure01("CLOUD_GROUP_ACCESS_REJECTED",4,true);
   if(cmd==2){DeviceId=SelectTarget(a);return;}
  }throw new RadioServiceFailure01("CLOUD_LIST_TIMEOUT",4,false);
 }
 byte[] Ask(int cmd,int action,byte[] data,int reply){
  if(DeviceId<=0)throw new RadioServiceFailure01("TARGET_NOT_SELECTED",4,true);
  Send(CloudFrame(DeviceId,0,ModemFrame(action,cmd,data)));
  var timer=Stopwatch.StartNew();var body=new List<byte>();bool started=false,stuffed=false;byte[] a;
  while((a=Receive(timer,6000))!=null){
   int outerCommand=a[8]|a[9]<<8;
   if(outerCommand==5)throw new RadioServiceFailure01("CLOUD_SESSION_DISCONNECTED",4,false);
   if(outerCommand==2){if(SelectTarget(a)!=DeviceId)throw new RadioServiceFailure01("TARGET_ID_CHANGED",4,false);continue;}
   if(outerCommand!=0||BitConverter.ToInt64(a,0)!=DeviceId)continue;
   for(int i=10;i<a.Length-2;i++){
    int x=a[i];if(x==192){body.Clear();started=true;stuffed=false;continue;}if(!started)continue;
    if(stuffed){if(x==193)x=192;else if(x==195)x=194;else if(x!=196)throw new RadioServiceFailure01("MODEM_BAD_ESCAPE",3,false);stuffed=false;}
    else if(x==196){stuffed=true;continue;}
    else if(x==194){
     started=false;byte[] b=body.ToArray();int n=b.Length;
     if(n<7||b[0]!=1||n!=7+b[4])throw new RadioServiceFailure01("MODEM_BAD_LENGTH_OR_VERSION",3,false);
     if(InnerCrc(b,n-2)!=(b[n-2]|b[n-1]<<8))throw new RadioServiceFailure01("MODEM_BAD_CRC",3,false);
     int response=b[2]|b[3]<<8;
     if(response==65535&&action==4&&b[1]==5)throw new RadioServiceFailure01("MODEM_AUTH_REJECTED",1,true);
     if(response==65535&&b[4]>=3&&(b[5]|b[6]<<8)==cmd)
      throw new RadioServiceFailure01(b[7]==0?"MODEM_AUTH_REQUIRED":"MODEM_COMMAND_ERROR",b[7]==0?1:3,false);
     if(response!=cmd)continue;
     if(b[1]!=reply)throw new RadioServiceFailure01("MODEM_BAD_REPLY_ACTION",3,false);
     byte[] result=new byte[b[4]];Array.Copy(b,5,result,0,result.Length);return result;
    }
    body.Add((byte)x);if(body.Count>262)throw new RadioServiceFailure01("MODEM_FRAME_TOO_LARGE",3,false);
   }
  }throw new RadioServiceFailure01("MODEM_TIMEOUT_CMD"+cmd,2,false);
 }
 public void Authenticate(byte[] key){Ask(78,4,key,5);}
 public long[] ReadRadio(){
  byte[] s=Ask(123,0,new byte[0],2),v=Ask(131,0,new byte[0],2),r=Ask(148,0,new byte[0],2);
  if(s.Length!=1||v.Length!=4||r.Length!=1||(s[0]>32&&s[0]!=99))throw new RadioServiceFailure01("MODEM_BAD_RADIO_DATA",3,false);
  return new long[]{s[0],r[0],BitConverter.ToUInt32(v,0)};
 }
 public void Dispose(){if(client!=null){try{client.Close();}catch{}client=null;}stream=null;pos=count=0;inside=escaped=false;outer.Clear();DeviceId=0;}
}
'@
}
try{
 $svcConfig=[IO.File]::ReadAllText($ConfigPath,[Text.Encoding]::UTF8)|ConvertFrom-Json
 if($svcConfig.Schema -ne 1){throw 'CONFIG_SCHEMA_INVALID'}
 $svcGroups=@{};$svcIds=@{};$svcPaths=@{}
 foreach($group in $svcConfig.Groups){
  if($group.Id -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$' -or $svcGroups.ContainsKey([string]$group.Id)){throw 'CONFIG_GROUP_ID_INVALID_OR_DUPLICATE'}
  if([string]::IsNullOrWhiteSpace($group.Server) -or [int]$group.Port -lt 1 -or [int]$group.Port -gt 65535 -or [long]$group.Login -lt 1){throw 'CONFIG_GROUP_CONNECTION_INVALID'}
  $svcGroups[[string]$group.Id]=$group
 }
 foreach($station in $svcConfig.Stations){
  if($station.Id -notmatch '^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$' -or $svcIds.ContainsKey([string]$station.Id)){throw 'CONFIG_STATION_ID_INVALID_OR_DUPLICATE'}
  if(-not $svcGroups.ContainsKey([string]$station.GroupId) -or $station.Imei -notmatch '^[0-9]{15}$'){throw 'CONFIG_STATION_GROUP_OR_IMEI_INVALID'}
  if([string]::IsNullOrWhiteSpace($station.RadioDataDirectory) -or -not [IO.Path]::IsPathRooted($station.RadioDataDirectory)){throw 'CONFIG_STATION_DIRECTORY_INVALID'}
  $canonical=[IO.Path]::GetFullPath($station.RadioDataDirectory).TrimEnd([char[]]@('\','/'))
  if($svcPaths.ContainsKey($canonical)){throw 'CONFIG_STATION_DIRECTORY_COLLISION'}
  if([int]$station.PollMilliseconds -lt 5000 -or [int]$station.PollMilliseconds -gt 3600000){throw 'CONFIG_POLL_INTERVAL_INVALID'}
  $svcPaths[$canonical]=$true;$svcIds[[string]$station.Id]=$station
 }
 if(-not $svcIds.ContainsKey($StationId)){throw 'CONFIG_SELECTED_STATION_NOT_FOUND'}
 $svcStation=$svcIds[$StationId];$svcConnection=$svcGroups[[string]$svcStation.GroupId]
 $svcDir=[string]$svcStation.RadioDataDirectory;$svcImei=[string]$svcStation.Imei
 $svcServer=[string]$svcConnection.Server;$svcPort=[int]$svcConnection.Port;$svcGroup=[long]$svcConnection.Login
}catch{Write-Host ('ERROR: Station configuration: '+$_.Exception.Message) -ForegroundColor Red;return}
$svcFile=Join-Path $svcDir 'radio.txt';$svcStop=Join-Path $svcDir 'radio.stop'
$svcStatus=Join-Path $svcDir 'radio-service-status.txt'
$svcRun=[Guid]::NewGuid().ToString('N');$svcTemp=$svcFile+'.'+$svcRun+'.tmp'
$svcEpoch=[DateTime]::new(1970,1,1,0,0,0,[DateTimeKind]::Utc)
$svcPub=@{Seq=[long]0};$svcOwn=$false;$svcFatal=$false
$svcLock=$null;$svcClient=$null;$svcCloudSecret=$null;$svcModemSecret=$null
function Get-ServiceEpoch {return [long][Math]::Floor(([DateTime]::UtcNow-$svcEpoch).TotalSeconds)}
function Publish-ServiceRadio([int]$state,[long]$sample,[long]$signal,[long]$rat,[long]$mv,[string]$code){
 $svcPub.Seq++
 [string[]]$rows=@('ARADIO1','SERVICE',$svcRun,[string]$svcPub.Seq,[string](Get-ServiceEpoch),[string]$sample,[string]$state,[string]$signal,[string]$rat,[string]$mv)
 [IO.File]::WriteAllText($svcTemp,([string]::Join("`n",$rows)+"`n"),[Text.UTF8Encoding]::new($false))
 for($attempt=0;$attempt -lt 5;$attempt++){
  try{if([IO.File]::Exists($svcFile)){[IO.File]::Replace($svcTemp,$svcFile,[NullString]::Value)}else{[IO.File]::Move($svcTemp,$svcFile)};break}
  catch{if($attempt -eq 4){throw};Start-Sleep -Milliseconds 25}
 }
 try{[IO.File]::WriteAllText($svcStatus,('UTC='+[DateTime]::UtcNow.ToString('o')+"`nSOURCE=SERVICE`nSTATION="+$StationId+"`nGROUP="+$svcGroup+"`nIMEI="+$svcImei+"`nSTATUS="+$code+"`n"),[Text.UTF8Encoding]::new($false))}catch{}
}
try{
 $null=[IO.Directory]::CreateDirectory($svcDir)
 try{$svcLock=[IO.File]::Open((Join-Path $svcDir 'collector.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}
 catch{throw 'COLLECTOR_LOCKED_OR_DIRECTORY_UNAVAILABLE'}
 $svcOwn=$true
 if([IO.File]::Exists($svcStop)){[IO.File]::Delete($svcStop)}
 $svcCloudSecret=Read-Host ('M2M24 Service GROUP '+$svcGroup+' password (same as Service server Login settings)') -AsSecureString
 $svcModemSecret=Read-Host 'TELEOFIS MODEM settings password (same as successful USB test)' -AsSecureString
 Write-Host ('RADIO SERVICE: '+$StationId+', '+$svcServer+':'+$svcPort+', group '+$svcGroup+', IMEI '+$svcImei+', interval '+$svcStation.PollMilliseconds+' ms.')
 Write-Host ('Output: '+$svcFile+'. Keep this window open. Stop: Ctrl+C. Main50008 and USB are not used.')
 $svcAuth=[Diagnostics.Stopwatch]::new()
 while(-not [IO.File]::Exists($svcStop)){
  $state=0;$sample=[long]0;$signal=[long]-1;$rat=[long]-1;$mv=[long]-1;$code='OK'
  try{
   if($null -eq $svcClient){
    $svcClient=[TeleofisRadioService01]::new($svcImei);$svcClient.Connect($svcServer,$svcPort)
    $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($svcCloudSecret)
    try{$plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr);$svcClient.Login($svcGroup,$plain)}
    finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr);$plain=$null}
    $svcAuth.Reset()
   }
   if(-not $svcAuth.IsRunning -or $svcAuth.ElapsedMilliseconds -gt 420000){
    $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($svcModemSecret);$key=$null
    try{
     $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
     if($plain -cnotmatch '^[\x20-\x7e]{0,32}$'){throw [RadioServiceFailure01]::new('MODEM_PASSWORD_FORMAT',1,$true)}
     [byte[]]$key=[Text.Encoding]::ASCII.GetBytes($plain);$svcClient.Authenticate($key);$svcAuth.Restart()
    }finally{[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr);$plain=$null;if($null -ne $key){[Array]::Clear($key,0,$key.Length)}}
   }
   $sample=Get-ServiceEpoch
   [long[]]$result=$svcClient.ReadRadio();$signal=$result[0];$rat=$result[1];$mv=$result[2]
  }catch{
   $e=$_.Exception;while($null -ne $e.InnerException){$e=$e.InnerException}
   if($e -is [RadioServiceFailure01]){$state=$e.State;$code=$e.Message;$svcFatal=$e.Fatal}
   else{$state=4;$code='SERVICE_UNEXPECTED_FAILURE'}
   $sample=[long]0;$signal=[long]-1;$rat=[long]-1;$mv=[long]-1
   if($null -ne $svcClient){$svcClient.Dispose();$svcClient=$null};$svcAuth.Reset()
  }
  Publish-ServiceRadio $state $sample $signal $rat $mv $code
  if($svcFatal){Write-Host ('ERROR: '+$code+'. Check the local Service/modem credentials or target group. No passwords were saved.') -ForegroundColor Red;break}
  $delay=[Diagnostics.Stopwatch]::StartNew();$interval=if($state -eq 0){[int]$svcStation.PollMilliseconds}else{30000}
  while($delay.ElapsedMilliseconds -lt $interval -and -not [IO.File]::Exists($svcStop)){Start-Sleep -Milliseconds 100}
 }
}catch{
 Write-Host 'ERROR: Collector could not start or publish its local file. Check whether another collector is running and the data directory is writable.' -ForegroundColor Red
}finally{
 if($svcOwn -and $svcPub.Seq -gt 0 -and -not $svcFatal){try{Publish-ServiceRadio 5 0 -1 -1 -1 'STOPPED'}catch{}}
 if($null -ne $svcClient){$svcClient.Dispose()}
 if($null -ne $svcCloudSecret){$svcCloudSecret.Dispose()};if($null -ne $svcModemSecret){$svcModemSecret.Dispose()}
 if([IO.File]::Exists($svcTemp)){[IO.File]::Delete($svcTemp)}
 if($null -ne $svcLock){$svcLock.Dispose()}
}
};
