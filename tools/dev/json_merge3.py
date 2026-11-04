"""Three-way merge of conflicted JSON files by key (stages 1/2/3 from the git index). Usage: json_merge3.py <repo> <path>..."""
import json, subprocess, sys

repo = sys.argv[1]
MISSING = object()


def stage(n, path):
    r = subprocess.run(["git", "-C", repo, "show", f":{n}:{path}"], capture_output=True, text=True, encoding="utf-8")
    return json.loads(r.stdout) if r.returncode == 0 else {}


def merge(base, ours, theirs, where, clashes):
    if isinstance(ours, dict) and isinstance(theirs, dict):
        base = base if isinstance(base, dict) else {}
        out = {}
        for key in list(ours) + [k for k in theirs if k not in ours]:
            o, t, b = ours.get(key, MISSING), theirs.get(key, MISSING), base.get(key, MISSING)
            if o is MISSING:
                if b is MISSING or t != b:
                    out[key] = t  # added by theirs (or changed by theirs after ours removed it)
                continue
            if t is MISSING:
                if b is MISSING or o != b:
                    out[key] = o
                continue
            out[key] = merge(None if b is MISSING else b, o, t, where + [key], clashes)
        return out
    if ours == theirs or theirs == base:
        return ours
    if ours == base:
        return theirs
    clashes.append(".".join(where))
    return theirs


for path in sys.argv[2:]:
    clashes = []
    result = merge(stage(1, path), stage(2, path), stage(3, path), [], clashes)
    with open(f"{repo}/{path}", "w", encoding="utf-8", newline="\n") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(path, "clashes (took theirs):", clashes or "none")
