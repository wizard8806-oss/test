#!/usr/bin/env python3
"""Static contract checks and synthetic quality-gate cases for Station 11.

This does not run Pascal, connect to OPC, change a project, or write an archive.
The source body is parsed from an explicitly supplied saved SCADA copy.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
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


def gate(x: dict) -> dict:
    """Pure synthetic mirror of the predicates and assignments in Script_49."""
    map_ok = x["map_good"] and x["map"] == 32
    plc_fresh = x["counter_good"] and 0 <= x["age"] <= 15
    pv_ok = (map_ok and plc_fresh and x["pv_good"] and x["source_good"]
             and x["source_ok"] == 1 and 0 <= x["pv_raw"] <= 1600)
    sp_ok = (map_ok and plc_fresh and x["sp_good"]
             and 10 <= x["sp_raw"] <= 1190 and x["sp_raw"] % 10 == 0)
    freq_ok = (map_ok and x["freq_good"] and x["state_good"]
               and ((x["state"] == 1 and x["freq_raw"] == 0)
                    or (x["state"] == 2 and 1 <= x["freq_raw"] <= 500)))
    out = dict(x["previous"])
    for key, ok, value in (
        ("pv", pv_ok, x["pv_raw"] / 100.0),
        ("sp", sp_ok, x["sp_raw"] / 100.0),
        ("freq", freq_ok, x["freq_raw"] / 10.0),
    ):
        out[key + "_archive"] = ok
        if ok:
            out[key] = value
    return out


def sample(**overrides: object) -> dict:
    x = {
        "map_good": True, "map": 32, "counter_good": True, "age": 1,
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

    checks = {
        "map-quality-and-version": "codex_Device1_MapVersion.IsGoodQuality" in body and "= 32" in body,
        "plc-freshness-15s": "PlcAliveCounter.Timestamp" in body and "<= 15.0" in body,
        "pv-quality-source-mask-and-range": all(s in body for s in (
            "PressurePV_x100.IsGoodQuality", "PressureSourceOK.IsGoodQuality",
            "PressureSourceOK.OriginalAsInt = 1", "PvRaw >= 0", "PvRaw <= 1600")),
        "sp-quality-and-range": all(s in body for s in (
            "PressureSP_x100.IsGoodQuality", "SpRaw >= 10", "SpRaw <= 1190", "SpRaw mod 10")),
        "frequency-zero-state-and-range": all(s in body for s in (
            "Vfd1FreqRaw.IsGoodQuality", "Vfd1FreqState.IsGoodQuality",
            "FreqState = 1", "FreqState = 2", "FreqRaw <= 500")),
        "internal-targets-only": all(s in body for s in (
            "TrendPressurePVBar.Value :=", "TrendPressureSPBar.Value :=", "TrendVfd1FreqHz.Value :=")),
        "invalid-disables-per-row-archive": body.count(".Archiving := False") == 3,
    }
    for name, ok in checks.items():
        require(ok, name)
    require(not any(s in body for s in (
        "PressurePV_x100.Value :=", "PressureSP_x100.Value :=",
        "PressureSP_Command.Value :=", "Vfd1FreqRaw.Value :=", "WriteValue")),
        "no-source-or-command-assignment")

    valid = gate(sample())
    require(valid["pv_archive"] and valid["sp_archive"] and valid["freq_archive"],
            "valid-sample-enables-three-independent-rows")

    invalid = gate(sample(source_ok=0, previous=valid))
    require(not invalid["pv_archive"] and invalid["pv"] == valid["pv"],
            "valid-invalid-keeps-value-but-disables-pv-archive")
    require(invalid["sp_archive"] and invalid["freq_archive"],
            "invalid-pv-does-not-suppress-good-sp-or-frequency")

    recovered = gate(sample(pv_raw=400, previous=invalid))
    require(recovered["pv_archive"] and recovered["pv"] == 4.0,
            "invalid-valid-resumes-pv-with-one-raw-conversion")

    stale = gate(sample(age=16, previous=valid))
    require(not stale["pv_archive"] and not stale["sp_archive"],
            "stale-plc-gates-pressure-and-setpoint")
    require(stale["freq_archive"], "plc-counter-staleness-does-not-suppress-independent-frequency")
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
    print("synthetic-cases: PASS")
    print("execution-scope: python semantic model; Pascal and native archive not executed")


if __name__ == "__main__":
    main()

