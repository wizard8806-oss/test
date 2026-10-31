#!/usr/bin/env python3
"""Prepare a source-checked telemetry change plan, without modifying PDW.
The plan cannot be deployed: receive buffers and new export fields require
allocation and native validation before a PLC revision is built.
"""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/fatek-process-map-01'

def main():
 r=json.loads((OUT/'review.json').read_text())
 normal=next(t for t in r['master_tables'] if t['register']=='R5000')
 changes=[]
 for drive in r['drive_frequency_exports']:
  row=normal['rows'][drive['normal_poll_row']-1]
  assert row[0]==drive['drive'] and row[1:3]==[1,1] and row[3]==13 and row[5]==4 and row[6]==0x1003+1
  changes.append(dict(drive=drive['drive'],tableRow=drive['normal_poll_row'],
   existingFrequencyBuffer=drive['frequency_source_buffer'],existingFrequencyExport=drive['frequency_register'],
   existingFreshnessState=drive['frequency_state_register'],
   proposedNativeStartPDU=0x1000,proposedNativeWordCount=7,
   proposedTableAddressOneBased=0x1000+1,
   receiveBuffer=None,newCurrentExport=None,newFaultCodeExport=None,
   preserveOldFrequencyDataFlow=True,
   requiredCopiesAndChecks=['On valid response for this slave/row, copy word3 to existing frequency data flow','Publish fault word1, state word0 and current word6 with the same successful-snapshot identity','Invalidate the complete snapshot on timeout, bad response or restart','Do not enlarge the old D200/D203/D206/D209 destination in place: adjacent words are already used']))
 assert len(changes)==4 and not r['current_reads']
 report=dict(status='Plan only; no PLC patch generated or deployed',sourcePDWSha256=r['source_sha256'],
  manual=dict(url='https://m-driver.by/wp-content/uploads/2025/11/Manual-M-driver-900G_900M.pdf',version='1.26',registerPage=50,modbusPage=52,maxConsecutiveReadWords=12),
  block=dict(startPDU=0x1000,count=7,fields={'0':'native drive state','1':'native fault code','2':'frequency setpoint','3':'actual frequency','4':'speed','5':'output voltage','6':'output current'},
   frequencyFactorReference=0.1,currentFactorReference=0.1,liveFactorsVerified=False),
  rowChanges=changes,
  performance=dict(normalPollFramesBefore=18,normalPollFramesProposed=18,
   addedResponseDataBytesPerFullRound=(7-1)*2*4,
   addedWireTimeSecondsAt9600_8N1=(7-1)*2*4*10/9600,
   limit='Byte-time estimate only; no measured cycle time or speed guarantee. Keep command/status scheduling and test freshness under fault/timeout.'),
  pumpSelection=dict(mode='eligible_pump_set',optionalPerStation=True,existingPLCTransaction=True,changeInStop=True,notFixedRunningCount=True),
  unresolved=['Allocate nonoverlapping buffers and exports after memory audit','Preserve row acceptance/freshness and existing frequency consumers','Provide independent monotonic station heartbeat','Native WinProladder validation and bench tests of the future revision'],
  deployable=False,PLCModified=False)
 memory=OUT/'telemetry-memory-review-2026-10-30.json'
 if memory.exists():
  evidence=json.loads(memory.read_text())
  assert evidence['sourceSHA256']==report['sourcePDWSha256'] and evidence['originalSourceUnchanged']
  assert not evidence['PLCModified'] and all(not p['allocated'] for p in evidence['proposedRangesForReview'])
  report['memoryReview']=memory.name
  report['candidateRangesForNativeReview']=evidence['proposedRangesForReview']
  report['allocationStatus']='Candidates only; indirect/block access and external HMI/OPC review remain unresolved'
 assert report['block']['count']<=report['manual']['maxConsecutiveReadWords']
 (OUT/'drive-telemetry-extension-plan.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 print('Prepared four checked block-read replacements;18 normal frames retained in plan; PDW unchanged.')

if __name__=='__main__':main()
