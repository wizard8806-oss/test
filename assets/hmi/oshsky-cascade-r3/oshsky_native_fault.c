/* Read-only native VFD batch from the four existing Port 3 replies.
 * LW51200..51305 is panel-retained event history. A new entry is committed
 * only for a change confirmed by a fresh complete drive reply.
 */
#ifndef OshFault
#error Configure_OshFault_Batch_UInt16_R3610_Bytes36
#endif
/* Bit n-1 names code n in the native M900G catalog. */
static int OshKnownFault(unsigned short raw)
{
    static const unsigned short known[5]={0xffffu, 0x327fu, 0x1380u, 0x81d8u, 0x1u};
    return raw && raw<=80u && (known[(raw-1u)/16u] & (1u<<((raw-1u)%16u)));
}

static unsigned short OshActiveAlarmCount(unsigned int mask)
{
    unsigned short n=0;
    while (mask) { mask &= mask-1u; ++n; }
    return n;
}

static void OshNativeFault(IN *p)
{
    static unsigned short primed, moving, previous, lastSecond;
    unsigned short now=InfoBCD(LocalWord[60000]);
    unsigned short hb=(unsigned short)OshFault[1];
    unsigned short raw, seen, last, i, j, k, valid, good;
    unsigned short changed=0, active=0;
    good=LocalBit[60107] && MapVersion==32u && OshContract[0]==27110u
        && OshFault[0]==27428u && now<60u;
    if (!good) { primed=0; moving=0; }
    else if (!primed) { primed=1; moving=0; previous=hb; lastSecond=now; }
    else if (hb!=previous) { previous=hb; lastSecond=now; moving=1; }
    else if ((now+60u-lastSecond)%60u>=3u) moving=0;
    if (LocalWord[51200]!=27428u || LocalWord[51201]!=38107u
            || LocalWord[51203]>10u || LocalWord[51202]>15u) {
        for (j=0;j<106u;++j) LocalWord[51200+j]=0;
        LocalWord[51200]=27428u; LocalWord[51201]=38107u;
    }
    for (i=0;i<4u;++i) {
        raw=(unsigned short)OshFault[2+i];
        valid=good && moving && OshFault[6+i]==1u && OshFault[14+i]!=0u;
        seen=(LocalWord[51202]>>i)&1u;
        last=LocalWord[51204+i];
        LocalBit[2160+i]=valid && raw!=0u;
        LocalBit[2164+i]=valid;
        LocalBit[2168+i]=!valid;
        LocalBit[2172+i]=valid && raw && !OshKnownFault(raw);
        LocalBit[2176+i]=good && moving && OshFault[14+i]!=0u;
        LocalWord[54300+i]=raw;
        LocalWord[54304+i]=(unsigned short)(hb-(unsigned short)OshFault[10+i]);
        LocalWord[54308+i]=!good?1u:!moving?2u:!OshFault[14+i]?3u:!valid?4u:0u;
        if (valid && raw!=last && (seen || raw!=0u)) {
            /* Copy complete older records. Values never refer to a live tag. */
            for (j=9u;j>0u;--j)
                for (k=0u;k<9u;++k)
                    LocalWord[51216+9*j+k]=LocalWord[51216+9*(j-1u)+k];
            LocalWord[51216]=i+1u; LocalWord[51217]=last; LocalWord[51218]=raw;
            for (k=0;k<6u;++k) LocalWord[51219+k]=InfoBCD(LocalWord[60005-k]);
            if (LocalWord[51203]<10u) ++LocalWord[51203];
            changed=1;
        }
        if (valid) {
            LocalWord[51202]|=(1u<<i);
            LocalWord[51204+i]=raw;
        }
        last=LocalWord[51204+i];
        if (last) active|=(1u<<i);
        for(j=0;j<6u;++j) LocalWord[54320+6*i+j]=0;
        if (last) {
            unsigned short index=last<=80u?last-1u:80u;
            LocalWord[54320+6*i+index/16u]=(1u<<(index%16u));
        }
    }
    LocalWord[54312]=active;
    LocalWord[54313]=good && moving;
    LocalWord[54314]=hb;
    /* The event is stored above even if its number is outside the dictionary. */
    if (changed) LocalWord[54315]=(unsigned short)(LocalWord[54315]+1u);
}
