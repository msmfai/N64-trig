#ifndef SINCOS_H
#define SINCOS_H

/* Sine and cosine of one angle in one call: kernel/sincos.s or sincos_code.s.
 * GNU C returns _Complex float in $f0/$f2, so nothing goes through memory.
 * sincoss(a, s, c) sets s = sins(a), c = coss(a). */
_Complex float trig_sincos(int angle);
#define sincoss(x, s, c) do { _Complex float _sc = trig_sincos((unsigned short) (x)); \
    (s) = __real__ _sc; (c) = __imag__ _sc; } while (0)

#endif
