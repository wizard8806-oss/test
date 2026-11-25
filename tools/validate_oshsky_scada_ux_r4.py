#!/usr/bin/env python3
"""Compile the actual read-only UX helper with in-memory inputs, not SCADA/SQL."""
from pathlib import Path
import os
import subprocess
import tempfile
from _runtime import ROOT, fpc, fpc_units


TEST = r'''
var N,I: Integer; S: string;
procedure Check(OK: Boolean; const Name: string);
begin if not OK then begin WriteLn('FAIL ',Name); Halt(1); end; Inc(N); end;
function Same(const A,B:string):Boolean;begin Result:=A=B;end;
function Find(const A,B:string):Integer;begin Result:=Pos(A,B);end;
begin
  {$ifdef windows}SetMultiByteConversionCodePage(65001);{$endif}
  Check(R4ModeGroup(10)=R4ModeGroup(12),'AUTO phases');
  Check(R4ModeGroup(20)=R4ModeGroup(22),'MANUAL phases');
  Check(R4ModeGroup(91)=-1,'unknown mode');
  Check(Same(R4AutoSetText(True,0),'Исключён из АВТО'),'excluded auto');
  Check(Same(R4AutoSetText(True,1),'Включён в АВТО'),'included auto');
  Check(Find('не подтверждено',R4AutoSetText(False,0))>0,'unknown membership');
  Check(Find('не подтверждено',R4AutoSetText(True,2))>0,'invalid membership');
  for I:=1 to 4 do begin
    Check(Same(R4PumpRole(True,12,I,15,I),'Ведущий'),'leader');
    Check(Same(R4PumpRole(True,12,(I mod 4)+1,15,I),'Ведомый'),'follower command');
    Check(Same(R4PumpRole(True,12,(I mod 4)+1,0,I),'Команда RUN не выдана'),'no invented reserve');
    Check(Same(R4PumpRole(True,12,0,15,I),'Роль не подтверждена'),'no inferred follower without leader');
    Check(Same(R4PumpRole(True,20,I,15,I),'Ручной режим шкафа'),'manual');
    Check(Same(R4PumpRole(False,12,I,15,I),'Роль не подтверждена'),'unknown core');
    Check(Find('Нет данных ПЧ',R4PumpHint(True,False,True,True,0,0,0,I))>0,'own unknown');
    Check(Find('код неисправности 53',R4PumpHint(True,True,True,True,53,0,15,I))>0,'fault');
    Check(Find('данные тока',R4PumpHint(True,True,True,False,0,250,15,I))>0,'current only stale');
    Check(Find('частота пока нулевая',R4PumpHint(True,True,True,True,0,0,15,I))>0,'RUN with zero');
    Check(Find('частота ненулевая',R4PumpHint(True,True,True,True,0,250,0,I))>0,'nonzero without command not new trip');
    Check(Same(R4DriveState(True,True,True,1,0,250,15,I),'ПЧ работает'),'fresh drive state');
    Check(Same(R4DriveState(True,True,True,3,0,0,0,I),'Остановлен'),'confirmed stopped');
    Check(Same(R4DriveState(True,True,True,3,0,0,15,I),'Команда RUN выдана'),'command pending');
    Check(Find('требует проверки',R4DriveState(True,True,True,1,0,0,0,I))>0,'zero Hz alone does not confirm stopped');
    Check(Find('различаются',R4DriveState(True,True,True,3,0,250,15,I))>0,'contradictory state');
    Check(Find('Авария',R4DriveState(True,True,True,3,53,0,0,I))>0,'fault precedes stopped');
  end;
  Check(Find('71582788 ч 15 мин',R4RuntimeSpread(True,0,4294967295,60,120))>0,'uint32 runtime spread');
  Check(Find('0 ч 0 мин',R4RuntimeSpread(True,0,0,0,0))>0,'zero runtime valid');
  Check(Find('нет полных',R4RuntimeSpread(False,0,1,2,3))>0,'unknown runtime');
  Check(Find('нет полных',R4RuntimeSpread(True,-1,1,2,3))>0,'negative runtime');
  R4Observe(0,False,100,0,0,0,0,'t0');
  R4Observe(0,True,101,65535,12,1,1,'t1');
  Check(Find('пока не зарегистрированы',R4RecentEvents(0))>0,'first sample silent');
  R4Observe(0,True,102,0,10,1,1,'t2');
  Check(Find('пока не зарегистрированы',R4RecentEvents(0))>0,'wrap and AUTO phase not events');
  R4Observe(0,True,103,0,20,2,3,'partial');
  Check(Find('partial',R4RecentEvents(0))=0,'same counter no events');
  R4Observe(0,True,104,1,12,2,3,'t3'); S:=R4RecentEvents(0);
  Check(Find('Ведущий насос: 2',S)>0,'leader changed');
  Check(Find('выдал команду RUN насосу 2',S)>0,'command not physical run');
  R4Observe(0,True,104.5,1,12,2,3,'duplicate');
  Check(R4RecentEvents(0)=S,'duplicate tick');
  R4Observe(0,False,105,1,0,0,0,'lost'); S:=R4RecentEvents(0);
  R4Observe(0,False,106,1,0,0,0,'lost again');
  Check(R4RecentEvents(0)=S,'one lost event');
  R4Observe(0,True,107,4,20,0,0,'return'); S:=R4RecentEvents(0);
  Check(Find('восстановлен',S)>0,'recovery');
  Check(Find('снял команду',S)=0,'no invented missed stop');
  R4Observe(1,True,100,1,0,0,0,'other');
  Check(Find('пока не зарегистрированы',R4RecentEvents(1))>0,'station isolated');
  R4Observe(0,True,120,5,0,0,0,'gap');
  Check(Find('Перерыв наблюдения',R4RecentEvents(0))>0,'clock gap resets baseline');
  for I:=1 to 12 do R4Observe(1,True,100+I,1+I,0,0,I mod 2,'event'+IntToStr(I));
  S:=R4RecentEvents(1); Check(Find('event1 ',S)=0,'bounded ring');
  Check(Find('event12 ',S)>0,'latest event retained');
  Check(R4RecentEvents(0)<>S,'independent rings');
  Check(Find('пока не зарегистрированы',R4RecentEvents(-1))>0,'invalid station');
  Check(Find('пока не зарегистрированы',R4RecentEvents(16))>0,'station upper bound');
  WriteLn('PASS read-only SCADA UX: ',N,' assertions; no native Client or archive proof');
end.
'''


