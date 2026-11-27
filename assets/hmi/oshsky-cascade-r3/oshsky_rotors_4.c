/* Called immediately after OshCurrents in the four-pump Map32 global macro.
 * Each channel uses its own valid frequency snapshot and its own phase.
 * LW54140..54143: 0 = still, 1..4 = U+E001..U+E004.
 */
static void OshRotors(IN *p)
{
    static unsigned short phase[4];
    static unsigned short ticks[4];
    int i;
    for (i = 0; i < 4; ++i) {
        unsigned short frequency = (unsigned short)OshTelemetry[i];
        unsigned short quality = (unsigned short)OshTelemetry[10+i];
        unsigned short divider;
        if (!LocalBit[2100+i] || quality != 2u || frequency == 0u || frequency > 5990u) {
            phase[i] = 0u;
            ticks[i] = 0u;
            LocalWord[54140+i] = 0u;
        } else {
            LocalWord[54140+i] = (unsigned short)(1u + phase[i]);
            divider = frequency < 200u ? 3u : (frequency < 350u ? 2u : 1u);
            if (++ticks[i] >= divider) {
                ticks[i] = 0u;
                phase[i] = (unsigned short)((phase[i]+1u) & 3u);
            }
        }
    }
}
