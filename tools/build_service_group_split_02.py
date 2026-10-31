#!/usr/bin/env python3
"""Prepare a separate Service-group pilot and stop on server session replacement."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'artifacts/teleofis-radio-service-01'
OUT=ROOT/'artifacts/teleofis-radio-service-02'

def sha(b):return hashlib.sha256(b).hexdigest()

def main():
    source=(OLD/'Run-Radio-Service-Collector-01.ps1').read_text()
    assert sha(source.encode())=='e334ef94c55230352441ba44471598faa2212e4dcfa7217a46d2f9d952624585'
    before="   else{$state=4;$code='SERVICE_UNEXPECTED_FAILURE'}"
    after=before+"\n   if($code -eq 'CLOUD_SESSION_DISCONNECTED' -or $code -eq 'CLOUD_GROUP_ACCESS_REJECTED'){$code='CLOUD_SESSION_REPLACED';$state=4;$svcFatal=$true}"
    old_fatal="  if($svcFatal){Write-Host ('ERROR: '+$code+'. Check the local Service/modem credentials or target group. No passwords were saved.') -ForegroundColor Red;break}"
    new_fatal="  if($svcFatal){\n   if($code -eq 'CLOUD_SESSION_REPLACED'){Write-Host 'ERROR: CLOUD_SESSION_REPLACED. Another client replaced the cloud session. Stop the competing Service client; automatic reconnect is paused.' -ForegroundColor Red}\n   else{Write-Host ('ERROR: '+$code+'. Check the local Service/modem credentials or target group. No passwords were saved.') -ForegroundColor Red}\n   break\n  }"
    assert source.count(before)==source.count(old_fatal)==1
    code=source.replace(before,after).replace(old_fatal,new_fatal)
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'Run-Radio-Service-Collector-02.ps1').write_text(code)
    template=(ROOT/'tools/service_group_split_template.ps1').read_text()
    template=template.replace('__OLD_SHA__',sha(source.encode())).replace('__NEW_SHA__',sha(code.encode()))
    template=template.replace('__BEFORE_CATCH__',before).replace('__AFTER_CATCH__',after)
    template=template.replace('__BEFORE_FATAL__',old_fatal).replace('__AFTER_FATAL__',new_fatal)
    (OUT/'Set-Service-Group-And-Run-02.ps1').write_text(template)
    manifest=dict(date='2026-10-30',status='Separate-Service-group pilot prepared; new group ID not yet supplied',
        groupId=None,MainGroup=7058,oldCollectorPreserved=True,configurationSecretsStored=False,
        oldCollectorSHA256=sha(source.encode()),newCollectorSHA256=sha(code.encode()),
        CSharpTransportUnchanged=True,sessionReplacementPolicy='Publish CLOUD_SESSION_REPLACED and stop, including replacement after modem authentication; never relabel it as wrong password or enter a reconnect contest',
        newGroupRequirements='Different from7058; only the target Service-channel record; Main entries unchanged',
        nativeCloudSuccess=False,centralCitySchedulerImplemented=False)
    binding=OUT/'group-binding.json'
    if binding.exists():
        actual=json.loads(binding.read_text());group_id=int(actual['groupId'])
        assert group_id>0 and group_id!=7058 and actual['correctServiceMembershipObserved']
        assert actual['targetImei']=='863906061228379'
        prompt="$inputId=(Read-Host 'NEW ServiceDiag group ID (not Main7058)').Trim()"
        assert template.count(prompt)==1
        delivery='Start-ServiceDiag-'+str(group_id)+'.ps1'
        (OUT/delivery).write_text(template.replace(prompt,"$inputId='"+str(group_id)+"'"))
        observed=actual['radioValuesFrom9336Observed']
        manifest.update(status=('ServiceDiag9336 native remote radio read and SCADA display confirmed' if observed else 'ServiceDiag9336 correct Service record confirmed; collector02 prepared, native run pending'),
            groupId=group_id,groupCreated=True,groupChannelValidated=True,inlineDelivery=delivery,
            nativeCloudSuccess=observed,groupBinding=binding.name)
        if actual.get('nativeObservation'):
            manifest['nativeObservation']=actual['nativeObservation']
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print('Separate group delivery ready:',len(template),'characters, new collector',sha(code.encode()))

if __name__=='__main__':main()
