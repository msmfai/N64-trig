#ifndef S5C6_H
#define S5C6_H

/* S5C6 sine/cosine for the N64 (VR4300): see s5c6.s.
 * Binary angles: 0x10000 is one turn; only the low 16 bits are used. */
float trig_sin(int angle);

/* Drop-in for SM64-style macros. */
#define sins(x) trig_sin((unsigned short) (x))
#define coss(x) trig_sin((unsigned short) (x) + 0x4000)

#endif
