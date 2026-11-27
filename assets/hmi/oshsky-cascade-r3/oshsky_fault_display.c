/* Four read-only operator views of the existing native-fault publisher.
 * 0..80 address the M900G dictionary. 81 is an unlisted code, 82 means
 * no confirmed observation. The numeric value is always kept at 16 bits.
 */
static unsigned short OshFaultLabel(unsigned short code)
{
    return code <= 80u ? code : 81u;
}

static void OshFaultDisplay(IN *p)
{
    unsigned short i, seen, valid, pump, oldCode, newCode;
    for (i = 0; i < 4u; ++i) {
        seen = (LocalWord[51202] >> i) & 1u;
        valid = LocalBit[2164+i] != 0;
        LocalBit[2200+i] = seen;
        LocalBit[2204+i] = seen && !valid;
        LocalBit[2208+i] = !seen;
        LocalWord[54400+i] = seen ? LocalWord[51204+i] : 0u;
        LocalWord[54404+i] = seen ? OshFaultLabel(LocalWord[51204+i]) : 82u;
        /* One existing status line per pump. A stopped drive and an unknown
         * fault channel can occur together. Keep a retained fault distinct. */
        if (valid && LocalBit[2160+i])
            LocalWord[54418+i] = 2u;  /* confirmed active fault */
        else if (valid)
            LocalWord[54418+i] = LocalBit[2100+i] ? 1u : 0u;
        else if (seen && LocalWord[51204+i] != 0u)
            LocalWord[54418+i] = 4u;  /* retained nonzero, current code unknown */
        else
            LocalWord[54418+i] = LocalBit[2100+i] ? 3u : 0u;
    }
    for (i = 0; i < 10u; ++i) {
        pump = LocalWord[51216+9*i];
        oldCode = LocalWord[51217+9*i];
        newCode = LocalWord[51218+9*i];
        LocalWord[54408+i] = pump ? OshFaultLabel(newCode ? newCode : oldCode) : 82u;
    }
}
