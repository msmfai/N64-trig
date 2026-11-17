// Ares 64 (github.com/HailToDodongo/ares-64) headless runner script for one
// trig benchmark ROM. bench/run.py starts it when --ares points to ares-test:
//
//   ares-test bench/ares64.js ROM [renderer] [interp|recomp] --timeout SECONDS
//
// The ROM plays the seven demos, prints "TRIGBENCH <hex>" through emux XLOG
// and asks ares to exit. Homebrew Mode enables emux and the bus counters.
// interp (default): the CPU interpreter, which fetches every instruction
// through the modelled caches. The recompiler does not, so its cache counts
// differ. renderer "none" skips RDP rendering; ares does not time the RDP.
ares.setHomebrew(true);
ares.setRecompiler((ares.args[2] || "interp") !== "interp");
ares.loadRom(ares.args[0]);
ares.setRenderer(ares.args[1] || "none");
ares.resume();
let result = null;
ares.onLog(line => {
  if (line.startsWith("TRIGBENCH ") && !line.startsWith("TRIGBENCH demo")) result = line;
});
while (result === null) ares.wait(1.0);
ares.exit(0);
