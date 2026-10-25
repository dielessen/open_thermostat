"""Bind a local native test report to reviewed source, never live HA data."""
from pathlib import Path
import hashlib
import json
import subprocess


def snapshot(root):
    root=Path(root).resolve()
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
    clean=not subprocess.check_output(['git','status','--porcelain'],cwd=root)
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
    files={}
    for name in tracked:
        if name.startswith('ha/') or name in ('scripts/ha_test_evidence.py','scripts/package_ha_release.py'):
            path=root/name
            # Removed/replaced/symlink source may never attest as clean.
            if not path.is_file() or path.is_symlink():
                clean=False;continue
            files[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return dict(source_commit=head,source_sha256=hashlib.sha256(
        json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest(),clean_source=clean)
