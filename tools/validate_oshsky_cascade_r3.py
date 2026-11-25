#!/usr/bin/env python3
"""Exercise the actual four-pump cascade bytecode, not a rewritten algorithm."""
import argparse
from itertools import permutations
import json
from pathlib import Path
import struct
import tempfile

from build_manual_no_sensor_pdw import u16
from build_setpoint_feedback_pdw_01 import build
from build_vfd_fault_export_r14 import inventory
from prepare_setpoint_feedback_01 import ANCHOR, networks
from validate_cascade_r10 import CascadeMachine as EdgeMachine
from validate_telemetry_continuity import check as telemetry_check


class CascadeMachine(EdgeMachine):
    def execute(self, code):
        # Source04 uses the vendor's immediate subtraction for one-second +1.
        if len(code) in (12, 20) and code[-10:-6] == bytes.fromhex('7fe8f664'):
            contact = struct.unpack_from('>H', code)[0]
            source, value, target = struct.unpack('>3H', code[-6:])
            assert contact >> 12 == 4
            enabled = self.bits.get(self.contact(contact & 0xfff), False)
            if len(code) == 20:
                op, descriptor, register, constant = struct.unpack('>4H', code[2:10])
                assert (op, descriptor) == (0xf67f, 0x21)
                enabled = enabled and self.regs.get(self.reg(register), 0) == constant
            if enabled:
                self.regs[self.reg(target)] = (self.regs.get(self.reg(source), 0) - value) & 65535
            return
        return super().execute(code)


def codes(raw):
    f, rows = inventory(raw)
    return {label.split(' | ')[0]: f['image'][pc:rows[i + 1][0] if i + 1 < len(rows)
             else u16(f['image'], 270) - 2] for i, (pc, label) in enumerate(rows)}


