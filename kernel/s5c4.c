/* The S5C4 constant line, read by s5c4_line.s and s5c4_shared.s: one 16-byte,
 * 16-byte-aligned cache line. a, b and d are full float32 values; the fourth
 * word is 1.0. c and e are built in the code (lui). */
typedef struct {
    float a, b, d, one;
} TrigK;

const TrigK trig_k __attribute__((aligned(16))) = {
    9.585895168129355e-05f,     /* A   0x38c907e2 */
    -1.4591748490923317e-13f,   /* B   0xaa2449da */
    -4.594466140872555e-09f,    /* D   0xb19ddd5a */
    1.0f,                       /* ONE 0x3f800000 */
};
