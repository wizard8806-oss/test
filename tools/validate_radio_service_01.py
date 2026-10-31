#!/usr/bin/env python3
"""Real PowerShell/.NET against an independent loopback M2M24 peer.

No external connections, modem or Main50008. Vendor JVM encoder is the
independent reference for the outer CRC/framing; the inner reference is the
previously verified Python peer. Test secrets are synthetic.
"""
import concurrent.futures,hashlib,json,os,select,socket,struct,subprocess,tempfile,time
from pathlib import Path
from xml.etree import ElementTree as ET
from validate_teleofis_radio_usb_probe_01 import frame,packet,PWSH

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/teleofis-radio-service-01'
SCRIPT=OUT/'Run-Radio-Service-Collector-01.ps1'
TARGET='863906061228379';DID=70001;OTHER_DID=42737
CLOUD_SECRET='Group<&"';MODEM_SECRET='TEST'

def arc(data):
 c=0
 for b in data:
  c^=b
  for _ in range(8):c=(c>>1)^ (0xa001 if c&1 else 0)
 return c

def cloud(did,cmd,data=b'',corrupt=False):
 body=struct.pack('<qH',did,cmd)+data
 body+=struct.pack('<H',arc(body)^int(corrupt))
 return b'\xab'+b''.join(bytes([239,b^255]) if b in [171,205,239] else bytes([b]) for b in body)+b'\xcd'

def uncloud(wire):
 assert wire[0]==171 and wire[-1]==205
 out=bytearray();i=1
 while i<len(wire)-1:
  x=wire[i];i+=1
  if x==239:x=wire[i]^255;i+=1
  out.append(x)
 assert len(out)>=12 and arc(out[:-2])==struct.unpack_from('<H',out,len(out)-2)[0]
 return struct.unpack_from('<qH',out,0)+(bytes(out[10:-2]),)

def device_list(case,target=TARGET):
 root=ET.Element('deviceList')
 if case=='empty_list':return ET.tostring(root)
 records=[(OTHER_DID,'123456789012345'),(DID,target)]
 if case=='missing_target':records=records[:1]
 if case=='duplicate_target':records=[(OTHER_DID,target),(DID,target)]
 for did,imei in records:
  d=ET.SubElement(root,'devices')
  for k,v in [('id',str(did)),('imei',imei),('name','fixture'),('enabled','false' if case=='disabled_target' and imei==target else 'true')]:ET.SubElement(d,k).text=v
 return ET.tostring(root,encoding='utf-8',xml_declaration=True)

