/* Shared layout between the Schwung DSP plugin (writer) and the SC UGen (reader). */
#ifndef PHMIC_H
#define PHMIC_H
#include <stdint.h>

#define PHMIC_SHM   "/poundhard-micin"
#define PHMIC_MAGIC 0x494D4850u          /* 'PHMI' */
#define PHMIC_FRAMES 65536               /* ~1.5 s at 44.1k, power of two for cheap wrap */

/* Single writer (the plugin's audio callback), single reader (the engine). No locks: the
 * writer publishes `write` with a release barrier AFTER filling the samples, so a reader
 * that sees an index is guaranteed the samples behind it are already there. A reader that
 * falls behind loses old audio, which is the correct failure for a live microphone. */
typedef struct {
    uint32_t magic;
    uint32_t version;
    uint32_t frames;        /* ring capacity */
    uint32_t sample_rate;
    volatile uint32_t write;    /* monotonic frame counter */
    volatile uint32_t blocks;   /* process_block calls — the heartbeat */
    volatile uint32_t peak;     /* |peak| of the last block, 0..32767 */
    volatile uint32_t flags;    /* 1 = host handed us a mailbox pointer */
    float samples[PHMIC_FRAMES];
} phmic_shm_t;

#endif
