/* Local observation only. LW54180 is the first audible rearm after a mute.
 * A power cycle restarts this local capture. The PLC independently retains
 * the first rising bit before its previous mask is overwritten.
 */
static void OshSoundEvidence(IN *p, unsigned int previous, unsigned int current,
    unsigned int rising, unsigned short old_gen, unsigned short gen,
    int changed_gen, int request, int was_muted, int muted)
{
    static unsigned short calls = 0u;
    static unsigned short armed = 0u;
    static unsigned short captured = 0u;
    unsigned short reason = 0u;
    int i;
    if (calls == 0u && !armed && !captured) {
        LocalWord[54180] = 0u;
    }
    LocalWord[54160] = ++calls;
    LocalWord[54161] = (unsigned short)previous;
    LocalWord[54162] = (unsigned short)(previous >> 16);
    LocalWord[54163] = (unsigned short)current;
    LocalWord[54164] = (unsigned short)(current >> 16);
    LocalWord[54165] = (unsigned short)rising;
    LocalWord[54166] = (unsigned short)(rising >> 16);
    LocalWord[54167] = old_gen;
    LocalWord[54168] = gen;
    LocalWord[54169] = (unsigned short)request;
    LocalWord[54170] = (unsigned short)was_muted;
    LocalWord[54171] = (unsigned short)muted;
    LocalWord[54172] = (unsigned short)LocalBit[801];
    LocalWord[54173] = (unsigned short)LocalBit[802];
    LocalWord[54174] = (unsigned short)LocalBit[60117];
    LocalWord[54175] = (unsigned short)BootAck;
    LocalWord[54176] = (unsigned short)LocalBit[60107];
    LocalWord[54177] = (unsigned short)AlarmWords[0];
    LocalWord[54178] = (unsigned short)AlarmWords[1];
    LocalWord[54179] = (unsigned short)MapVersion;
    if (request && muted) armed = 1u;
    if (armed && !captured && LocalBit[802]) {
        if (rising) reason |= 1u;
        if (changed_gen) reason |= 2u;
        if (!reason) reason = 4u;
        for (i=0;i<20;++i) LocalWord[54181+i]=LocalWord[54160+i];
        for (i=0;i<6;++i) LocalWord[54201+i]=LocalWord[60005-i];
        LocalWord[54207]=(unsigned short)OshTelemetry[8];
        LocalWord[54208]=(unsigned short)CascadeBlock[5];
        LocalWord[54180]=reason;
        captured=1u;
    }
}
