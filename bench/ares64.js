// Ares 64 (github.com/HailToDodongo/ares-64) headless runner script for one
// trig benchmark ROM. bench/run.py starts it when --ares points to ares-test:
//
//   ares-test bench/ares64.js ROM [renderer] [interp|recomp] [rsp-recomp|rsp-interp] --timeout SECONDS
//
// The ROM plays the seven demos, prints "TRIGBENCH <hex>" through emux XLOG
// and asks ares to exit. Homebrew Mode enables emux and the bus counters.
// interp (default): the CPU interpreter, which fetches every instruction
// through the modelled caches. The recompiler does not, so its cache counts
// differ. rsp-recomp (default): the RSP runs on the recompiler, about 3 times
// faster; it needs the local Ares 64 change that separates the two executors
// (with an unchanged Ares 64 the RSP follows the CPU). renderer "none" skips
// RDP rendering; ares does not time the RDP.
ares.setHomebrew(true);
ares.setRecompiler((ares.args[2] || "interp") !== "interp", (ares.args[3] || "rsp-recomp") === "rsp-recomp");
ares.loadRom(ares.args[0]);
ares.setRenderer(ares.args[1] || "none");
ares.resume();
let result = null;
ares.onLog(line => {
  if (line.startsWith("TRIGBENCH ") && !line.startsWith("TRIGBENCH demo")) result = line;
});
while (result === null) ares.wait(1.0);
ares.exit(0);
