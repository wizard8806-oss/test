#!/usr/bin/env python3
"""Real-data overview, native stream and private-copy preservation checks."""
import os
import re
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import prepare_native_ui_event_probe as candidate
from build_native_operator_console_01 import native_navigation_grid_pages, parse_pages, repair_visual_page_style
from native_overview_panel import overview_module, overview_pages
from validate_native_operator_console_01 import runtime
from validate_native_ui_event_probe import fixture


EXTRA = r'''
 Check(UiOverviewMetric0Value.Text='2','catalog count, no demo stations');
 Check(UiOverviewMetric1Value.Text='2','both station counters progressed');
 Check(UiOverviewMetric3Value.Text='0','no stale stations');
 Check(UiOverviewMetric2Value.Text='0','known zero fault code');
 V[0,6].IsGoodQuality:=False;V[1,6].IsGoodQuality:=False;OperatorUiUpdate;
 Check(UiOverviewMetric2Value.Text='Нет данных','unknown faults are not zero');
 Check(UiOverviewPumpInfo.Text='Нет данных','unknown pump code stays unknown');
 V[0,6].IsGoodQuality:=True;V[0,6].OriginalAsInt:=7;OperatorUiUpdate;
 Check(UiOverviewMetric2Value.Text='1','one confirmed VFD1 fault');
 Check(UiOverviewMetric2Note.Text='Подтверждено тегов ПЧ 1: 1','partial coverage explicit');
 Check(UiOverviewPumpInfo.Text='1: ошибка; 2-4: н/д','no invented pump2-4 status');
 Tick(1045,30001,129);
 Check(Pos('4 с',UiOverviewUpdated.Text)>0,'age is counter progress, not repaint');
 Tick(1050,30001,134);Tick(1056,30001,140);
 Check(UiOverviewMetric1Value.Text='1','stale station excluded');
 Check(UiOverviewMetric3Value.Text='1','stale station counted');
 Check(UiOverviewMetric2Value.Text='Нет данных','stale fault is not a current alarm');
 Check(UiOverviewUpdated.Text='Нет обновлений','stale age cannot look fresh');
 Tick(1057,30002,141);
 Check(UiOverviewMetric1Value.Text='2','progress restores overview');
 V[0,0].ComputerName:='wrong';OperatorUiUpdate;
 Check(UiOverviewMetric1Value.Text='1','wrong endpoint excluded');
 V[1,0].OriginalAsInt:=31;OperatorUiUpdate;
 Check(UiOverviewMetric1Value.Text='0','wrong map excluded');
 Check(UiOverviewMetric3Value.Text='2','both invalid counted');
 Check(V[0,5].OriginalAsInt=400,'overview never writes setpoint');
'''


