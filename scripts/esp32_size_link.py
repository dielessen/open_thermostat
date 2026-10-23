"""Use the pinned Xtensa linker's size preference on the 4 MB generic board."""
Import("env")

# E32 and S3 have their own build profiles. Keep their code-layout policy intact.
if env.subst("$PIOENV") == "esp32dev":
    env.AppendUnique(LINKFLAGS=["-Wl,--size-opt", "-Os", "-flto"])

    def verify_actual_ota_image(source, target, env):
        import csv
        from pathlib import Path
        root = Path(env.subst("$PROJECT_DIR"))
        table = root / env.GetProjectOption("board_build.partitions")
        rows = csv.reader(line for line in table.read_text().splitlines()
                          if line.strip() and not line.lstrip().startswith("#"))
        slots = {row[2].strip(): int(row[4].strip(), 0) for row in rows
                 if len(row) >= 5 and row[1].strip() == "app" and row[2].strip() in ("ota_0", "ota_1")}
        image = Path(str(target[0]))
        size = image.stat().st_size
        if set(slots) != {"ota_0", "ota_1"} or not 0 < size <= min(slots.values()):
            raise RuntimeError(f"Actual firmware image {size} bytes does not fit both OTA slots: {slots}")
        print(f"PASS: actual OTA image {size} bytes fits both app slots")

    env.AddPostAction("$BUILD_DIR/${PROGNAME}.bin", verify_actual_ota_image)
