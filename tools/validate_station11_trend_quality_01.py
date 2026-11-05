#!/usr/bin/env python3
"""Static source clues and reference quality-gate examples for Station 11.

This does not run Pascal, connect to OPC, change a project, or write an archive.
Source clues are not control-flow, write-safety or native gap verification.
The reference model is not inferred from the supplied saved Pascal body.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import re
from pathlib import Path


def load_scripts(project: Path, tool_dir: Path) -> tuple[dict, str]:
    parser_path = tool_dir / "import_native_empty_timer.py"
    spec = importlib.util.spec_from_file_location("native_timer_importer", parser_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("reviewed native parser unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = (project / "Scripts" / "Scripts.ssc").read_bytes()
    return module.copy.scripts(raw), hashlib.sha256(raw).hexdigest()


def require(condition: bool, name: str) -> None:
    if not condition:
        raise AssertionError(name)
    print(f"PASS {name}")


def executable_text(body: str) -> str:
    """Mask Pascal comments/literals without joining adjacent code tokens."""
    out = list(body)
    i, size = 0, len(body)
    while i < size:
        start = i
        if body.startswith('//', i):
            end = body.find('\n', i)
            i = size if end < 0 else end
        elif body[i] == "'":
            i += 1
            while i < size:
                if body[i] in '\r\n':
                    raise ValueError('Unterminated Pascal string literal')
                if body[i] == "'":
                    i += 1
                    if i < size and body[i] == "'":
                        i += 1
                        continue
                    break
                i += 1
            else:
                raise ValueError('Unterminated Pascal string literal')
        elif body[i] == '{' or body.startswith('(*', i):
            stack = ['}' if body[i] == '{' else '*)']
            i += 1 if body[i] == '{' else 2
            while stack:
                if i >= size:
                    raise ValueError('Unterminated Pascal block comment')
                if body.startswith(stack[-1], i):
                    i += len(stack.pop())
                elif body[i] == '{':
                    stack.append('}'); i += 1
                elif body.startswith('(*', i):
                    stack.append('*)'); i += 2
                else:
                    i += 1
        else:
            i += 1
            continue
        for pos in range(start, i):
            if out[pos] not in '\r\n':
                out[pos] = ' '
    return ''.join(out)


def static_clues(body: str) -> dict[str, bool]:
    code = executable_text(body)
    flat = re.sub(r'\s+', '', code).lower()
    present = lambda *parts: all(re.sub(r'\s+', '', p).lower() in flat for p in parts)
    writes_source = re.search(
        r'\b\w*(?:PressurePV_x100|PressureSP_x100|PressureSP_Command|Vfd1FreqRaw)'
        r'\s*\.\s*Value\s*:=|\bWriteValue\b', code, re.I)
    return {
        'map-clues-present': present('codex_Device1_MapVersion.IsGoodQuality', '=32'),
        'timestamp-age-clues-present': present('PlcAliveCounter.Timestamp', '<=15.0'),
        'pv-clues-present': present('PressurePV_x100.IsGoodQuality', 'PressureSourceOK.IsGoodQuality',
                                   'PressureSourceOK.OriginalAsInt=1', 'PvRaw>=0', 'PvRaw<=1600'),
        'sp-clues-present': present('PressureSP_x100.IsGoodQuality', 'SpRaw>=10', 'SpRaw<=1190', 'SpRaw mod 10'),
        'frequency-clues-present': present('Vfd1FreqRaw.IsGoodQuality', 'Vfd1FreqState.IsGoodQuality',
                                          'FreqState=1', 'FreqState=2', 'FreqRaw<=500'),
        'named-target-assignments-present': present('TrendPressurePVBar.Value:=',
                                                   'TrendPressureSPBar.Value:=', 'TrendVfd1FreqHz.Value:='),
        'three-archive-disable-markers-present': len(re.findall(r'\.\s*Archiving\s*:=\s*False\b', code, re.I)) == 3,
        'no-recognized-direct-source-assignment': writes_source is None,
    }


def gate(x: dict) -> dict:
    """Reference contract, not execution or reconstruction of Script_49.

    Frequency needs common PLC freshness unless separate fresh-source evidence
    is explicitly supplied. Archive disable alone does not establish a gap.
    """
    map_ok = x["map_good"] and x["map"] == 32
    plc_fresh = x["counter_good"] and x.get('counter_progress_seen', False) and 0 <= x["age"] <= 15
    pv_ok = (map_ok and plc_fresh and x["pv_good"] and x["source_good"]
             and x["source_ok"] == 1 and 0 <= x["pv_raw"] <= 1600)
    sp_ok = (map_ok and plc_fresh and x["sp_good"]
             and 10 <= x["sp_raw"] <= 1190 and x["sp_raw"] % 10 == 0)
    freq_fresh = plc_fresh or x.get('freq_independent_fresh', False)
    freq_ok = (map_ok and freq_fresh and x["freq_good"] and x["state_good"]
               and ((x["state"] == 1 and x["freq_raw"] == 0)
                    or (x["state"] == 2 and 1 <= x["freq_raw"] <= 500)))
    out = dict(x["previous"])
    for key, ok, value in (
        ("pv", pv_ok, x["pv_raw"] / 100.0),
        ("sp", sp_ok, x["sp_raw"] / 100.0),
        ("freq", freq_ok, x["freq_raw"] / 10.0),
    ):
        out[key + "_archive"] = ok
        out[key + "_valid"] = ok
        if ok:
            out[key] = value
    return out


def sample(**overrides: object) -> dict:
    x = {
        "map_good": True, "map": 32, "counter_good": True, "age": 1,
        "counter_progress_seen": True,
        "pv_good": True, "source_good": True, "source_ok": 1, "pv_raw": 390,
        "sp_good": True, "sp_raw": 410,
        "freq_good": True, "state_good": True, "state": 2, "freq_raw": 120,
        "previous": {"pv": 3.7, "pv_archive": False, "sp": 3.7,
                      "sp_archive": False, "freq": 12.0, "freq_archive": False},
    }
    x.update(overrides)
    return x


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-directory", type=Path, required=True)
    ap.add_argument("--tool-directory", type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()

    scripts, scripts_sha = load_scripts(args.project_directory, args.tool_directory)
    row = scripts.get(50)
    if not row or row.get("name") != "Script_49":
        raise RuntimeError("expected saved Script_49 not found")
    body = row["body"]
    print("scripts-sha256:", scripts_sha)
    print("script-49-body-sha256:", hashlib.sha256(body.encode("utf-8")).hexdigest())

    print('source-check-scope: lexical presence only; not control flow, target binding or write-safety proof')
    for name, ok in static_clues(body).items():
        require(ok, 'static-clue: ' + name)

    valid = gate(sample())
    require(valid["pv_archive"] and valid["sp_archive"] and valid["freq_archive"],
            "valid-sample-enables-three-independent-rows")

    invalid = gate(sample(source_ok=0, previous=valid))
    require(not invalid["pv_archive"] and invalid["pv"] == valid["pv"],
            "valid-invalid-keeps-value-but-disables-pv-archive")
    require(not invalid['pv_valid'], 'invalid-pv-is-unavailable-despite-retained-number')
    require(invalid["sp_archive"] and invalid["freq_archive"],
            "invalid-pv-does-not-suppress-good-sp-or-frequency")

    recovered = gate(sample(pv_raw=400, previous=invalid))
    require(recovered["pv_archive"] and recovered["pv"] == 4.0,
            "invalid-valid-resumes-pv-with-one-raw-conversion")

    stale = gate(sample(age=16, previous=valid))
    require(not stale["pv_archive"] and not stale["sp_archive"],
            "stale-plc-gates-pressure-and-setpoint")
    require(not stale['freq_archive'], 'stale-plc-also-gates-frequency-without-independent-freshness')
    independent = gate(sample(age=16, freq_independent_fresh=True, previous=valid))
    require(independent['freq_valid'] and not independent['pv_valid'],
            'independent-frequency-requires-explicit-freshness-evidence')
    startup = gate(sample(counter_progress_seen=False, previous=valid))
    require(not any(startup[k+'_valid'] for k in ['pv','sp','freq']),
            'a-single-startup-counter-sample-is-not-progression-proof')
    fresh = gate(sample(age=0, previous=stale))
    require(fresh["pv_archive"] and fresh["sp_archive"], "fresh-counter-restores-valid-pressure-rows")

    zero = gate(sample(pv_raw=0, source_ok=1, state=1, freq_raw=0))
    require(zero["pv_archive"] and zero["pv"] == 0.0, "confirmed-pressure-zero-is-valid")
    require(zero["freq_archive"] and zero["freq"] == 0.0, "stopped-state-zero-frequency-is-valid")

    bad_quality = gate(sample(source_good=False, previous=valid))
    require(not bad_quality["pv_archive"] and bad_quality["sp_archive"],
            "bad-source-quality-breaks-only-pv")
    wrong_map = gate(sample(map=31, previous=valid))
    require(not wrong_map["pv_archive"] and not wrong_map["sp_archive"],
            "wrong-map-version-gates-pressure-rows")
    for key in ['map_good','counter_good','pv_good','sp_good','freq_good','state_good']:
        require(not gate(sample(**{key:False}))[{'map_good':'pv','counter_good':'freq','pv_good':'pv',
                    'sp_good':'sp','freq_good':'freq','state_good':'freq'}[key]+'_valid'],
                'reference-bad-quality: '+key)
    print('reference-examples: PASS; this model is independent of the supplied Pascal body')
    print('native-quality-gap-acceptance: UNVERIFIED')
    print('execution-scope: Python reference contract only; Pascal and native archive not executed')


if __name__ == "__main__":
    main()

