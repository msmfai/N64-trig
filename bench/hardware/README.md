# Console test: HackerSM64 benchmark patches

These patches make the in-game benchmark of this repository run on a real N64. Each patch makes one ROM. Each ROM uses one kernel. The ROM plays the seven attract-mode demos of SM64, measures the CPU time of each frame, and then shows the results on the title screen.

The patches contain no ROM. You must supply your own copy of the base ROM.

> [!NOTE]
> The patch hashes and the emulator values below are for the build of commit 8b95f76 with the results screen. A build from a later commit gives different hashes and values. Make the patches and the values again for each console test (refer to [Build](#build)).

## Patches

| Patch | Kernel | SHA-1 of the patched ROM |
|---|---|---|
| `asilas-sc.bps` | Silas Lock | `6655adc0424649add03a30ff09f2b11eb8b2bf7c` |
| `abfskl-sc.bps` | S5C6, one cache line | `2603e9c720245d9db51c0ee17d7ba205108957cd` |
| `abfsk-sc.bps` | S5C6, pure code | `9102d8c6a05a17791105ace10e0351ab075d3faf` |
| `aone-sc.bps` | S5C6, quantized | `5b1056b82da1890b7713e433adadd02f74618c51` |

All four ROMs use `sincoss()` at the 13 changed call sites ([`bench/hsm64-sincos.patch`](../hsm64-sincos.patch)).

## Base ROM

| Item | Value |
|---|---|
| Game | Super Mario 64, USA (NTSC) |
| Format | `.z64` (big-endian). Convert a `.n64` or `.v64` file to `.z64` before you patch it. |
| Size | 8,388,608 bytes (8 MiB) |
| SHA-1 | `9bef1128717f958171a4afac3ed78ee2bb4e86ce` |
| MD5 | `20b854b239203baf6c961b850a4a51a2` |
| CRC-32 | `3ce60709` |

The patcher refuses a different ROM: each patch checks the CRC-32 of the base ROM.

## Equipment

| Item | Requirement |
|---|---|
| Console | N64, NTSC |
| Expansion Pak | Required (the ROM uses 8 MB of RAM) |
| Flash cart | Any cart that runs a ROM of 8.2 MB, for example EverDrive 64, SummerCart64 or 64drive |
| Controller | Not used |

## Procedure

1. Patch the base ROM with one patch. Use [Rom Patcher JS](https://www.marcrobledo.com/RomPatcher.js/) or Floating IPS.
2. Compare the SHA-1 of the patched ROM with the table above.
3. Copy the patched ROM to the flash cart.
4. Start the ROM. Do not touch the controller. The title screen shows the demos one after the other.
5. Wait until the results screen shows. This takes approximately 4 minutes. The results stay on the screen.
6. Take a photograph of the screen.
7. Do steps 1 to 6 again for each patch.
8. Send the four photographs, the console region, and the name of the flash cart.

## Results screen

| Field | Meaning |
|---|---|
| Name (top left) | The kernel: `SILAS`, `S5C6 LINE` (one cache line), `S5C6 CODE` (pure code) or `S5C6 8 BIT` (quantized) |
| `1` to `7` | Game-thread CPU time of each demo, in µs per frame |
| `ALL` | Game-thread CPU time of all demos, in µs per frame |
| `CYCLES ×10` | CPU cycles for each call, multiplied by 10, with random angles and a warm cache |
| `SIN` | One `trig_sin` call |
| `PAIR` | One sine and one cosine as two `trig_sin` calls |
| `SC` | One `trig_sincos` call |
| `CRC` | CRC-32 of the bit patterns of the sine and the cosine of all 65,536 angles |
| `BAD` | The number of angles where `trig_sincos` differs from two `trig_sin` calls |
| `HASH` | The position hashes of Mario of all demos, combined |

## Emulator values

These values come from [Ares 64](https://github.com/HailToDodongo/ares-64) (commit b4ead632f) with the CPU interpreter and with Homebrew Mode off. Compare them with the console:

- `CRC` must be the same. A different `CRC` means that the console calculates a different float32 result.
- `BAD` must be 0.
- `HASH` must be the same. A different `HASH` means that the demos played a different game.
- The times and the cycles are the measurements. The console values replace the emulator values.

| Field | `SILAS` | `S5C6 LINE` | `S5C6 CODE` | `S5C6 8 BIT` |
|---|---|---|---|---|
| `1` | 11,358 | 11,518 | 11,508 | 11,527 |
| `2` | 13,901 | 14,082 | 13,955 | 14,075 |
| `3` | 12,381 | 12,458 | 12,324 | 12,449 |
| `4` | 15,136 | 15,015 | 14,867 | 15,027 |
| `5` | 11,795 | 11,777 | 11,606 | 11,758 |
| `6` | 17,732 | 17,715 | 17,545 | 17,683 |
| `7` | 8,344 | 8,387 | 8,299 | 8,404 |
| `ALL` | 12,404 | 12,438 | 12,319 | 12,438 |
| `SIN` | 654 | 545 | 545 | 530 |
| `PAIR` | 1320 | 1099 | 1099 | 1070 |
| `SC` | 929 | 895 | 915 | 885 |
| `CRC` | `C457EF86` | `7FB7F6D0` | `7FB7F6D0` | `7BA50950` |
| `BAD` | 0 | 0 | 0 | 0 |
| `HASH` | `3AFAC265` | `F733065A` | `F733065A` | `597A7297` |

The screenshots of these results are in [`expected/`](expected/). [`hwshot.js`](hwshot.js) makes them with the Ares 64 headless runner. The CRC values agree with [`fit/accuracy.py`](../../fit/accuracy.py), which calculates the same float32 values independently.

The in-game times are for one code layout. Other layouts change them by up to approximately ±3 % (refer to the main README).

## Build

The ROMs come from `bench/build.py --hardware --cycles --variants asilas-sc abfskl-sc abfsk-sc aone-sc`. `--hardware` removes the instructions that only ares executes. The patches come from `python3 bench/hardware/bps.py create BASE ROM PATCH`, and `python3 bench/hardware/bps.py apply BASE PATCH OUT` applies a patch.
