/* Read-only component. Native adapter owns aliases, RTC conversion and audited
 * local word/bit allocation. No PLC writes, commands, keypad or local timer.
 * words = one coherent read-only Batch16 R3120..R3125 (12 bytes).
 * sourceGood = successful fresh batch + PLC link + Map32 + contract27110.
 * autoMode = existing physical AUTO gate; nowSeconds = advancing HMI RTC seconds.
 */
typedef struct {
    unsigned short initialized, moving, heartbeat;
    unsigned long changedAt, lastNow;
} OshskyCountdownState;

typedef struct {
    unsigned short action, pump, seconds;
} OshskyCountdownOutput;

static void OshskyCountdown(OshskyCountdownState *s,
        const unsigned short *words, unsigned short sourceGood,
        unsigned short autoMode, unsigned long nowSeconds,
        OshskyCountdownOutput *out)
{
    out->action = out->pump = out->seconds = 0u;
    if (!sourceGood || words[0] != 27402u) {
        s->initialized = s->moving = 0u;
        return;
    }
    if (!s->initialized || nowSeconds < s->lastNow) {
        s->initialized = 1u;
        s->moving = 0u;
        s->heartbeat = words[5];
        s->changedAt = s->lastNow = nowSeconds;
        return;
    }
    s->lastNow = nowSeconds;
    if (s->heartbeat != words[5]) {
        s->heartbeat = words[5];
        s->changedAt = nowSeconds;
        s->moving = 1u;
    }
    if (nowSeconds - s->changedAt >= 3ul) s->moving = 0u;
    if (!s->moving || !autoMode) return;
    if (words[1] != 1u && words[1] != 2u) return;
    if (words[2] < 1u || words[2] > 4u || words[3] < 1u) return;
    if (words[4] < 1u || words[4] > (words[1] == 1u ? 3600u : 1800u)) return;
    if (words[3] > words[4]) return;
    out->action = words[1];
    out->pump = words[2];
    out->seconds = words[3];
}
