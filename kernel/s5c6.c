/* The four full-precision S5C6 coefficients, read by s5c6.s: one 16-byte,
 * 16-byte-aligned cache line. S5 and C6 are built in the code (lui). */
typedef struct {
    float s1, s3, c2, c4;
} TrigK;

const TrigK trig_k __attribute__((aligned(16))) = {
     9.586999658495188e-05f,   /* S1  0x38c90dd0 */
    -1.4654559033280834e-13f,  /* S3  0xaa24fee4 */
    -4.595529734530146e-09f,   /* C2  0xb19de6b5 */
     3.4901736165623554e-18f,  /* C4  0x2280c3c2 */
};
