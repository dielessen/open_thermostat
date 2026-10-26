"""Save actual expanded E32 link and LGPL-library compile commands for packaging."""
import json
from pathlib import Path

Import("env")


def capture(variable, filename):
    def action(source, target, env):
        commands = env.subst_list(env[variable], target=target, source=source)
        if len(commands) != 1 or not commands[0]:
            raise RuntimeError("A single expanded command is required for relink capture")
        receipt = Path(env.subst("$BUILD_DIR")) / filename
        receipt.write_text(json.dumps([str(arg) for arg in commands[0]], indent=2) + "\n")
    return action


if env.subst("$PIOENV") == "e32v2":
    env.AddPreAction("$BUILD_DIR/${PROGNAME}.elf", capture("LINKCOM", "relink-command.json"))
    env.AddPreAction("$BUILD_DIR/FrameworkArduino/esp32-hal-misc.c.o",
                     capture("CCCOM", "arduino-misc-compile-command.json"))
