#!/usr/bin/env python3
"""Compile and exercise the read-only HMI countdown component; no panel I/O."""
import ctypes as ct
from pathlib import Path
import shutil
import subprocess
import tempfile


class State(ct.Structure):
    _fields_ = [('initialized', ct.c_ushort), ('moving', ct.c_ushort), ('heartbeat', ct.c_ushort),
                ('changedAt', ct.c_ulong), ('lastNow', ct.c_ulong)]


class Output(ct.Structure):
    _fields_ = [('action', ct.c_ushort), ('pump', ct.c_ushort), ('seconds', ct.c_ushort)]


def main():
    source = Path(__file__).resolve().parents[1] / 'assets/hmi/oshsky-cascade-r3/cascade_countdown.c'
    compiler = shutil.which('cc') or shutil.which('gcc') or shutil.which('clang')
    if compiler is None:
        raise SystemExit('A host C compiler is required; native SKTool verification is separate')
    with tempfile.TemporaryDirectory(prefix='oshsky-countdown-c-') as folder:
        root = Path(folder)
        wrapper = root / 'wrapper.c'
        wrapper.write_text(source.read_text() + '\nvoid step(OshskyCountdownState *s, const unsigned short *w,'
            'unsigned short good, unsigned short automatic, unsigned long now, OshskyCountdownOutput *o)'
            '{OshskyCountdown(s,w,good,automatic,now,o);}\n')
        library = root / 'test.so'
        subprocess.run([compiler, '-std=c99', '-Wall', '-Wextra', '-Werror', '-fPIC', '-shared',
                        str(wrapper), '-o', str(library)], check=True, capture_output=True)
        call = ct.CDLL(str(library)).step
        call.argtypes = [ct.POINTER(State), ct.POINTER(ct.c_ushort), ct.c_ushort,
                         ct.c_ushort, ct.c_ulong, ct.POINTER(Output)]
        cases = 0

        def step(s, words, now, expected, good=1, automatic=1):
            nonlocal cases
            out = Output(9, 9, 9)
            call(ct.byref(s), (ct.c_ushort * 6)(*words), good, automatic, now, ct.byref(out))
            actual = (out.action, out.pump, out.seconds)
            assert actual == expected, (words, now, expected, actual)
            cases += 1

        zero = (0, 0, 0)
        for action, maximum in ((1, 3600), (2, 1800)):
            for pump in range(1, 5):
                s = State()
                step(s, [27402, action, pump, maximum, maximum, 50], 0, zero)
                step(s, [27402, action, pump, maximum, maximum, 50], 1, zero)
                step(s, [27402, action, pump, maximum, maximum, 51], 2, (action, pump, maximum))
                step(s, [27402, action, pump, maximum - 1, maximum, 51], 3, (action, pump, maximum - 1))
                # No local decrement: PLC value stays constant until invalidated.
                step(s, [27402, action, pump, maximum - 1, maximum, 51], 4, (action, pump, maximum - 1))
                step(s, [27402, action, pump, maximum - 1, maximum, 51], 5, zero)
        for index, value in ((0, 27401), (1, 0), (1, 3), (2, 0), (2, 5), (2, 65535),
                             (3, 0), (3, 11), (4, 0), (4, 3601)):
            s = State(); words = [27402, 1, 3, 10, 10, 1]
            step(s, words, 10, zero)
            words[5] = 2; step(s, words, 11, (1, 3, 10))
            words[index] = value; step(s, words, 12, zero)
        s = State()
        step(s, [27402, 1, 4, 5, 10, 65535], 86398, zero)
        step(s, [27402, 1, 4, 5, 10, 0], 86399, (1, 4, 5))
        step(s, [27402, 1, 4, 5, 10, 0], 0, zero)
        step(s, [27402, 1, 4, 5, 10, 1], 1, (1, 4, 5))
        step(s, [27402, 1, 4, 5, 10, 2], 2, zero, good=0)
        step(s, [27402, 1, 4, 5, 10, 3], 3, zero)
        step(s, [27402, 1, 4, 5, 10, 4], 4, (1, 4, 5))
        step(s, [27402, 1, 4, 5, 10, 5], 5, zero, automatic=0)
        step(s, [27402, 2, 1, 1801, 1801, 6], 6, zero)
        step(s, [27402, 2, 1, 8, 30, 7], 7, (2, 1, 8))
        print(f'HMI countdown host C: {cases} cases PASS; native SKTool/Simulator remain')


if __name__ == '__main__':
    main()
