"""Read the four PUA bitmaps in a compiled SKTool QPF2 rotor font."""
import hashlib
import struct


def rotor_bitmap_hashes(file):
    data=file.read_bytes()
    assert data[:4]==b'QPF2'
    at=12+int.from_bytes(data[10:12],'big')
    blocks={}
    while at<len(data):
        kind,padding,size=struct.unpack_from('>HHI',data,at)
        assert not padding and at+8+size<=len(data) and kind not in blocks
        blocks[kind]=data[at+8:at+8+size]
        at+=8+size
    cmap,index,bitmaps=(blocks[k] for k in range(3))
    u16=lambda buf,pos:struct.unpack_from('>H',buf,pos)[0]
    fmt=next(struct.unpack_from('>I',cmap,8+8*i)[0] for i in range(u16(cmap,2))
             if struct.unpack_from('>HH',cmap,4+8*i)==(3,1))
    assert u16(cmap,fmt)==4
    cmap=cmap[fmt:]
    count=u16(cmap,6)//2
    result={}
    for cp in range(0xe001,0xe005):
        seg=next(i for i in range(count) if u16(cmap,14+2*i)>=cp)
        start=u16(cmap,16+2*count+2*seg)
        assert cp>=start
        delta=u16(cmap,16+4*count+2*seg)
        range_at=16+6*count+2*seg
        offset=u16(cmap,range_at)
        glyph=(cp+delta)&65535 if not offset else (u16(cmap,range_at+offset+2*(cp-start))+delta)&65535
        entry=struct.unpack_from('>I',index,4*glyph)[0]
        assert entry!=0xffffffff
        width,height,pitch=bitmaps[entry:entry+3]
        image=bitmaps[entry+6:entry+6+height*pitch]
        assert 0<width<=pitch and height>0 and len(image)==height*pitch
        pixels=b''.join(image[y*pitch:y*pitch+width] for y in range(height))
        assert max(pixels)>0
        result[f'U+{cp:04X}']=hashlib.sha256(pixels).hexdigest()
    assert len(set(result.values()))==4
    return result
