// Run the console build of the timing ROM (bench/micro/build.py --hardware) as a console would
// (no Homebrew Mode, CPU interpreter) and save the screen:
//   ares-test bench/micro/screen.js ROM OUT.png [emulated seconds]
ares.setHomebrew(false);
ares.setRecompiler(false, true);
ares.loadRom(ares.args[0]);
ares.setRenderer("none");          // the CPU draws the text: the VI scanout of RDRAM shows it
ares.resume();
ares.wait(Number(ares.args[2] || 20));
ares.screenshot().save(ares.args[1]);
ares.exit(0);