def run(case):
 with tempfile.TemporaryDirectory(prefix='radio-service-') as tmp:
  p=Path(tmp);directory=p/'data';directory.mkdir()
  listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();listener.setblocking(False)
  config=json.loads((OUT/'stations.json').read_text())
  config['Groups'][0].update(Server='127.0.0.1',Port=listener.getsockname()[1])
  config['Stations'][0]['RadioDataDirectory']=str(directory)
  target=TARGET;login='7058';station_id='station-001'
  if case=='other_station':
   station_id='station-002';target='555555555555555';login='8765'
   config['Groups'].append(dict(Id='other-group',Server='127.0.0.1',Port=listener.getsockname()[1],Login=8765))
   station=dict(config['Stations'][0]);station.update(Id=station_id,GroupId='other-group',Imei=target,RadioDataDirectory=str(p/'other-data'))
   config['Stations'].append(station);directory=p/'other-data';directory.mkdir()
  elif case=='duplicate_station':config['Stations'].append(dict(config['Stations'][0]))
  elif case=='colliding_paths':
   station=dict(config['Stations'][0]);station.update(Id='station-002',Imei='555555555555555');config['Stations'].append(station)
  config_path=p/'stations.json';config_path.write_text(json.dumps(config))
  data=directory/'radio.txt';stop=directory/'radio.stop'
  source=SCRIPT.read_text()
  source=source.replace('Receive(timer,10000)','Receive(timer,250)').replace('Receive(timer,6000)','Receive(timer,200)')
  source=source.replace('{[int]$svcStation.PollMilliseconds}else{30000}','{80}else{120}')
  if case=='refresh_auth':source=source.replace('-gt 420000','-gt 50')
  prefix="function Read-Host {param([string]$Prompt,[switch]$AsSecureString) if($Prompt -match 'GROUP'){ConvertTo-SecureString '"+CLOUD_SECRET+"' -AsPlainText -Force}else{ConvertTo-SecureString '"+MODEM_SECRET+"' -AsPlainText -Force}}\n"
  if case=='locked':
   data.write_text('existing USB publication')
   prefix+="$testHeld=[IO.File]::Open('"+str(directory/'collector.lock')+"',[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)\n"
  source=source.replace("$ErrorActionPreference='Stop'","$ErrorActionPreference='Stop'\n"+prefix,1)
  f=p/'run.ps1';f.write_text(source)
  env=os.environ|{'XDG_CACHE_HOME':str(p/'cache'),'XDG_CONFIG_HOME':str(p/'config'),'XDG_DATA_HOME':str(p/'store')}
  proc=subprocess.Popen([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(f),'-ConfigPath',str(config_path),'-StationId',station_id],stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env)
  conn=None;buf=bytearray();seen={};requests=[];groups=0;fault=False;deadline=time.monotonic()+18
  try:
   while proc.poll() is None and time.monotonic()<deadline:
    if data.exists() and case!='locked':
     rows=data.read_text().splitlines();assert len(rows)==10 and rows[:2]==['ARADIO1','SERVICE'],rows
     assert CLOUD_SECRET not in '\n'.join(rows) and MODEM_SECRET not in '\n'.join(rows)
     if rows[6]!='0':assert rows[5]=='0' and rows[7:]==['-1','-1','-1'],rows
     else:assert 0<int(rows[5])<=int(rows[4]),rows
     seen[rows[3]]=rows
     good=[r for r in seen.values() if r[6]=='0']
     errors=[r for r in seen.values() if r[6] not in ['0','5']]
     recovery=case in ['recover_disconnect','recover_timeout','recover_inner_auth']
     recovered=recovery and good and errors and groups>=2 and max(int(r[3]) for r in good)>max(int(r[3]) for r in errors)
     if recovered or (not recovery and len(seen)>=3):stop.touch()
     if case in ['outer_crc','inner_crc','wrong_did','cloud_timeout'] and errors:stop.touch()
    ready,_,_=select.select([listener]+([conn] if conn else []),[],[],.01)
    if listener in ready:
     fresh,_=listener.accept();fresh.setblocking(False)
     assert conn is None,'Overlapping collector connections'
     conn=fresh;buf.clear()
    if conn is None or conn not in ready:continue
    chunk=conn.recv(16384)
    if not chunk:conn.close();conn=None;continue
    buf.extend(chunk)
    while 205 in buf:
     end=buf.index(205)+1;wire=bytes(buf[:end]);del buf[:end];did,cmd,payload=uncloud(wire)
     if cmd==1:
      groups+=1;assert did==0
      xml=ET.fromstring(payload);assert xml.tag=='groupInfo' and xml.findtext('login')==login and xml.findtext('password')==CLOUD_SECRET
      if case=='cloud_timeout':continue
      if case=='cloud_rejected':conn.sendall(cloud(0,5));continue
      listing=device_list(case,target)
      if case=='xml_dtd':listing=b'<!DOCTYPE deviceList [<!ENTITY x SYSTEM "file:///no-such-file">]><deviceList>&x;</deviceList>'
      response=cloud(0,2,listing)
      if case=='fragmented':
       for n in range(0,len(response),7):conn.sendall(response[n:n+7]);time.sleep(.001)
      else:conn.sendall(response)
     else:
      assert cmd==0 and did==DID,(cmd,did)
      action,command,key=packet(payload);requests.append((action,command))
      assert (action,command) in [(4,78),(0,123),(0,131),(0,148)]
      assert key==(MODEM_SECRET.encode() if command==78 else b'')
      if case=='session_replaced' and command==123:
       conn.sendall(cloud(DID,5));continue
      if case=='modem_rejected' and command==78:response=frame(5,65535,b'\x4e\x00\x01')
      elif case=='recover_inner_auth' and command==123 and not fault:
       fault=True;response=frame(2,65535,b'\x7b\x00\x00')
      elif case=='recover_timeout' and command==123 and not fault:fault=True;continue
      else:
       value={78:b'',123:bytes([99 if case=='unknown' else 26]),131:struct.pack('<I',11500),148:b'\x02'}[command]
       response=frame(5 if command==78 else 2,command,value,corrupt=case=='inner_crc' and command==123)
      reply_did=OTHER_DID if case=='wrong_did' and command==123 else DID
      if case=='fragmented' and command==131:
       conn.sendall(cloud(OTHER_DID,0,frame(2,131,struct.pack('<I',9999)))+cloud(DID,0,response[:4]))
       conn.sendall(cloud(DID,0,response[4:]))
      else:conn.sendall(cloud(reply_did,0,response,corrupt=case=='outer_crc' and command==123))
      if case=='recover_disconnect' and command==148 and not fault:
       fault=True;conn.shutdown(socket.SHUT_RDWR);conn.close();conn=None;break
   if proc.poll() is None:proc.kill();raise AssertionError((case,'Process did not stop',seen))
   stdout,stderr=proc.communicate(timeout=2);out=stdout.decode();err=stderr.decode()
   assert proc.returncode==0 and not err,(case,out,err)
   assert CLOUD_SECRET not in out+err and MODEM_SECRET not in out+err,(case,'Secret in output')
   assert not list(directory.glob('*.tmp'))
   if case in ['duplicate_station','colliding_paths']:
    assert not groups and not data.exists() and 'ERROR: Station configuration:' in out,(case,out)
   elif case=='locked':
    assert not groups and data.read_text()=='existing USB publication' and 'ERROR:' in out
   else:
    last=data.read_text().splitlines();states={r[6] for r in seen.values()}|{last[6]}
    fatal=case in ['missing_target','duplicate_target','disabled_target','empty_list','cloud_rejected','modem_rejected','xml_dtd','session_replaced']
    if fatal:
     assert 'ERROR:' in out and last[6]==('1' if case=='modem_rejected' else '3' if case=='xml_dtd' else '4'),(case,out,last)
     expected=[(4,78)] if case=='modem_rejected' else [(4,78),(0,123)] if case=='session_replaced' else []
     assert requests==expected,requests
    else:
     assert 'ERROR:' not in out and last[6]=='5',(case,out,last)
     if case in ['outer_crc','inner_crc']:assert '3' in states,states
     elif case=='wrong_did':assert '2' in states,states
     elif case=='cloud_timeout':assert '4' in states,states
     else:
      good=[r for r in seen.values() if r[6]=='0'];assert good,(case,seen)
      assert any(r[7:]==['99' if case=='unknown' else '26','2','11500'] for r in good),good
      if case.startswith('recover_'):assert any(st not in ['0','5'] for st in states) and groups>=2,(case,states,groups)
      if case=='refresh_auth':assert requests.count((4,78))>=2,requests
   if case=='other_station':assert not (p/'data/radio.txt').exists()
   status=(directory/'radio-service-status.txt')
   if status.exists():assert CLOUD_SECRET not in status.read_text() and MODEM_SECRET not in status.read_text()
   status_code=None
   if status.exists():
    status_code=next((line[7:] for line in status.read_text().splitlines() if line.startswith('STATUS=')),None)
   return dict(case=case,passed=True,group_logins=groups,read_only_modem_requests=len(requests),complete_publications=len(seen),final_status_code=status_code)
  finally:
   if proc.poll() is None:proc.kill();proc.communicate()
   if conn:conn.close()
   listener.close()

