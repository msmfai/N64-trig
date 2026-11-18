// Run a console (--hardware) benchmark ROM to its results screen and save a screenshot.
// usage: ares-test hwshot.js ROM OUT.png [emulated seconds]
ares.setHomebrew(false);           // as a console: no emulator extensions
ares.setRecompiler(false);         // interpreter: every instruction through the modelled caches
ares.loadRom(ares.args[0]);
ares.setRenderer("none");          // fast while the demos run
ares.resume();
ares.wait(Number(ares.args[2] || 600));
ares.setRenderer("angrylion");     // draw the results screen
ares.waitFrames(4);
ares.screenshot().save(ares.args[1]);
ares.exit(0);
