#!/usr/bin/env python3
"""Build read-only PLC setpoint-feedback display in a new codex_diag_07 copy."""
import base64
import gzip
import hashlib
import json
from pathlib import Path

from build_radio_display_01 import bootstrap

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'artifacts/station-mode-display-01/scripts/StationDiagnostics.txt'
OUT = ROOT / 'artifacts/station-setpoint-display-01'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def module():
    text = BASE.read_text()

    def once(old, new):
        nonlocal text
        assert text.count(old) == 1, old[:80]
        text = text.replace(old, new)

    once('var\n  RouteHasTick,', 'var\n  SpFeedbackHasSample: Boolean;\n  SpFeedbackSampleKey: string;\n  SpFeedbackSampleCounter: Int64;\n  RouteHasTick,')
    once('procedure StationProcessUpdate;\nvar\n', (OUT / 'feedback-core.txt').read_text().rstrip() + '\n\nprocedure StationProcessUpdate;\nvar\n')
    once('  ModeGood: Boolean;\nbegin', '  ModeGood: Boolean;\n  SpState, SpCount, SpColor: Integer;\n  SpCaption, SpNote: string;\nbegin')
    once("begin\n  MapGood := ProcessWord('MapVersion', Map);", "begin\n  SP := 0;\n  MapGood := ProcessWord('MapVersion', Map);")
    once('  ProcessStatus.Text := Status;', '''  SpFeedbackView(DriveMap and RouteLive, SPGood, SP, AliveCounter,
    SpState, SpCount, SpColor, SpCaption, SpNote);
  ProcessSetpointLabel.Text := 'УСТАВКА ПЛК';
  ProcessSetpointNote.Text := SpCaption;
  ProcessSetpointNote.Color := SpColor;
  ProcessScope.Text := 'Уставка: ' + SpCaption + #13#10 + SpNote;
  ProcessMainScope.Text := 'Мониторинг: изменение уставки из SCADA пока недоступно.';
  if (SpState = 4) and (StatusColor <> RGB(165, 50, 50)) then
  begin
    Status := 'ПЛК: ошибка применения уставки';
    Detail := SpCaption + '. ' + SpNote;
    StatusColor := RGB(165, 50, 50);
  end;
  ProcessStatus.Text := Status;''')
    once("  if MapMatches then ProcessMap.Text :=", "  if DriveMap and RouteLive then\n  begin\n    ProcessOPC.Text := ProcessOPC.Text + '; уставка: прочитано ' + IntToStr(SpCount) + ' из 7';\n    if SpCount <> 7 then ProcessOPC.Color := RGB(165, 100, 0);\n  end;\n  if MapMatches then ProcessMap.Text :=")
    return text


def main():
    (OUT / 'scripts').mkdir(parents=True, exist_ok=True)
    code = module()
    assert len(code.encode()) < 65536
    (OUT / 'scripts/StationDiagnostics.txt').write_text(code)
    template = (ROOT / 'tools/drive_display_install_template.ps1').read_text()
    template = template.replace('codex_diag_04', 'codex_diag_07').replace('codex_diag_03', 'codex_diag_06')
    before = "    $processSource=(Get-Item -LiteralPath $processSource).FullName.TrimEnd([char[]]'\\/')"
    after = before + '''
    if(-not (Test-Path -LiteralPath (Join-Path $processSource 'Project.spr') -PathType Leaf)){
        $child=Join-Path $processSource 'codex_diag_06'
        if(Test-Path -LiteralPath (Join-Path $child 'Project.spr') -PathType Leaf){$processSource=$child}
        else{throw 'Choose the codex_diag_06 folder containing Project.spr, Pages.spg and Scripts.'}
    }'''
    assert template.count(before) == 1
    template = template.replace(before, after)
    template = template.replace('Import3 new ReadOnly OPC tags, F9, save. Current PLC may stay map31 for this check.',
                                'Import the seven existing feedback tags into this copy if absent. F9, save. Expected SpFeedbackVersion=1.')
    template = template.replace('Read-only drive display', 'Read-only setpoint feedback display')
    installer = template.replace('__MODULE_GZIP__', base64.b64encode(gzip.compress(code.encode(), mtime=0)).decode())
    installer = installer.replace('__MODULE_SHA__', sha(code.encode())).replace('__OLD_CORE_SHA__', sha(BASE.read_text().strip().encode()))
    (OUT / 'Install-Setpoint-Display-01.ps1').write_text(installer)
    paste = bootstrap(installer).replace('$radio', '$setpoint')
    (OUT / 'Paste-Setpoint-Display-01.ps1').write_text(paste)
    report = dict(date='2026-10-31', sourceProject='codex_diag_06', targetProject='Desktop/codex_diag_07',
                  sourceCoreSHA256=sha(BASE.read_text().strip().encode()), moduleSHA256=sha(code.encode()),
                  installerSHA256=sha(installer.encode()), inlineCharacters=len(paste),
                  feedbackVersion=1, existingReadOnlyTags='artifacts/station-setpoint-feedback-01/masteropc-feedback-tags.json',
                  snapshotPolicy='Two equal complete tuples including working pressure, with observed PLC counter change. This is not an atomic PLC snapshot or a request-ID acknowledgment.',
                  successRequires='Map32, fresh counter, compatible complete good bindings, valid matching pressure, drive1..4, low flags2 and idle phase0',
                  errorCodesUsedOnlyWhenM968=True, M969RequiredForVerifiedCache=True,
                  flagsBeyondBits0and1NotDecoded=True, nativeFaultPriorityPreserved=True,
                  PLCProgramChanged=False, existingPagesPreserved=True, radioAndTimerRecordsPreserved=True,
                  writesOrControlCommandsAdded=False, nativeF9Observed=False, nativeNewDisplayObserved=False)
    observation=OUT/'native-observation-2026-10-31.json'
    if observation.exists():
        native=json.loads(observation.read_text())
        report.update(nativeNewDisplayObserved=native['nativeNewDisplayObserved'],
                      nativeScriptExecutionObserved=native['nativeScriptExecutionObserved'],
                      nativeF9Observed=native['explicitF9CommandObserved'],nativeObservation=observation.name)
    (OUT / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print('Built setpoint feedback copy:', len(paste), 'inline characters;', len(code.encode()), 'module bytes')


if __name__ == '__main__':
    main()