def vendor_reference():
 base=Path(os.environ['CODEX_TELEOFIS_PLUGINS'])
 jars=[base/'rcp.transport_2.0.1.202511131113.jar',base/'rcp.crc_1.0.0.202511131113.jar',base/'rcp.apachecommons_3.1.0.202511131113/commons-lang3-3.1.jar']
 with tempfile.TemporaryDirectory(prefix='service-vendor-') as tmp:
  p=Path(tmp);cp=os.pathsep.join(map(str,jars))
  java=r'''import rcp.m2mtcpclient.*;
public class CheckServiceFrames {
 public static void main(String[] args){
  long[] ids={0L,70001L,0x00EFCDAB56433211L};short[] commands={1,0,0};
  byte[][] data={"<groupInfo><login>7058</login><password>TEST</password></groupInfo>".getBytes(java.nio.charset.StandardCharsets.UTF_8),{(byte)192,1,0,123,0,0,(byte)164,(byte)147,(byte)194},{(byte)171,(byte)205,(byte)239,0}};
  for(int i=0;i<ids.length;i++){byte[] a=TcpProtocol.encode(new TcpMessage(ids[i],commands[i],data[i]));StringBuilder h=new StringBuilder();for(byte b:a)h.append(String.format("%02X",b&255));System.out.println(h);}
 }
}'''
  (p/'CheckServiceFrames.java').write_text(java)
  r=subprocess.run(['java','-m','jdk.compiler/com.sun.tools.javac.Main','-cp',cp,str(p/'CheckServiceFrames.java')],capture_output=True,text=True,timeout=20);assert r.returncode==0,r.stderr
  r=subprocess.run(['java','-cp',str(p)+os.pathsep+cp,'CheckServiceFrames'],capture_output=True,text=True,timeout=15);assert r.returncode==0,r.stderr
  vendor=r.stdout.splitlines()
  python=[cloud(0,1,b'<groupInfo><login>7058</login><password>TEST</password></groupInfo>'),cloud(DID,0,frame(0,123)),cloud(0x00EFCDAB56433211,0,b'\xab\xcd\xef\x00')]
  assert vendor==[v.hex().upper() for v in python],vendor
  ps=SCRIPT.read_text().split("try{\n $svcConfig=")[0]+r'''
[byte[]]$x=[Text.Encoding]::UTF8.GetBytes('<groupInfo><login>7058</login><password>TEST</password></groupInfo>')
[BitConverter]::ToString([TeleofisRadioService01]::CloudFrame(0,1,$x)).Replace('-','')
[BitConverter]::ToString([TeleofisRadioService01]::CloudFrame(70001,0,[byte[]]@(192,1,0,123,0,0,164,147,194))).Replace('-','')
[BitConverter]::ToString([TeleofisRadioService01]::CloudFrame(67498604841579025,0,[byte[]]@(171,205,239,0))).Replace('-','')
};
'''
  # Keep the large ID an explicit invariant decimal value, not a PS hex cast.
  ps=ps.replace('67498604841579025',str(0x00EFCDAB56433211))
  (p/'frames.ps1').write_text(ps)
  env=os.environ|{'XDG_CACHE_HOME':str(p/'cache'),'XDG_CONFIG_HOME':str(p/'config'),'XDG_DATA_HOME':str(p/'store')}
  r=subprocess.run([PWSH,'-NoLogo','-NoProfile','-NonInteractive','-File',str(p/'frames.ps1')],capture_output=True,text=True,timeout=20,env=env);assert r.returncode==0 and not r.stderr,r.stderr
  assert r.stdout.splitlines()==vendor,(r.stdout,vendor)
  return dict(actual_vendor_TcpProtocol_encode_matches_Python_and_CSharp=True,crc='CRC16/ARC polynomialA001 init0, distinct from inner CCITT-FALSE',vectors=vendor,jar_sha256={j.name:hashlib.sha256(j.read_bytes()).hexdigest() for j in jars})

def main():
 vendor=vendor_reference();print('PASS actual vendor JVM frames',flush=True)
 cases=['normal','fragmented','unknown','modem_rejected','cloud_rejected','empty_list','missing_target','duplicate_target','disabled_target','xml_dtd','outer_crc','inner_crc','wrong_did','cloud_timeout','recover_timeout','recover_disconnect','recover_inner_auth','refresh_auth','locked','other_station','duplicate_station','colliding_paths']
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
  results=list(pool.map(run,cases))
 for result in results:print('PASS',result['case'],flush=True)
 report=dict(date='2026-10-29',vendor_reference=vendor,cases=results,limitations='Actual PowerShell7.6.9/Linux TCP loopback; native Windows collector and real cloud server not yet tested. Native configurator service read is separately observed. No external connections in tests.')
 (OUT/'validation-2026-10-29.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
