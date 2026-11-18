// Ares 64 headless runner script for the timing ROM (bench/micro):
//   ares-test bench/micro/micro.js work/micro/micro.z64 [interp|recomp] --timeout SECONDS
// The ROM prints "MICRO ..." lines through emux XLOG and asks ares to exit.
ares.setHomebrew(true);
ares.setRecompiler((ares.args[1] || "interp") !== "interp");
ares.loadRom(ares.args[0]);
ares.setRenderer("none");
ares.resume();
let done = false;
ares.onLog(line => { if (line.startsWith("MICRODONE")) done = true; });
while (!done) ares.wait(0.5);
ares.exit(0);
