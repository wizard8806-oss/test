/* r15 extension: generated Batch16 aliases only. No assumed pVar layout.
 * PLC reset frame R3216..3221 is frozen until ack or local timeout.
 * Buttons LB1250..1252 are local requests, not drive/RUN writes.
 */
#ifndef NativeFaultData
#error Configure_NativeFaultData_Batch16_R3040_Bytes80_ReadOnly
#endif
#ifndef DriveResetData
#error Configure_DriveResetData_Batch16_R3200_Bytes64_ReadOnly
#endif
#ifndef DriveResetRequest
#error Configure_DriveResetRequest_Batch16_R3216_Bytes12_WriteOnly
#endif
static unsigned int native_alarm_mask = 0u;
static unsigned short native_event_seq = 0u;
static unsigned short native_sample_seq[3] = {0u,0u,0u};
static unsigned short native_sample_age[3] = {65535u,65535u,65535u};
static unsigned short reset_session = 0u;
static unsigned short reset_window = 0u;
static unsigned short reset_window_age = 65535u;
static unsigned short reset_frame[6] = {0u,0u,0u,0u,0u,0u};
static unsigned short reset_pending_ticks = 0u;
static int reset_started = 0;
static int reset_window_live = 0;
static int reset_pending = 0;
static int reset_target = 0;

static int NativeFaultService(IN *p)
{
    int i;
    int valid;
    int event;
    unsigned short seq;
    unsigned short state;
    valid = LocalBit[60107] && MapVersion == PANEL_MAP_VERSION
        && NativeFaultData[9] == 27120u && NativeFaultData[35] <= 7u;
    event = 0;
    LocalWord[940] = 27130u;
    LocalWord[941] = NativeFaultData[9];
    LocalWord[942] = NativeFaultData[35];
    LocalWord[943] = NativeFaultData[36];
    LocalWord[944] = (unsigned short)valid;
    LocalWord[945] = (unsigned short)((LocalWord[945] + 1u) % 60000u);
    if (valid) {
        native_alarm_mask = ((unsigned int)NativeFaultData[35]) << 24;
        event = (NativeFaultData[36] != native_event_seq && native_alarm_mask != 0u);
        native_event_seq = NativeFaultData[36];
    }
    for (i = 0; i < 3; ++i) {
        seq = NativeFaultData[6 + i];
        if (valid && seq != 0u && seq != native_sample_seq[i]) {
            native_sample_seq[i] = seq;
            native_sample_age[i] = 0u;
        } else if (native_sample_age[i] < 65535u) {
            ++native_sample_age[i];
        }
        state = NativeFaultData[10 + i];
        if (!valid) {
            state = 4u;
        } else if (state > 3u || seq == 0u) {
            state = 0u;
        } else if (native_sample_age[i] > 24u || NativeFaultData[3 + i] != 1u) {
            state = 3u;
        }
        LocalWord[956 + i] = state;
    }
    return event;
}

static void DriveResetService(IN *p)
{
    int i;
    int click;
    int valid;
    unsigned short session;
    unsigned short window;
    unsigned short seq;
    unsigned short permit;
    if (!reset_started) {
        for (i = 0; i < 3; ++i) { LocalBit[1250 + i] = 0; }
        reset_started = 1;
    }
    click = -1;
    for (i = 0; i < 3; ++i) {
        if (LocalBit[1250 + i]) {
            if (click == -1) { click = i; } else { click = 3; }
        }
        LocalBit[1250 + i] = 0;
    }
    valid = LocalBit[60107] && MapVersion == PANEL_MAP_VERSION
        && DriveResetData[0] == 27131u && NativeFaultData[9] == 27120u;
    session = DriveResetData[15];
    window = DriveResetData[25];
    if (!valid || session == 0u || window == 0u || session != reset_session) {
        reset_pending = 0;
        reset_window_live = 0;
        reset_window_age = 65535u;
        reset_session = valid ? session : 0u;
        reset_window = window;
        reset_frame[0] = 0u;
        LocalWord[947] = 4u;
        for (i = 0; i < 3; ++i) { LocalWord[950 + i] = 4u; }
    } else {
        if (window != reset_window) {
            reset_window = window;
            reset_window_age = 0u;
            reset_window_live = 1;
        } else if (reset_window_age < 65535u) { ++reset_window_age; }
        if (reset_window_age > 16u) {
            reset_window_live = 0;
            reset_pending = 0;
            reset_frame[0] = 0u;
        }
        for (i = 0; i < 3; ++i) {
            LocalWord[950 + i] = DriveResetData[6 + i] <= 4u ? DriveResetData[6 + i] : 4u;
        }
        if (reset_pending) {
            if (DriveResetData[22] == reset_frame[1]
                    && DriveResetData[23] == reset_frame[0]) {
                reset_pending = 0;
                reset_frame[0] = 0u;
            } else if (++reset_pending_ticks > 12u) {
                reset_pending = 0;
                reset_frame[0] = 0u;
                LocalWord[950 + reset_target] = 4u;
            } else {
                LocalWord[950 + reset_target] = 1u;
            }
        }
        LocalWord[947] = !reset_window_live ? 4u
            : (DriveResetData[27] != 1u ? 3u : (DriveResetData[1] != 0u ? 1u : 0u));
        if (click >= 0 && click < 3) {
            permit = (unsigned short)(1u << click);
            if (!reset_window_live || reset_pending || DriveResetData[1] != 0u) {
                LocalWord[950 + click] = 4u;
            } else if (DriveResetData[27] != 1u) {
                LocalWord[950 + click] = 3u;
            } else if (!(DriveResetData[9] & permit)) {
                LocalWord[950 + click] = 4u;
            } else {
                seq = (unsigned short)(DriveResetData[22] + 1u);
                if (seq == 0u) { seq = 1u; }
                reset_frame[0] = permit;
                reset_frame[1] = seq;
                reset_frame[2] = session;
                reset_frame[3] = (unsigned short)(session ^ 65535u);
                reset_frame[4] = window;
                reset_frame[5] = (unsigned short)(window ^ 65535u);
                reset_pending = 1;
                reset_pending_ticks = 0u;
                reset_target = click;
                LocalWord[950 + click] = 1u;
            }
        }
    }
    for (i = 0; i < 6; ++i) { DriveResetRequest[i] = reset_frame[i]; }
}
