& {
$ErrorActionPreference='Stop'
if(-not ('TeleofisRadioProbe04' -as [type])){
Add-Type -TypeDefinition @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
public static class TeleofisRadioProbe04 {
 public static int Crc(byte[] b,int n) {
  int c=65535;
  for(int i=0;i<n;i++){c^=b[i]<<8;for(int k=0;k<8;k++)c=((c<<1)^((c&32768)!=0?4129:0))&65535;}
  return c;
 }
 public static byte[] Frame(int action,int cmd,byte[] data) {
  var b=new List<byte>(new byte[]{1,(byte)action,(byte)(cmd&255),(byte)(cmd>>8),(byte)data.Length});
  b.AddRange(data);int c=Crc(b.ToArray(),b.Count);b.Add((byte)(c&255));b.Add((byte)(c>>8));
  var f=new List<byte>();f.Add(192);
  foreach(byte x in b){if(x==192){f.Add(196);f.Add(193);}else if(x==194){f.Add(196);f.Add(195);}else if(x==196){f.Add(196);f.Add(196);}else f.Add(x);}
  f.Add(194);return f.ToArray();
 }
 public static byte[] Ask(Action<byte[]> tx,Func<int> rx,int cmd,int action,byte[] data,int reply) {
  bool auth=action==4&&cmd==78&&data.Length<=32&&reply==5;
  bool read=action==0&&(cmd==123||cmd==131||cmd==148)&&data.Length==0&&reply==2;
  if(!auth&&!read)throw new InvalidOperationException("Read-only probe: request rejected");
  tx(Frame(action,cmd,data));var clock=Stopwatch.StartNew();
  var b=new List<byte>();bool inside=false,escaped=false;int rxCount=0;
  while(clock.ElapsedMilliseconds<3000){
   int x=rx();if(x<0)continue;rxCount++;
   if(x==192){b.Clear();inside=true;escaped=false;continue;}
   if(!inside)continue;
   if(escaped){if(x==193)x=192;else if(x==195)x=194;else if(x!=196)throw new FormatException("Bad escape");escaped=false;}
   else if(x==196){escaped=true;continue;}
   else if(x==194){
    inside=false;byte[] a=b.ToArray();int n=a.Length;
    if(n<7||a[0]!=1||n!=7+a[4])throw new FormatException("Bad protocol version or packet length");
    if(Crc(a,n-2)!=(a[n-2]|a[n-1]<<8))throw new FormatException("CRC mismatch");
    int responseCmd=a[2]|a[3]<<8;
    if(responseCmd==65535&&auth&&a[1]==5)throw new InvalidOperationException("AUTH_REJECTED: modem rejected authentication. Verify the settings password in the official configurator.");
    if(responseCmd==65535&&a[4]>=3){int errorCmd=a[5]|a[6]<<8;if(errorCmd==cmd)throw new InvalidOperationException("DEVICE_ERROR: CMD="+errorCmd+" CODE="+a[7]);}
    if(responseCmd!=cmd)continue;
    if(a[1]!=reply)throw new InvalidOperationException("Device reply action "+a[1]+" for command "+cmd);
    byte[] result=new byte[a[4]];Array.Copy(a,5,result,0,result.Length);return result;
   }
   b.Add((byte)x);if(b.Count>262)throw new FormatException("Packet too long");
  }
  throw new TimeoutException("No matching reply to command "+cmd+" on COM18; RX_BYTES="+rxCount);
 }
}
'@
}
$diagSerial=$null;$diagSecure=$null;$diagLock=$null;$diagOwn=$false
$diagFatal=0;$diagPublish=@{Seq=[long]0}
$diagDir='C:\ProgramData\Automatika\Station50008'
$diagFile=Join-Path $diagDir 'radio.txt'
$diagStop=Join-Path $diagDir 'radio.stop'
$diagRun=[Guid]::NewGuid().ToString('N')
$diagTemp=$diagFile+'.'+$diagRun+'.tmp'
$diagEpoch=[DateTime]::new(1970,1,1,0,0,0,[DateTimeKind]::Utc)
function Get-RadioEpoch {return [long][Math]::Floor(([DateTime]::UtcNow-$diagEpoch).TotalSeconds)}
function Publish-Radio([int]$state,[long]$sample,[long]$signal,[long]$rat,[long]$mv){
    $diagPublish.Seq++
    [string[]]$rows=@('ARADIO1','USB',$diagRun,[string]$diagPublish.Seq,[string](Get-RadioEpoch),[string]$sample,[string]$state,[string]$signal,[string]$rat,[string]$mv)
    [IO.File]::WriteAllText($diagTemp,([string]::Join("`n",$rows)+"`n"),[Text.UTF8Encoding]::new($false))
    for($attempt=0;$attempt -lt 5;$attempt++){
        try{
            if([IO.File]::Exists($diagFile)){[IO.File]::Replace($diagTemp,$diagFile,[NullString]::Value)}
            else{[IO.File]::Move($diagTemp,$diagFile)}
            return
        }catch{
            if($attempt -eq 4){throw}
            Start-Sleep -Milliseconds 25
        }
    }
}
try{
    $null=[IO.Directory]::CreateDirectory($diagDir)
    try{$diagLock=[IO.File]::Open((Join-Path $diagDir 'collector.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)}
    catch{throw 'Radio collector already running, or its directory is unavailable'}
    $diagOwn=$true
    if([IO.File]::Exists($diagStop)){[IO.File]::Delete($diagStop)}
    $diagSecure=Read-Host 'TELEOFIS modem settings password (not Gateway group password)' -AsSecureString
    Write-Host ('RADIO COLLECTOR: USB COM18, interval 5 s. Output: '+$diagFile)
    Write-Host 'Keep this window open. Stop with Ctrl+C or radio.stop. No modem/PLC settings are written.'
    $diagAuth=[Diagnostics.Stopwatch]::new()
    while(-not [IO.File]::Exists($diagStop)){
        $state=0;$signal=[long]-1;$rat=[long]-1;$mv=[long]-1;$sample=[long]0
        try{
            if($null -eq $diagSerial){
                $diagSerial=[IO.Ports.SerialPort]::new('COM18',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
                $diagSerial.Handshake=[IO.Ports.Handshake]::None
                $diagSerial.DtrEnable=$true;$diagSerial.RtsEnable=$true
                $diagSerial.ReadTimeout=100;$diagSerial.WriteTimeout=1000
                $diagSerial.Open();$diagAuth.Reset()
            }
            $diagTx=[Action[byte[]]]{param([byte[]]$packet) $diagSerial.Write($packet,0,$packet.Length)}
            $diagRx=[Func[int]]{try{return $diagSerial.ReadByte()}catch [TimeoutException]{return -1}}
            if(-not $diagAuth.IsRunning -or $diagAuth.ElapsedMilliseconds -gt 420000){
                $key=$null
                $ptr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($diagSecure)
                try{
                    $plain=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
                    if($plain -cnotmatch '^[\x20-\x7e]{0,32}$'){throw 'AUTH_REJECTED: settings password must contain 0 to 32 ASCII characters'}
                    [byte[]]$key=[Text.Encoding]::ASCII.GetBytes($plain)
                    $null=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,78,4,$key,5)
                    $diagAuth.Restart()
                }finally{
                    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
                    $plain=$null
                    if($null -ne $key){[Array]::Clear($key,0,$key.Length)}
                }
            }
            [byte[]]$a=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,123,0,[byte[]]@(),2)
            [byte[]]$b=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,131,0,[byte[]]@(),2)
            [byte[]]$c=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,148,0,[byte[]]@(),2)
            if($a.Length -ne 1 -or $b.Length -ne 4 -or $c.Length -ne 1){throw 'Bad radio packet length'}
            $signal=[long]$a[0];$rat=[long]$c[0];$mv=[long][BitConverter]::ToUInt32($b,0)
            if($signal -gt 32 -and $signal -ne 99){throw 'Bad radio packet signal'}
            $sample=Get-RadioEpoch
        }catch{
            $message=$_.Exception.Message
            $signal=[long]-1;$rat=[long]-1;$mv=[long]-1;$sample=[long]0
            if($message -match 'AUTH_REJECTED:'){$state=1;$diagFatal=1}
            elseif($message -match 'No matching reply'){$state=2}
            elseif($message -match 'CRC|packet|escape'){$state=3}
            elseif($message -match 'DEVICE_ERROR:.*CODE=0'){$state=1;$diagAuth.Reset()}
            else{$state=4}
            if($state -eq 4 -and $null -ne $diagSerial){
                try{if($diagSerial.IsOpen){$diagSerial.Close()}}catch{}
                $diagSerial.Dispose();$diagSerial=$null;$diagAuth.Reset()
            }
        }
        Publish-Radio $state $sample $signal $rat $mv
        if($diagFatal -ne 0){break}
        $delay=[Diagnostics.Stopwatch]::StartNew()
        while($delay.ElapsedMilliseconds -lt 5000 -and -not [IO.File]::Exists($diagStop)){Start-Sleep -Milliseconds 100}
    }
}catch{
    Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
}finally{
    if($diagOwn -and $diagPublish.Seq -gt 0 -and $diagFatal -eq 0){try{Publish-Radio 5 0 -1 -1 -1}catch{}}
    if($null -ne $diagSerial){try{if($diagSerial.IsOpen){$diagSerial.Close()}}catch{};$diagSerial.Dispose()}
    if($null -ne $diagSecure){$diagSecure.Dispose()}
    if([IO.File]::Exists($diagTemp)){[IO.File]::Delete($diagTemp)}
    if($null -ne $diagLock){$diagLock.Dispose()}
}
};
