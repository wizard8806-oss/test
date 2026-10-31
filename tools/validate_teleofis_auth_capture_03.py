#!/usr/bin/env python3
"""Real .NET SerialPort/PTYS; auth capture never prints payload/password bytes."""
import binascii,hashlib,json,os,pty,select,struct,subprocess,tempfile,time,tty
from pathlib import Path
from validate_teleofis_radio_usb_probe_01 import frame,packet,OUT,PWSH,SCRIPT

CAPTURE=OUT/'Inspect-Teleofis-Usb-Auth-03.ps1'

def run(case):
 with tempfile.TemporaryDirectory(prefix='radio-auth-') as tmp:
  p=Path(tmp);master,slave=pty.openpty();tty.setraw(slave);device=os.ttyname(slave)
  helper=SCRIPT.read_text().split('$diagSerial=$null')[0]+'\n};\n'
  source=CAPTURE.read_text()
  assert source.count('$diagSerial.DtrEnable=$true;$diagSerial.RtsEnable=$true')==1
  source=source.replace('$diagSerial.DtrEnable=$true;$diagSerial.RtsEnable=$true',
                        '$diagSerial.DtrEnable=$false;$diagSerial.RtsEnable=$false')
  source=source.replace("'COM18',115200",repr(device)+',115200')
  source=source.replace('$diagWatch.ElapsedMilliseconds -lt 4000','$diagWatch.ElapsedMilliseconds -lt 350')
  source=source.replace('$diagSerial.Open()','$diagSerial.Open();$global:ProbeTestPort=$diagSerial')
  password='BAD' if case=='password_format' else 'TEST'
  prompt="function Read-Host { param([string]$Prompt,[switch]$AsSecureString) if($global:ProbeTestPort){throw 'Prompt after open'}; $global:PromptFirst=$true;ConvertTo-SecureString '"+password+"' -AsPlainText -Force }\n"
  source=prompt+helper+source+"\nWrite-Output ('PORT_CLOSED='+(-not $global:ProbeTestPort.IsOpen))\nWrite-Output ('PROMPT_FIRST='+$global:PromptFirst)\n"
  f=p/'run.ps1';f.write_text(source)
  env=os.environ|{k:str(p/v) for k,v in [('XDG_CACHE_HOME','cache'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data')]}
  proc=subprocess.Popen([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(f)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
  buf=bytearray();requests=[];start=time.monotonic();reply=b''
  try:
   while proc.poll() is None and time.monotonic()-start<12:
    if not select.select([master],[],[],.02)[0]:continue
    buf.extend(os.read(master,4096))
    while 194 in buf:
     end=buf.index(194)+1;wire=bytes(buf[:end]);del buf[:end]
     assert packet(wire)==(4,78,b'TEST');requests.append(wire);assert len(requests)==1
     reply=frame(5,78)
     if case=='echo_secret':reply=wire
     if case=='wrong_command':reply=frame(5,0)
     if case=='auth_rejected_ffff':reply=frame(5,65535)
     if case=='bad_crc':reply=frame(5,78,corrupt=True)
     if case=='legacy_v0':
      body=bytes([0,5,78,0]);body+=struct.pack('<H',binascii.crc_hqx(body,0xffff))
      reply=b'\xc0'+b''.join({192:b'\xc4\xc1',194:b'\xc4\xc3',196:b'\xc4\xc4'}.get(x,bytes([x])) for x in body)+b'\xc2'
     if case=='noise':reply=b'BOOT\r\n'
     if case=='silent':reply=b''
     if case=='unknown_version':reply=frame(5,78,version=3)
     if case=='fragmented':
      reply=b'BOOT\r\n'+frame(5,78)
      for x in reply:os.write(master,bytes([x]));time.sleep(.002)
     elif reply:os.write(master,reply)
   if proc.poll() is None:proc.kill();raise AssertionError('Test exceeded12s')
   stdout,stderr=proc.communicate(timeout=2);out=stdout.decode();err=stderr.decode()
   assert proc.returncode==0 and not err,(case,out,err)
   assert 'TEST' not in out and 'TEST' not in err,'Secret echo was printed'
   assert 'PORT_CLOSED=True' in out and 'PROMPT_FIRST=True' in out,(case,out)
   if case=='password_format':assert not requests and 'ERROR:' in out
   else:
    assert len(requests)==1 and 'ERROR:' not in out,(case,out)
    assert 'TX_BYTES='+str(len(requests[0])) in out
    assert 'RX_BYTES='+str(len(reply)) in out,(case,out,len(reply))
    if case in ['noise','silent']:assert 'COMPLETE_FRAMES=0' in out
    elif case=='unknown_version':assert 'FRAME UNKNOWN VERSION=3' in out
    else:
     assert 'COMPLETE_FRAMES=1' in out
     assert 'CRC='+('BAD' if case=='bad_crc' else 'OK') in out
     assert 'CMD='+('65535' if case=='auth_rejected_ffff' else '0' if case=='wrong_command' else '78') in out
     assert 'ACTION='+('4' if case=='echo_secret' else '5') in out
     assert 'V='+('0' if case=='legacy_v0' else '1') in out
   return dict(case=case,passed=True,one_auth_only=case!='password_format',password_and_payload_not_printed=True,port_closed=True,prompt_before_open=True)
  finally:
   if proc.poll() is None:proc.kill();proc.communicate()
   os.close(master);os.close(slave)

def main():
 cases=['normal','echo_secret','wrong_command','auth_rejected_ffff','bad_crc','legacy_v0','noise','silent','unknown_version','fragmented','password_format']
 results=[]
 for case in cases:results.append(run(case));print('PASS',case,flush=True)
 report=dict(date='2026-10-29',sha256=hashlib.sha256(CAPTURE.read_bytes()).hexdigest(),cases=results,
  transport='Actual PowerShell7.6.9/.NET SerialPort and independent Python peer on Linux PTYs',
  fixture_limits='DTR/RTS disabled solely for PTY; capture deadline350ms instead of4000ms; simulated password.',
  actual_modem_success=False,Windows_PowerShell51_verified=False,
  purpose='Distinguish zero bytes from ignored/malformed/other-version frames; no settings writes or password output.')
 (OUT/'auth-capture-validation-2026-10-29.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
