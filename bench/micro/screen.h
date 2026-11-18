/* Text on the N64 screen for the timing ROM (bench/micro, MICRO_HW builds).
 * NTSC 320x240, 16 bits per pixel, framebuffer at 0x00300000, set up directly
 * through the VI registers. The public-domain font8x8_basic (font8x8_basic.h).
 * Text stays inside the area a TV shows: columns 2 to 37, rows 2 to 27. */
#include "font8x8_basic.h"

#define FB ((volatile unsigned short *) 0xA0300000)   /* uncached: no write-back needed */
#define VI_REG(n) (*(volatile unsigned int *) (0xA4400000 + 4 * (n)))

static void screen_init(void) {
    static const unsigned int vi[14] = {
        0x00003302,   /* status: 16 bpp, no anti-aliasing or resampling, pixel advance 3 */
        0x00300000,   /* origin */
        320,          /* width */
        2,            /* vertical interrupt line */
        0,            /* current line */
        0x03E52239,   /* burst (NTSC) */
        0x0000020D,   /* vertical sync: 525 half lines */
        0x00000C15,   /* horizontal sync */
        0x0C150C15,   /* horizontal sync leap */
        0x006C02EC,   /* horizontal video */
        0x002501FF,   /* vertical video */
        0x000E0204,   /* vertical burst */
        0x00000200,   /* x scale: 320 pixels */
        0x00000400,   /* y scale: 240 lines */
    };
    int i;
    for (i = 0; i < 320 * 240; i++) FB[i] = 0x0001;    /* black (alpha bit set) */
    for (i = 0; i < 14; i++) VI_REG(i) = vi[i];
}

static void screen_text(int col, int row, const char *s) {
    col += 2;                                         /* the left margin */
    row += 2;                                         /* the top margin */
    for (; *s && col < 38; s++, col++) {
        const unsigned char *g = font8x8_basic[(unsigned char) *s & 0x7F];
        int y, x;
        for (y = 0; y < 8; y++) {
            for (x = 0; x < 8; x++) {
                FB[(row * 8 + y) * 320 + col * 8 + x] = (g[y] >> x) & 1 ? 0xFFFF : 0x0001;
            }
        }
    }
}