def exercise(raw):
    c = codes(raw)
    cases = []

    def scan(m, first=1, last=117, clock=False):
        m.bits['M', 1780] = clock
        for key, body in c.items():
            if key.startswith('65.C') and first <= int(key[4:7]) <= last:
                m.execute(body)

    def fresh(stage=0, target=4):
        m = CascadeMachine()
        m.regs.update({('R', 2120): 30, ('R', 2121): 480, ('R', 2122): 220,
                      ('R', 2123): 3, ('R', 2124): 4, ('R', 2125): 10,
                      ('R', 2884): 5, ('R', 2885): 2, ('R', 2886): 27402,
                      ('R', 2893): 1, ('R', 2894): stage, ('R', 2895): target,
                      ('R', 2900): target, ('D', 906): stage, ('D', 904): target,
                      ('D', 909): target, ('D', 903): stage, ('D', 870): 1,
                      ('D', 871): 490, ('R', 111): 50})
        for n in (740, 1140, 969, 854, 1282):
            m.bits['M', n] = True
        return m

    # Same stage can connect a different physical pump after rotation.
    for stage, preset in ((0, 3), (1, 5), (2, 2)):
        for target in range(1, 5):
            m = fresh(stage, target)
            scan(m, 69, 117)
            assert m.regs.get(('R', 3121)) == 1, 'No active PLC start countdown'
            assert m.regs['R', 3122] == target
            assert m.regs['R', 3123] == preset
            for seconds in range(preset + 1):
                scan(m, 69, 117, clock=True)
                fired = m.bits['M', 1260]
                scan(m, 69, 117, clock=False)
                if seconds < preset:
                    assert not m.bits['M', 1260]
                    assert m.regs['R', 3123] == preset - seconds
            assert fired
            assert m.regs['R', 3121] == 0
            assert m.bits['M', 1210 + target - 1]
            assert m.regs['D', 903] == stage + 1
            cases.append(f'stage{stage + 2}/physical{target}/independent delay/commit')

    # Stop countdown is the original R2124/D911 and targets the actual stack.
    for target in range(1, 5):
        m = fresh(2, target)
        m.regs.update({('D', 871): 210, ('R', 111): 0})
        m.bits['M', 1210 + target - 1] = True
        scan(m, 69, 117)
        assert [m.regs['R', n] for n in (3121, 3122, 3123)] == [2, target, 4]
        for tick in range(5):
            scan(m, 69, 117, clock=True)
            fired = m.bits['M', 1261]
            scan(m, 69, 117)
            if tick < 4:
                assert not m.bits['M', 1261]
                assert m.regs['R', 3123] == 4 - tick
        assert fired and not m.bits['M', 1210 + target - 1]
        assert m.regs['R', 3121] == 0
        cases.append(f'original stop delay/physical{target}/commit')

    for stage in range(3):
        for cancel in ('demand', 'monitor', 'mode', 'settings', 'safety', 'stack'):
            m = fresh(stage)
            scan(m, 69, 117)
            scan(m, 69, 117, clock=True); scan(m, 69, 117)
            scan(m, 69, 117, clock=True); scan(m, 69, 117)
            if cancel == 'demand':
                m.regs['R', 111] = 0
            else:
                m.bits['M', {'monitor': 1140, 'mode': 740, 'settings': 1282,
                             'safety': 969, 'stack': 1270}[cancel]] = cancel == 'stack'
            scan(m, 69, 117)
            assert [m.regs.get(('R', n), 0) for n in (3121, 3122, 3123)] == [0, 0, 0]
            assert [m.regs.get(k, 0) for k in (('D', 910), ('R', 2896), ('R', 2897))] == [0, 0, 0]
            assert not m.bits['M', 1260]
            cases.append(f'cancel {cancel}/stage{stage + 2}')

    for stage in range(3):
        m = fresh(stage)
        scan(m, 69, 117)
        for _ in range(2):
            scan(m, 69, 117, clock=True); scan(m, 69, 117)
        m.regs['D', 904] = 2
        scan(m, 69, 117)
        assert m.regs['R', 3122] == 2 and m.regs['R', 3123] == (3, 5, 2)[stage]
        assert not m.bits['M', 1260], 'Replacement candidate inherited elapsed time'
        cases.append(f'candidate change resets stage{stage + 2}')
    m = fresh(1)
    m.regs['R', 2896] = 4
    m.regs['D', 906] = 2
    scan(m, 69, 117)
    assert m.regs['R', 2896] == 0 and m.regs['R', 3123] == 2
    cases.append('stage change resets previous and new counters')

    # New values participate in the existing complete STOP edit/apply gate.
    for a, b in ((1, 3600), (30, 29), (3600, 1), (0, 10), (10, 3601), (65535, 10)):
        for stopped in (False, True):
            m = fresh()
            m.bits.update({('M', 1468): True, ('M', 1463): True, ('M', 1465): stopped,
                           ('M', 1472): True, ('M', 1473): True,
                           ('M', 1791): True, ('M', 1792): True, ('M', 1793): True})
            for n in range(1480, 1486):
                m.bits['M', n] = True
            m.regs.update({('R', 2887): a, ('R', 2888): b})
            for key, body in c.items():
                if key.startswith('95.S') and '034' <= key[4:7] < '051':
                    m.execute(body)
            accepted = stopped and 1 <= a <= 3600 and 1 <= b <= 3600
            assert m.bits['M', 1469] == accepted
            assert (m.regs['R', 2884], m.regs['R', 2885]) == ((a, b) if accepted else (5, 2))
            cases.append(f'atomic STOP apply/{a},{b}/stopped{stopped}')
    for initial in (1, 10, 600, 0, 65535):
        m = fresh(); m.regs.update({('R', 2886): 0, ('R', 2123): initial})
        m.bits['M', 1924] = True
        scan(m, 1, 1)
        assert m.regs['R', 2884] == m.regs['R', 2885] == (initial if 1 <= initial <= 600 else 10)
        m.regs['R', 2884] = 123; scan(m, 1, 1)
        assert m.regs['R', 2884] == 123
        cases.append(f'first use inherits original {initial}/retained edit')
    for value in (0, 1, 65535):
        m = fresh(); m.regs['R', 2840] = value; scan(m, 117, 117)
        assert m.regs['R', 3120] == 27402 and m.regs['R', 3125] == value
        cases.append(f'dedicated new heartbeat {value}')
    # Run the original eligibility/order selector, not just injected targets.
    for order in permutations(range(1, 5)):
        for leader in range(1, 5):
            m = fresh(); m.regs['D', 270] = leader; m.regs['R', 2110] = 350
            for i, pump in enumerate(order):
                m.regs['R', 480 + i] = pump
                m.regs['D', 420 + i] = 350
                for n in (750 + i, 610 + i, 870 + i, 850 + i):
                    m.bits['M', n] = True
                m.bits['X', i + 1] = True
            scan(m, 36, 64)
            target = next(p for p in order if p != leader)
            assert m.regs['D', 904] == target
            scan(m, 69, 117)
            assert m.regs['R', 3122] == target
            # Loss of READY selects another candidate and resets its wait.
            scan(m, 69, 117, clock=True); scan(m, 69, 117)
            scan(m, 69, 117, clock=True); scan(m, 69, 117)
            m.bits['X', target] = False
            scan(m, 36, 64); scan(m, 69, 117)
            replacement = next(p for p in order if p not in (leader, target))
            assert (m.regs['R', 3122], m.regs['R', 3123]) == (replacement, 3)
            cases.append(f'original selector order{order}/leader{leader}/READY loss')
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, help='Exact reviewed r2 source used by the builder')
    parser.add_argument('--candidate', type=Path)
    parser.add_argument('--vendor', type=Path)
    args = parser.parse_args()
    from build_oshsky_cascade_r3 import prepare
    from build_oshsky_telemetry_r2 import prepare as telemetry
    with tempfile.TemporaryDirectory(prefix='oshsky-r3-') as folder:
        root = Path(folder)
        seed, _, _ = build((Path(__file__).resolve().parents[1] / 'source/plc/station_MC_CM55_900G_04.pdw').read_bytes(), networks(), ANCHOR)
        source05 = root / '05.pdw'; source05.write_bytes(seed)
        r2 = root / 'r2.pdw'; r2.write_bytes(telemetry(source05)[0])
        try:
            exercise(r2.read_bytes())
        except (AssertionError, KeyError):
            pass
        else:
            raise AssertionError('Baseline did not reproduce missing independent countdown')
        data, report = prepare(r2)
        cases = exercise(data)
        if args.source:
            data, report = prepare(args.source)
            cases = exercise(data)
        candidate = args.candidate or root / 'r3.pdw'
        if args.candidate:
            # Saved native image must match exactly; serialization differences need explicit review.
            actual, rows = inventory(candidate.read_bytes()); expected, expected_rows = inventory(data)
            assert actual['image'] == expected['image'] and rows == expected_rows
            assert actual['payload'] == expected['payload'], 'Native payload changed: explicit review required'
            keep = lambda f: [record for kind, _, record in f['records'] if kind not in (0x1001, 0x1002)]
            assert keep(actual) == keep(expected), 'Native non-PC metadata changed: explicit review required'
            cases = exercise(candidate.read_bytes())
        else:
            candidate.write_bytes(data)
        # Exact source locks, malformed frames and input preservation are fail-closed.
        for wrong in (source05, candidate):
            try:
                prepare(wrong)
            except ValueError:
                pass
            else:
                raise AssertionError('Builder accepted an unreviewed source')
        assert telemetry_check(candidate, pumps=4) == 222
        if args.vendor:
            from check_fatek_network_graph import GraphChecker
            graph = GraphChecker(args.vendor)
            for row in report['newNetworks'] + report['changedNetworks']:
                graph.require(bytes.fromhex(row['codeHex']))
        print(json.dumps(dict(cascadeCases=len(cases), telemetryCases=222,
            vendorNetworks=len(report['newNetworks']) + len(report['changedNetworks']) if args.vendor else None,
            candidateBytes=report['candidateBytes'], candidateSHA256=report['candidateSHA256'],
            nativeF8Observed=False, hardwareObserved=False)))


if __name__ == '__main__':
    main()
