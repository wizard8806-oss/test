#!/usr/bin/env python3
"""Exercise native telemetry invalidation rungs, without serial/hardware I/O.

A failed unrelated poll row must not erase a still-fresh seven-WORD cache.
Own-row failures, watchdog expiry and boot must still invalidate it. Display
quality follows that own snapshot, not a generic link flag from other jobs.
Input is a private PDW, never a Git fixture; serial/hardware stays outside scope.
"""
import argparse
from pathlib import Path
import struct

from build_vfd_fault_export_r14 import inventory
from validate_drive_reset_r15 import Machine
from validate_three_pump_pdw_candidate import Machine as LogicMachine


def poll_rows(records, pumps=3):
    tables = [body for kind, body, _ in records
              if kind == 0x1015 and b'R5000\0' in body]
    assert len(tables) == 1, 'Expected one R5000 metadata record'
    body, copies = tables[0], []
    for offset in range(len(body) - 4):
        if body[offset:offset + 2] != b'\x50\xa5':
            continue
        count, columns = body[offset + 2:offset + 4]
        if columns != 7 or not count or offset + 4 + 14 * count > len(body):
            continue
        values = struct.unpack_from('<' + 'H' * count * columns, body, offset + 4)
        copies.append([values[i * 7:(i + 1) * 7] for i in range(count)])
    assert len(copies) == 2 and copies[0] == copies[1], 'R5000 copies differ'
    # Babanov filters the table at boot; Oshsky keeps the original four slaves.
    rows = [row for row in copies[0] if row[0] <= pumps]
    assert len(rows) == (14 if pumps == 3 else 18), 'Unexpected runtime table'
    return rows


