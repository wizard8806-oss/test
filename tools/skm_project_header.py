#!/usr/bin/env python3
"""Read the reviewed SKTool7.1 stream prefix sequentially.

After version/model QStrings, the stream contains a page count and one
sceneCommonData pair of signed 32-bit integers PER PAGE, then Scene1's
QRectF. Checking QString anchors or a trailing directory alone cannot
validate this prefix. This is not a whole native SKM parser or Compile.
"""
import math
import struct


def read_project_header(raw, validate_rect=True):
    position=0
    def string():
        nonlocal position
        if position+4>len(raw):raise ValueError('Truncated project QString')
        size=struct.unpack_from('>I',raw,position)[0];position+=4
        if size>4096 or size%2 or position+size>len(raw):raise ValueError('Invalid project QString')
        value=raw[position:position+size].decode('utf-16-be');position+=size
        return value
    version,model=string(),string()
    if version!='SKTOOL-V7.1.0.80' or not model.startswith('SK-'):raise ValueError('Unreviewed SKM version/model')
    count_at=position
    if position+4>len(raw):raise ValueError('Truncated scene count')
    count=struct.unpack_from('>I',raw,position)[0];position+=4
    if not 1<=count<=1000:raise ValueError('Invalid scene count')
    common_at=position;common_end=position+8*count
    if common_end+32>len(raw):raise ValueError('Truncated sceneCommonData/first QRectF')
    common=[struct.unpack_from('>ii',raw,common_at+8*i) for i in range(count)]
    rect=struct.unpack_from('>4d',raw,common_end)
    if validate_rect and (not all(math.isfinite(n) for n in rect) or rect[:2]!=(0.0,0.0)
            or not all(64<=n<=16384 and n==int(n) for n in rect[2:])):
        raise ValueError('Invalid first scene QRectF after sceneCommonData: '+repr(rect))
    return dict(version=version,model=model,pageCount=count,countOffset=count_at,
                commonOffset=common_at,commonEnd=common_end,common=common,
                firstSceneRect=rect,resolution=rect[2:])
