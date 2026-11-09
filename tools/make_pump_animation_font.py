#!/usr/bin/env python3
"""Build our four-frame vector impeller font (build-time fontTools only)."""
import math
from pathlib import Path
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def polygon(pen, points):
    pen.moveTo(points[0])
    for point in points[1:]:
        pen.lineTo(point)
    pen.closePath()


def rotor(angle):
    pen = TTGlyphPen(None)
    for radius, reverse in ((460, False), (410, True), (75, False)):
        points = [(round(500 + radius * math.cos(2 * math.pi * i / 64)),
                   round(500 + radius * math.sin(2 * math.pi * i / 64))) for i in range(64)]
        polygon(pen, points[::-1] if reverse else points)
    for blade in range(4):
        points = []
        for radius, start, stop in ((370, 10, 58), (120, 40, 8)):
            for step in range(9):
                t = math.radians(angle + 90 * blade + start + (stop - start) * step / 8)
                points.append((round(500 + radius * math.cos(t)), round(500 + radius * math.sin(t))))
        polygon(pen, points)
    return pen.glyph()


def main():
    root = Path(__file__).resolve().parents[1]
    out = root / 'assets/hmi/pump-animation/PumpStationRotor.ttf'
    fb = FontBuilder(1000, isTTF=True)
    names = ['.notdef', 'space'] + ['rotor%d' % i for i in range(4)]
    fb.setupGlyphOrder(names)
    fb.setupCharacterMap({32: 'space', **{0xE001+i: 'rotor%d' % i for i in range(4)}})
    empty = TTGlyphPen(None).glyph()
    fb.setupGlyf({'.notdef': empty, 'space': empty, **{'rotor%d' % i: rotor(22.5*i) for i in range(4)}})
    fb.setupHorizontalMetrics({n: (1000, 0) for n in names})
    fb.setupHorizontalHeader(ascent=1000, descent=0)
    fb.setupNameTable({'familyName': 'Pump Station Rotor', 'styleName': 'Regular',
                       'uniqueFontIdentifier': 'PumpStationRotor-1.0',
                       'fullName': 'Pump Station Rotor', 'psName': 'PumpStationRotor',
                       'version': 'Version 1.0', 'copyright': 'Original vector artwork; CC0-1.0'})
    fb.setupOS2(sTypoAscender=1000, sTypoDescender=0, usWinAscent=1000, usWinDescent=0, fsType=0)
    fb.setupPost()
    fb.setupMaxp()
    fb.font['head'].created = fb.font['head'].modified = 3876940800
    fb.font.recalcTimestamp = False
    fb.save(out)
    print(out)


if __name__ == '__main__':
    main()