def check(source, pumps=3):
    assert pumps in (3, 4), 'Only the reviewed Babanov/Oshsky layouts are supported'
    raw = Path(source).read_bytes()
    framed, rungs = inventory(raw)
    rows = poll_rows(framed['records'], pumps)
    cases, failures = [], []
    spans = {label: framed['image'][pc:rungs[i + 1][0]]
             for i, (pc, label) in enumerate(rungs[:-1])}
    prep = spans.get('65.T000 | TELEMETRY_RESULT_ROW')

    def expect(name, actual, wanted):
        cases.append(name)
        if actual != wanted:
            failures.append(f'{name}: cache={actual}, expected {wanted}')

    for pump in range(pumps):
        prefix = f'65.T{5 + 9 * pump:03d}'
        matches = [(i, pc) for i, (pc, label) in enumerate(rungs)
                   if label.startswith(prefix + ' | ')]
        assert len(matches) == 1, f'Missing/ambiguous invalidate rung {prefix}'
        index, pc = matches[0]
        code = framed['image'][pc:rungs[index + 1][0]]
        slave, local = pump + 1, 2800 + 8 * pump
        own = [i for i, row in enumerate(rows)
               if row == (slave, 1, 7, 12, local, 4, 4097)]
        own_rows = (0, 3, 13) if pumps == 3 else (0, 3, 16, 17)
        assert own == [own_rows[pump]], 'Seven-WORD telemetry row changed'
        own = own[0]
        unrelated = [i for i, row in enumerate(rows)
                     if row[0] == slave and row[1] == 1 and i != own]
        assert unrelated, 'An unrelated same-slave FC03 row is required'

        def run(row=own, error=False, result=1, station=slave, function=3,
                boot=False, timeout=False, fresh=False):
            machine = Machine()
            fresh_bit = (1830 if pumps == 3 else 1744) + pump
            machine.bits.update({('M', 1748 + pump): True, ('M', 601): error,
                                 ('M', 1924): boot, ('T', 92 + pump): timeout,
                                 ('M', fresh_bit): fresh})
            machine.regs.update({('D', 300): (result << 8) | row,
                                 ('D', 301): (station << 8) | function})
            if prep:
                # The new separate row decoder uses FUN18 AND; reuse the reset
                # interpreter's implementation rather than inventing opcodes.
                machine.execute(prep)
            # Reuse the existing branch-logic interpreter (e4xx OR merge), with
            # the reset Machine's native M/T/X/Y and R/D decoders. No FUN150 runs.
            LogicMachine.execute(machine, code)
            return machine.bits[('M', 1748 + pump)]

        expect(f'P{slave} no error retains cache', run(), True)
        for result in (1, 2, 16, 255):
            expect(f'P{slave} own row{own} failure status{result}',
                   run(error=True, result=result), False)
            for row in unrelated:
                expect(f'P{slave} unrelated row{row} FC03 failure status{result}',
                       run(row=row, error=True, result=result), True)
        expect(f'P{slave} watchdog expiry', run(timeout=True), False)
        expect(f'P{slave} boot', run(boot=True), False)
        expect(f'P{slave} qualified new sample wins over latched own error',
               run(error=True, fresh=True), True)
        expect(f'P{slave} unrelated function FC06',
               run(error=True, function=6), True)
        for station in set(range(1, pumps + 1)) - {slave}:
            expect(f'P{slave} another slave{station} failure',
                   run(error=True, station=station), True)

        # Generic M610 also feeds control protections. Leave that meaning alone;
        # only the displayed quality must use the independently aged own cache.
        number = 7 + 9 * pump
        publication = [value for label, value in spans.items()
                       if label.split(' | ')[0] in
                       {f'65.T{n:03d}' for n in range(number, number + 3)}]
        assert len(publication) == 3, 'Expected UNKNOWN/STOP/RUN quality rungs'
        for frequency, quality in ((0, 1), (250, 2), (5990, 2),
                                   (5991, 0), (65535, 0)):
            for cache in (False, True):
                for link in (False, True):
                    machine = Machine()
                    machine.bits.update({('M', 1748 + pump): cache,
                                         ('M', 610 + pump): link})
                    machine.regs.update({('R', 2500 + pump): frequency,
                                         ('R', 2510 + pump): 12345})
                    for body in publication:
                        LogicMachine.execute(machine, body)
                    expect(f'P{slave} publication F{frequency} own-cache{cache} '
                           f'generic-link{link}',
                           machine.regs[('R', 2510 + pump)], quality if cache else 0)

        sample = next(value for label, value in spans.items()
                      if label.startswith(f'65.T{6 + 9 * pump:03d} | '))
        for current in (0, 47, 1234, 65535):
            for accepted in (False, True):
                machine = Machine()
                machine.bits[('M', 1744 + pump)] = accepted
                machine.regs.update({('R', local + 3): 357,
                                     ('R', local + 6): current,
                                     ('R', 2500 + pump): 111,
                                     ('R', 2504 + pump): 222})
                LogicMachine.execute(machine, sample)
                expect(f'P{slave} coherent F/I snapshot I{current} accepted{accepted}',
                       (machine.regs[('R', 2500 + pump)], machine.regs[('R', 2504 + pump)]),
                       (357, current) if accepted else (111, 222))

    machine = Machine()
    if prep:
        machine.execute(prep)
    marker = 27133 if pumps == 3 else 27401
    feature = spans.get('65.I001 | CURRENT_FEATURE')
    if feature:
        machine.execute(feature)
    expect('new current-export contract marker', machine.regs.get(('R', 2509), 0), marker)
    if pumps == 4:
        heartbeat = spans.get('65.I002 | CURRENT_HEARTBEAT')
        for value in (0, 1, 65535, 0, 17):
            machine.regs[('R', 2840)] = value
            if heartbeat:
                machine.execute(heartbeat)
            expect(f'current-feature heartbeat follows PLC counter {value}',
                   machine.regs.get(('R', 2508), -1), value)

    assert Path(source).read_bytes() == raw, 'Input was modified'
    if failures:
        raise AssertionError(f'{len(failures)}/{len(cases)} cases failed:\n'
                             + '\n'.join(failures))
    return len(cases)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Private native/candidate PDW')
    parser.add_argument('--pumps', type=int, choices=(3, 4), default=3,
                        help='Accepted fixed-three or original four-pump table')
    args = parser.parse_args()
    print(f'PASS: {check(args.source, args.pumps)} actual-bytecode cache-continuity cases; '
          'field behavior remains separate')


if __name__ == '__main__':
    main()
