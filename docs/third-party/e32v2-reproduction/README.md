# Retained E32 SDK and runtime reproduction

These recipes reproduce the reviewed retained open SDK and compiler-runtime
objects from the pinned original source archives. They do not install firmware
or modify the installed framework, toolchain or project settings. Nine original
vendor binary-only archives have independently verified original origins; these
recipes do not claim to rebuild those vendor binaries from unavailable source.

Prepare a fresh working directory from the accompanying source distribution:

```sh
python3 scripts/e32_prepare_source_tree.py --archive /path/to/openthermostat-e32v2-source-inputs-20261023.1.zip --output out/e32-reproduction
```

The preparer verifies the complete pinned source package and every recipe hash
before extracting the ten original GitHub source snapshots with Python's safe
tar filter. It requires a Python version providing `tarfile.data_filter` and
refuses an existing output directory. Source and original license comments stay
unchanged. The actual Arduino and external-library snapshots remain in the
source distribution alongside their original notices.

With the exact PlatformIO packages installed, run inside the prepared directory:

```sh
python3 recompile-retained.py --all --report SDK-REPRODUCED.json
python3 recompile-assembly.py
python3 recompile-runtime.py --all --group runtime-reproduced --report RUNTIME-REPRODUCED.json
python3 recompile-startup.py
```

`PLATFORMIO_CORE_DIR` can point to a nondefault PlatformIO installation. The source
snapshot provides the full upstream component/build-system trees. The recipes
add the original SDK configuration, private includes, compiler producer options
and macro inputs needed to reproduce the retained objects. In particular, the
historical SDK app descriptor uses its original build date/time; those inputs
are not a current application timestamp or a device reading. The QIO assembly
headers reproduce the original SDK units without changing the application's DIO
flash configuration.

Comparison removes only debug sections and `.comment`; instruction, data,
symbol and section names are never rewritten. Each result records its original
object hash, source hash, complete executed command and comparison result.
Every required unit must report `EXACT_STRIPPED_OBJECT`: 346 C/C++ SDK units,
11 assembly units, 269 runtime units and three startup objects. Original archive
members with duplicate names are selected using their actual source identity.

Runtime generated configuration headers are retained unchanged in runtime-config.
Their corresponding GCC/Newlib/crosstool/overlay source and original notices are
in the pinned source distribution. Application source, actual application objects,
link recipes and deliberately modified-library relink verification are separate
per-application deliverables. None of this grants physical heating acceptance.
