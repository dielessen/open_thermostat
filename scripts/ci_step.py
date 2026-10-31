"""Print the shell script of one step of a GitHub workflow, so a local run uses exactly CI's commands.

Usage: python3 scripts/ci_step.py <workflow.yml> "<step name>" [--drop-prefix "pip install" ...]
The step is found by its exact `- name:` line; its `run: |` block (or inline `run:`) is printed dedented.
Exit 2 when the step or its run block is missing (CI changed: review the final-check script).
"""
import sys
from pathlib import Path

args = sys.argv[1:]
drop = []
while "--drop-prefix" in args:
    index = args.index("--drop-prefix")
    drop.append(args[index + 1])
    del args[index:index + 2]
workflow, name = Path(args[0]), args[1]
lines = workflow.read_text(encoding="utf-8").splitlines()
start = next((i for i, line in enumerate(lines) if line.strip() == f"- name: {name}"), None)
if start is None:
    print(f"step not found: {name}", file=sys.stderr)
    sys.exit(2)
step_indent = len(lines[start]) - len(lines[start].lstrip())
body = []
for line in lines[start + 1:]:
    if line.strip() and len(line) - len(line.lstrip()) <= step_indent:
        break
    body.append(line)
run = next((i for i, line in enumerate(body) if line.strip().startswith("run:")), None)
if run is None:
    print(f"no run block in step: {name}", file=sys.stderr)
    sys.exit(2)
head = body[run].strip()[4:].strip()
if head not in ("|", "|-", ">"):
    script = [head]
else:
    indent = len(body[run]) - len(body[run].lstrip())
    script = []
    for line in body[run + 1:]:
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        script.append(line)
    width = min((len(l) - len(l.lstrip()) for l in script if l.strip()), default=0)
    script = [l[width:] for l in script]
script = [l for l in script if not any(l.lstrip().startswith(p) for p in drop)]
print("\n".join(script).rstrip() + "\n")
