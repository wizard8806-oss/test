"""Replay the saved r4 Pascal bodies on local in-memory inputs. No field or SQL adapter."""
import argparse
import hashlib
from pathlib import Path
import os
import re
import subprocess
import tempfile

from audit_native_ui_navigation import scripts
from verify_scada_variable_metadata_native import Layout


EXPECTED = {
    "StationDiagnostics": "e31c0334577f01b75516277a7d50707c649111ec82eab651837b12962131c44e",
    "OperatorConsole": "48f255da76c32693ba264225d82055478954c511ed91f7c46f61b05c738c84c9",
    "Script_49": "4dbb8cc63b3eede7d36e4d551ddd9daddd26fabb7ea16afdfd3a46d730437fcc",
}
VARIABLES_SHA = "c34c19d1f86344f5d429a355771c77ac9b27c2077acfd8c4b7ae74e98ef178d5"


def prepare(project):
    raw = (project / "Variables.svr").read_bytes()
    if hashlib.sha256(raw).hexdigest() != VARIABLES_SHA:
        raise ValueError("Variable table differs from the reviewed native Save As")
    records = Layout(raw).run().records
    entries = scripts((project / "Scripts/Scripts.ssc").read_bytes())
    bodies = {row["name"]: row["body"] for row in entries.values()}
    for name, expected in EXPECTED.items():
        if hashlib.sha256(bodies[name].encode()).hexdigest() != expected:
            raise ValueError(f"Changed Pascal body requires review: {name}")

    station = bodies["StationDiagnostics"].split("implementation", 1)[1]
    station = station.split("procedure StationProcessUpdate;", 1)[0]
    offset = station.index("procedure RouteFreshReset;")
    console = bodies["OperatorConsole"]
    display = console[console.index("var\n  R4Baseline, R4Lost"):console.rindex("procedure OperatorUiUpdate;")]
    trend = bodies["Script_49"]
    controls = sorted(set(re.findall(r"\b(\w+)\.(?:Text|Color|Enabled)\b", station + display)))
    variables = sorted(set(re.findall(r"\b(\w+)\.(?:OriginalAsInt|Value|Archiving|IsGoodQuality)\b", trend)))
    variables = sorted(set(variables) | set(re.findall(r"\b(TrendVfd\w+)\.(?:Value|Archiving)\b", display)))
    seed = []
    for record in records:
        name = record["name"]
        if record["external"]:
            item = record["address"].rsplit(".", 1)[-1].replace("'", "''")
            target = f"{name} := " if name in variables else ""
            seed.append(f"{target}mk('{item}');")
        elif name in variables:
            seed.append(f"{name} := TM_Variable.Create;")

    template = Path(__file__).parent / "fixtures/oshsky-r3-host-test.pas.in"
    text = template.read_text(encoding="utf8")
    text = text.replace("begin seed;", "begin {$ifdef windows}SetMultiByteConversionCodePage(65001);{$endif} seed;")
    extra = template.with_name("oshsky-r4-additional-checks.pas.in").read_text(encoding="utf8")
    text = text.replace("writeln('PASS isolated Pascal checks:", extra + "\nwriteln('PASS isolated Pascal checks:")
    host = template.with_name("oshsky-r4-host-api.pas.in").read_text(encoding="utf8")
    state = console[console.index("  R4FaultKnown:"):console.index("  R3Primed,")]
    text = text.replace(" R3Primed,R3Moving:", state + " R3Primed,R3Moving:")
    nav = console[console.rindex("procedure R4OpenTrend("):].removesuffix("end.")
    display = host + display + nav
    replacements = {
        "STATION_DECL": station[:offset], "STATION_LOGIC": station[offset:],
        "READ_WORD": console[console.index("function UiWord("):console.index("procedure UiReset(")],
        "DISPLAY": display, "TREND": trend.removesuffix(".") + ";",
        "CONTROLS": ",".join(controls), "TREND_VARIABLES": ",".join(variables),
        "SEED": "\n".join(seed),
    }
    for key, value in replacements.items():
        marker = f"@@{key}@@"
        if text.count(marker) != 1:
            raise ValueError(f"Missing or duplicate fixture marker: {key}")
        text = text.replace(marker, value)
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("--compiler", default="fpc")
    parser.add_argument("--unit-path", type=Path, action="append", default=[])
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="oshsky-TEST_ONLY-") as scratch:
        program = Path(scratch) / "review.pas"
        program.write_text(prepare(args.project), encoding="utf8")
        command = [args.compiler, "-Mdelphi", "-Cr", "-Co", "-gl"]
        command.extend(f"-Fu{path.resolve()}" for path in args.unit_path)
        subprocess.run([*command, program.name], cwd=scratch, check=True, timeout=90)
        binary = program.with_suffix(".exe" if os.name == "nt" else "")
        subprocess.run([str(binary)], cwd=scratch, check=True, timeout=30)


if __name__ == "__main__":
    main()
