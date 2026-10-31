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
$diagSerial=$null
$diagKey=$null
try{
    $diagSecure=Read-Host 'TELEOFIS settings password (same as in configurator)' -AsSecureString
    $diagPtr=[Runtime.InteropServices.Marshal]::SecureStringToBSTR($diagSecure)
    try{
        $diagText=[Runtime.InteropServices.Marshal]::PtrToStringBSTR($diagPtr)
        if($diagText -cnotmatch '^[\x20-\x7e]{0,32}$'){throw 'Settings password must contain 0 to 32 ASCII characters'}
        $diagKey=[Text.Encoding]::ASCII.GetBytes($diagText)
    }finally{
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($diagPtr)
        $diagText=$null;$diagSecure.Dispose()
    }
    $diagSerial=[IO.Ports.SerialPort]::new('COM18',115200,[IO.Ports.Parity]::None,8,[IO.Ports.StopBits]::One)
    $diagSerial.Handshake=[IO.Ports.Handshake]::None
    $diagSerial.DtrEnable=$true;$diagSerial.RtsEnable=$true
    $diagSerial.ReadTimeout=100;$diagSerial.WriteTimeout=1000
    $diagSerial.Open()
    $diagSerial.DiscardInBuffer()
    $diagTx=[Action[byte[]]]{param([byte[]]$packet) $diagSerial.Write($packet,0,$packet.Length)}
    $diagRx=[Func[int]]{try{return $diagSerial.ReadByte()}catch [TimeoutException]{return -1}}
    $null=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,78,4,$diagKey,5)
    [Array]::Clear($diagKey,0,$diagKey.Length)
    [byte[]]$diagSignal=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,123,0,[byte[]]@(),2)
    [byte[]]$diagSupply=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,131,0,[byte[]]@(),2)
    [byte[]]$diagRat=[TeleofisRadioProbe04]::Ask($diagTx,$diagRx,148,0,[byte[]]@(),2)
    if($diagSignal.Length -ne 1 -or $diagSupply.Length -ne 4 -or $diagRat.Length -ne 1){throw 'Unexpected radio-data length'}
    $diagSignalNote=if($diagSignal[0] -eq 99){' (unknown)'}elseif($diagSignal[0] -le 32){''}else{' (unrecognised code)'}
    $diagRatName=if($diagRat[0] -le 2){@('2G','3G','4G')[$diagRat[0]]}else{'unknown'}
    $diagMv=[BitConverter]::ToUInt32($diagSupply,0)
    Write-Host ('SIGNAL_RAW='+$diagSignal[0]+$diagSignalNote)
    Write-Host ('NETWORK='+$diagRatName+'; CODE='+$diagRat[0])
    Write-Host ('SUPPLY_MV='+$diagMv+'; VOLTS='+($diagMv/1000.0))
    Write-Host ('CHECKED_UTC='+[DateTime]::UtcNow.ToString('o'))
}catch{
    Write-Host ('ERROR: '+$_.Exception.Message) -ForegroundColor Red
}finally{
    if($null -ne $diagKey){[Array]::Clear($diagKey,0,$diagKey.Length)}
    if($null -ne $diagSerial){
        if($diagSerial.IsOpen){$diagSerial.Close()}
        $diagSerial.Dispose()
    }
}
};
