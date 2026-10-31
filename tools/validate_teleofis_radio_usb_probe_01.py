#!/usr/bin/env python3
"""Independent Python protocol peer over a PTY, real PowerShell/.NET serial I/O.

No modem, Main50008 or hardware is contacted. Python's CRC implementation
(binascii.crc_hqx) is independent of the probe's C# CRC implementation.
"""
from _runtime import PWSH as PWSH_RUNTIME
import binascii,hashlib,json,os,pty,re,select,struct,subprocess,tempfile,time,tty
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/teleofis-radio-usb-probe-01'
SCRIPT=OUT/'Read-Teleofis-Radio-Usb-01.ps1'
PWSH=PWSH_RUNTIME

def frame(action,cmd,data=b'',version=1,corrupt=False):
 body=bytes([version,action])+struct.pack('<H',cmd)+bytes([len(data)])+data
 body+=struct.pack('<H',binascii.crc_hqx(body,0xffff)^int(corrupt))
 return b'\xc0'+b''.join({192:b'\xc4\xc1',194:b'\xc4\xc3',196:b'\xc4\xc4'}.get(b,bytes([b])) for b in body)+b'\xc2'

def packet(encoded):
 assert encoded[0]==192 and encoded[-1]==194
 raw=encoded[1:-1];out=bytearray();i=0
 while i<len(raw):
  x=raw[i];i+=1
  if x==196:
   x={193:192,195:194,196:196}[raw[i]];i+=1
  out.append(x)
 assert out[0]==1 and len(out)==7+out[4]
 assert struct.unpack_from('<H',out,len(out)-2)[0]==binascii.crc_hqx(out[:-2],0xffff)
 return out[1],struct.unpack_from('<H',out,2)[0],bytes(out[5:-2])