def main():
    source = ROOT / 'assets/scada/oshsky-ux-r4/OperatorUxR4.txt'
    original = source.read_text(encoding='utf8')
    import json
    layout = json.loads((source.parent / 'layout.json').read_text(encoding='utf8'))
    assert len(layout['cards']) == 4
    rects = [row['rect'] for row in layout['cards']]
    assert len({(r[2], r[3]) for r in rects}) == 1
    for left, right in zip(rects, rects[1:]):
        assert left[0] + left[2] < right[0]
    for row in layout['cards']:
        for name, (x, y, width, height) in layout['cardTemplate']['fields'].items():
            assert x >= 0 and y >= 0 and x + width <= row['rect'][2] and y + height <= row['rect'][3], name
    body = original.split('implementation\n', 1)[1].removesuffix('end.\n')
    compiler = fpc()
    with tempfile.TemporaryDirectory(prefix='oshsky-ux-r4-') as folder:
        root = Path(folder)
        program = root / 'check.pas'
        program.write_text('program CheckUX;\n{$mode delphi}{$H+}{$B+}{$codepage utf8}\nuses {$ifdef unix}cwstring,{$endif}SysUtils;\n'
                           + body + TEST, encoding='utf8')
        command = [str(compiler), '-Mdelphi', '-Cr', '-Co', '-gl']
        command += ['-Fu' + str(p) for p in fpc_units(compiler)]
        result = subprocess.run(command + [str(program)], cwd=root, text=True, capture_output=True, timeout=30)
        assert result.returncode == 0, result.stdout + result.stderr
        result = subprocess.run([str(program.with_suffix('.exe' if os.name == 'nt' else ''))],
                                cwd=root, text=True, capture_output=True, timeout=20)
        assert result.returncode == 0, result.stdout + result.stderr
        assert source.read_text(encoding='utf8') == original
        print(result.stdout.strip())


if __name__ == '__main__':
    main()
