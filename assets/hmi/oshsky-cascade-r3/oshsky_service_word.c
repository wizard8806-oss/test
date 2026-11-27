/* Send the existing R2553 service once through the native transfer. The
 * transfer resets LB54210 after consuming LW54210. An outdated generation
 * and a lost session cancel a pending mute before another session can use it.
 */
static void OshServiceTransport(IN *p, unsigned short generation, int muted)
{
    static int boot_submitted = 0;
    int connected = LocalBit[60107] && MapVersion == 32u;
    unsigned short request = BootAck;
    if (!connected) {
        LocalBit[54210] = 0;
        LocalWord[54210] = 0;
        boot_submitted = 0;
        return;
    }
    if (!(AlarmWords[1] & 256u)) boot_submitted = 0;
    if (LocalBit[54210] && LocalWord[54210] > 256u &&
            (!muted || LocalWord[54210] != 256u + generation)) {
        LocalBit[54210] = 0;
        LocalWord[54210] = 0;
    }
    if (request > 256u && muted && generation && request == 256u + generation) {
        LocalWord[54210] = request;
        LocalBit[54210] = 1;
    } else if (request == 1u && !boot_submitted && !LocalBit[54210]) {
        LocalWord[54210] = 1u;
        LocalBit[54210] = 1;
        boot_submitted = 1;
    }
}