def main():
    with tempfile.TemporaryDirectory(prefix='native-overview-') as tmp:
        root=Path(tmp);source=root/'codex_diag_11_review_tabs_test0001';fixture(source)
        raw=native_navigation_grid_pages(repair_visual_page_style((source/'Pages.spg').read_bytes(),True))
        (source/'Pages.spg').write_bytes(raw)
        (source/'Scripts/Scripts.ssc').write_bytes(candidate.pressure_display_scripts((source/'Scripts/Scripts.ssc').read_bytes()))
        before=candidate.inventory(source);pins=(before['Pages.spg'],before['Scripts/Scripts.ssc'])
        out=root/'codex_diag_11_review_overview_test0001'
        report=candidate.prepare_overview_panel(source,out,*pins)
        assert report['changedScripts']==['OperatorConsole'] and report['hardwareCommands']==0
        assert not report['WindowsCompileObserved'] and not report['visualAcceptancePassed']
        assert candidate.inventory(source)==before and not list((out/'Scripts/Compiled').iterdir())
        for name,digest in before.items():
            if name in ('Pages.spg','Scripts/Scripts.ssc') or name.startswith('Scripts/Compiled/'):continue
            assert candidate.SHA((out/name).read_bytes())==digest,name
        updated=(out/'Pages.spg').read_bytes();old_pages=parse_pages(raw);new_pages=parse_pages(updated)
        uids=[];names=[];added=[]
        for old,new in zip(old_pages,new_pages):
            assert old['header']==new['header']
            if old['name']!='PageUiOverview':assert old['objects']==new['objects']
            prior={o['name']:o for o in old['objects']}
            for z,obj in enumerate(new['objects']):
                names.append(obj['name']);uids.append(struct.unpack_from('<I',obj['body'],107)[0])
                x,y,w,h=struct.unpack_from('<4f',obj['body'],8)
                assert x>=0 and y>=64 and w>0 and h>0 and x+w<=1920 and y+h<=1080,obj['name']
                if new['name']!='PageUiOverview':continue
                assert struct.unpack_from('<I',obj['body'],54)[0]==z
                if obj['name'] not in prior:
                    added.append(obj['name']);assert struct.unpack_from('<q',obj['body'],75)[0]==-1
                else:
                    saved=prior[obj['name']];restored=bytearray(obj['record']);start=6+len(obj['name'].encode())
                    for offset,length in ((8,16),(32,4),(54,4)):
                        restored[start+offset:start+offset+length]=saved['body'][offset:offset+length]
                    assert restored==saved['record'],obj['name']
        assert len(set(names))==len(names) and len(set(uids))==len(uids)
        assert len(added)==35,(len(added),added)
        audit=candidate.audit(out);assert audit['buttons']==15 and not audit['findings']
        page=next(p for p in new_pages if p['name']=='PageUiOverview')
        controls={o['name']:o for o in page['objects']}
        assert controls['UiRow0Open']['body'][75:83]==next(o for p in old_pages for o in p['objects'] if o['name']=='UiRow0Open')['body'][75:83]
        # No noninteractive label/container is allowed to sit over the action.
        button=struct.unpack_from('<4f',controls['UiRow0Open']['body'],8)
        button_z=struct.unpack_from('<I',controls['UiRow0Open']['body'],54)[0]
        ax,ay,aw,ah=button
        for obj in page['objects'][button_z+1:]:
            bx,by,bw,bh=struct.unpack_from('<4f',obj['body'],8)
            assert min(ax+aw,bx+bw)<=max(ax,bx) or min(ay+ah,by+bh)<=max(ay,by),obj['name']
        old_scripts=candidate.scripts((source/'Scripts/Scripts.ssc').read_bytes())
        new_scripts=candidate.scripts((out/'Scripts/Scripts.ssc').read_bytes())
        assert len(old_scripts)==len(new_scripts)==48
        for id_,old in old_scripts.items():
            new=new_scripts[id_];assert old['name']==new['name'] and old['meta']==new['meta']
            if id_!=7:assert old==new
        for label,project,pages_sha,scripts_sha,target in [
            ('existing',source,*pins,out),
            ('bad-digest',source,'0'*64,pins[1],root/'codex_diag_11_review_overview_bad00001'),
            ('wrong-family',root,pins[0],pins[1],root/'codex_diag_11_review_overview_bad00002'),
            ('duplicate',out,candidate.SHA(updated),candidate.SHA((out/'Scripts/Scripts.ssc').read_bytes()),root/'codex_diag_11_review_overview_bad00003')]:
            existing=candidate.inventory(target) if target.exists() else None
            try:candidate.prepare_overview_panel(project,target,pages_sha,scripts_sha)
            except ValueError:pass
            else:raise AssertionError('Expected refusal '+label)
            assert candidate.inventory(source)==before
            if existing is None:assert not target.exists()
            else:assert candidate.inventory(target)==existing
        try:overview_module(new_scripts[7]['body'])
        except ValueError:pass
        else:raise AssertionError('Module replay accepted')
        assert not re.search(r'\.Value\s*:=|SetVariableValue|AddActionMessage',new_scripts[7]['body'])
        if os.environ.get('CODEX_PAGE_LOADER')=='1':
            from verify_scada_native_loader_01 import read_pages
            assert len(read_pages(out/'Pages.spg')['objects'])==102+len(added)
        pascal=root/'pascal';pascal.mkdir();print(runtime(pascal,overview_module,EXTRA))
        entry=subprocess.run([sys.executable,'-I','-B',str(Path(candidate.__file__)),'--help'],capture_output=True,text=True)
        assert entry.returncode==0 and 'overview-panel' in entry.stdout
        print('PASS native overview: 35 added Text controls, 137 total, 15 bindings; 5 other pages/47 scripts/resources preserved; private-copy refusals4; no Windows GUI acceptance')


if __name__=='__main__':main()