def run(case,retry=False):
 with tempfile.TemporaryDirectory(prefix='radio-probe-') as tmp:
  work=Path(tmp);master,slave=pty.openpty();tty.setraw(slave);device=os.ttyname(slave)
  source=SCRIPT.read_text()
  if retry:
   library=source.split('$diagSerial=$null')[0]+'\n};\n'
   source=library+(OUT/'Retry-Teleofis-Radio-Usb-02.ps1').read_text()
  assert source.count("'COM18',115200")==1
  # PTYs lack electrical modem-control lines. Match native configurator on
  # Windows, but disable the two lines solely for this data-path fixture.
  assert source.count('$diagSerial.DtrEnable=$true;$diagSerial.RtsEnable=$true')==1
  source=source.replace('$diagSerial.DtrEnable=$true;$diagSerial.RtsEnable=$true',
                        '$diagSerial.DtrEnable=$false;$diagSerial.RtsEnable=$false')
  source=source.replace("'COM18',115200",repr(device)+',115200')
  password='12345' if case=='password_format' else 'ABCDEFGH' if case=='long_password' else '' if case=='empty_password' else '1234'
  secure="[Security.SecureString]::new()" if not password else "ConvertTo-SecureString '"+password+"' -AsPlainText -Force"
  source="function Read-Host { param([string]$Prompt,[switch]$AsSecureString) "+secure+" }\n"+source
  source+="\nWrite-Output ('PORT_CLOSED='+(-not $global:ProbeTestPort.IsOpen))\n"
  # Capture the actual SerialPort instance, without replacing .NET I/O.
  source=source.replace('$diagSerial.Open()','$diagSerial.Open();$global:ProbeTestPort=$diagSerial')
  file=work/'probe.ps1';file.write_text(source)
  env=os.environ|{k:str(work/v) for k,v in [('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data')]}
  proc=subprocess.Popen([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(file)],
                        stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
  started=time.monotonic();buffer=bytearray();received=[];fail=None
  try:
   while proc.poll() is None and time.monotonic()-started<15:
    ready,_,_=select.select([master],[],[],.05)
    if not ready:continue
    try:chunk=os.read(master,2048)
    except OSError:break
    buffer.extend(chunk)
    while 194 in buffer:
     end=buffer.index(194)+1;encoded=bytes(buffer[:end]);del buffer[:end]
     action,cmd,data=packet(encoded);received.append(dict(action=action,cmd=cmd,length=len(data)))
     assert len(received)<=4 and cmd==[78,123,131,148][len(received)-1],received
     assert (action,data)==((4,password.encode('ascii')) if cmd==78 else (0,b''))
     payload={78:b'',123:b'\x12',131:struct.pack('<I',11800),148:b'\x02'}[cmd]
     if case=='unknown_signal' and cmd==123:payload=b'\x63'
     if case=='unknown_rat' and cmd==148:payload=b'\x03'
     if case=='escaped_payload' and cmd==131:payload=b'\xc0\xc2\xc4\x00'
     if case=='wrong_payload_length' and cmd==123:payload=b'\x12\x13'
     if case=='timeout' and cmd==123:continue
     reply=frame(3 if case=='auth_denied' and cmd==78 else (5 if cmd==78 else 2),cmd,payload,
                 version=2 if case=='bad_version' and cmd==123 else 1,
                 corrupt=case=='bad_crc' and cmd==131)
     if case=='native_auth_denied' and cmd==78:reply=frame(5,65535,b'\x4e\x00\x01')
     if case=='native_read_denied' and cmd==123:reply=frame(2,65535,b'\x7b\x00\x00')
     if case=='bad_escape' and cmd==123:reply=b'\xc0\x01\xc4\x80\xc2'
     if case=='noise_fragmented' and cmd==123:
      reply=b'\x7f\x55'+frame(2,148,b'\x02')+reply
      for b in reply:os.write(master,bytes([b]));time.sleep(.001)
     else:os.write(master,reply)
   if proc.poll() is None:proc.kill();raise AssertionError('Probe exceeded15s')
   stdout,stderr=proc.communicate(timeout=2);output=stdout.decode();error=stderr.decode()
   assert proc.returncode==0,(case,output,error)
   assert not error,(case,error)
   assert 'PORT_CLOSED=True' in output,(case,output)
   assert '1234' not in output and '1234' not in error and 'ABCDEFGH' not in output,'Password leaked'
   success=case in ['normal','unknown_signal','unknown_rat','escaped_payload','noise_fragmented','long_password','empty_password']
   if success:
    assert len(received)==4 and 'ERROR:' not in output,(case,received,output)
    assert 'SIGNAL_RAW='+('99 (unknown)' if case=='unknown_signal' else '18') in output,(case,output)
    assert 'NETWORK='+('unknown; CODE=3' if case=='unknown_rat' else '4G; CODE=2') in output
    assert 'SUPPLY_MV='+str(0xc4c2c0 if case=='escaped_payload' else 11800) in output
   else:
    assert 'ERROR:' in output and 'SIGNAL_RAW=' not in output,(case,output)
    if case=='password_format':assert not received
    if case=='auth_denied':assert len(received)==1
    if case=='native_auth_denied':assert len(received)==1 and 'AUTH_REJECTED:' in output,output
    if case=='native_read_denied':assert len(received)==2 and 'DEVICE_ERROR: CMD=123 CODE=0' in output,output
    if case in ['bad_escape','bad_version','timeout']:assert len(received)==2
    if case=='bad_crc':assert len(received)==3
   return dict(case=case,retry_block=retry,passed=True,requests=received,port_closed=True,password_not_printed=True)
  finally:
   if proc.poll() is None:proc.kill();proc.communicate()
   os.close(master);os.close(slave)

def main():
 cases=['normal','unknown_signal','unknown_rat','escaped_payload','noise_fragmented',
        'auth_denied','bad_crc','bad_version','bad_escape','wrong_payload_length','timeout','password_format']
 results=[]
 for case in cases:
  result=run(case);results.append(result);print('PASS',case,flush=True)
 result=run('normal',retry=True);results.append(result);print('PASS retry_block',flush=True)
 report=dict(date='2026-10-29',sha256=hashlib.sha256(SCRIPT.read_bytes()).hexdigest(),
             transport='Real PowerShell7.6.9 / .NET SerialPort over Linux PTYs, independent Python peer',
             cases=results,requests_only='AUTH4/78, READ0/123, READ0/131, READ0/148',
             actual_Windows_COM18_or_TELEOFIS_verified=False,radio_SCADA_integration_implemented=False,
             control_lines_not_exercised='PTY fixtures substitute false for DTR/RTS; production true matches vendor JSSC defaults, physical validation pending.',
             underlying_protocol='Rechecked against official2.3.1 Java encoder and controller; actual device verification pending.')
 (OUT/'validation-2026-10-29.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
