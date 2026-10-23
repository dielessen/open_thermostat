"""Use the pinned Xtensa linker's size preference on the 4 MB generic board."""
Import("env")

# E32 and S3 have their own build profiles. Keep their code-layout policy intact.
if env.subst("$PIOENV") == "esp32dev":
    env.AppendUnique(LINKFLAGS=["-Wl,--size-opt"])
