/* Native SKTool inputs, both READ ONLY, inserted before BootAckW:
 * MainModeData: Batch16 R2300, Bytes2.
 * MainRotationData: Batch16 R2140, Bytes40.
 * Only HMI-local LW970..979 are written. No PLC command or local bit write.
 * Called AFTER PumpAnimation, which owns the confirmed states LW903..905.
 */
#ifndef MainModeData
#error Configure_MainModeData_Batch16_R2300_Bytes2_ReadOnly
#endif
#ifndef MainRotationData
#error Configure_MainRotationData_Batch16_R2140_Bytes40_ReadOnly
#endif

static void MainOverview(IN *p)
{
    int i;
    int all_known;
    unsigned short state;
    unsigned short interval;
    unsigned short elapsed;
    unsigned short phase;
    unsigned short mode;
    unsigned short remaining;
    for (i = 970; i <= 979; ++i) LocalWord[i] = 0u;
    LocalWord[978] = 27135u;
    LocalWord[972] = !LocalBit[60107] ? 2u : (MapVersion != 32u ? 3u : 1u);
    if (LocalWord[972] != 1u) return;
    LocalWord[979] = 1u;
    all_known = 1;
    for (i = 0; i < 3; ++i) {
        state = LocalWord[903 + i];
        if (state == 2u) ++LocalWord[970];
        if (state < 1u || state > 4u) all_known = 0;
    }
    LocalWord[971] = (unsigned short)all_known;

    interval = MainRotationData[0];
    phase = MainRotationData[10];
    elapsed = MainRotationData[11];
    mode = MainModeData[0];
    if (mode != 0u && mode != 10u && mode != 11u && mode != 12u
            && mode != 20u && mode != 21u && mode != 22u && mode != 90u) return;
    state = 0u;
    if (interval > 32767u || phase == 91u) state = 8u;
    else if (phase == 90u) state = 7u;
    else if (phase == 20u) state = 4u;
    else if (phase == 30u) state = 5u;
    else if (phase == 11u) state = 6u;
    else if (phase == 10u) state = 3u;
    else if (phase == 0u || phase == 1u) {
        if (interval == 0u) state = 1u;
        else if (elapsed > interval) state = 0u;
        else if (mode != 12u) state = 9u;
        else if (phase == 1u) {
            state = 2u;
            remaining = (unsigned short)(interval - elapsed);
            LocalWord[974] = (unsigned short)(remaining / 60u);
            LocalWord[975] = (unsigned short)(remaining % 60u);
            LocalWord[976] = remaining;
            LocalWord[977] = 1u;
        }
    }
    LocalWord[973] = state;
}
