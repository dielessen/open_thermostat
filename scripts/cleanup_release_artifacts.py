"""Keep local release output tidy while preserving source, receipts and relink kits.

Defaults to a preview. Only out/ is eligible. Published old ZIPs require an
exact GitHub asset digest; identical retained ZIPs share read-only hard links.
"""
import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from organize_releases import classify, fetch

PROTECTED = ('SHA256SUMS.txt', 'RELINK-MANIFEST.json', 'NOTICE-INVENTORY.json',
             'backup-manifest.json', 'BACKUP-MANIFEST.json')


def filehash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def fingerprint(path):
    info=path.stat()
    return [info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_mode&0o777,info.st_uid,info.st_gid]


def protected(path, out):
    return any(any((parent/name).exists() for name in PROTECTED)
               for parent in (path,*path.parents) if parent==out or out in parent.parents)


def contains_source(target,root):
    if any(target.rglob('.git')):return True
    for parent in target.parents:
        if (parent/'.git').exists():
            result=subprocess.run(['git','-C',str(parent),'ls-files','--error-unmatch','--',
                                   str(target.relative_to(parent))],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            return result.returncode==0
        if parent==root:break
    return False


def plan(root, releases=(), keep=3):
    root=Path(root).resolve();out=root/'out'
    if keep<1:raise ValueError('keep_releases_must_be_positive')
    if out.is_symlink():raise ValueError('out_must_not_be_a_symlink')
    versions=sorted(((classify(row['tag_name'])[1],row['tag_name']) for row in releases
                     if not row['draft'] and classify(row['tag_name'])[0]=='firmware'),reverse=True)
    retained={tag for _,tag in versions[:keep]}
    policy=root/'docs/modern-thermostat/E32-UPDATE-GATE.json'
    if policy.is_file():
        data=json.loads(policy.read_text())
        retained.update(tag for tag in (data.get('pending_tag'),(data.get('accepted') or {}).get('tag')) if tag)
    public={}
    for row in releases:
        if row['draft'] or row['tag_name'] in retained or classify(row['tag_name'])[0]!='firmware':continue
        for asset in row.get('assets',[]):
            digest=asset.get('digest') or ''
            if asset['name'].endswith('.zip') and re.fullmatch('sha256:[0-9a-f]{64}',digest):
                public[(asset['name'],asset['size'],digest[7:])]=asset['browser_download_url']
    caches=[];archives=[]
    for base,dirs,files in os.walk(out,followlinks=False):
        parent=Path(base)
        dirs[:]=[name for name in dirs if name!='.git' and not (parent/name).is_symlink()]
        for name in list(dirs):
            target=parent/name
            cache=name in ('node_modules','__pycache__','.pytest_cache')
            cache|=name=='build' and parent.name=='.pio' and (parent.parent/'.git').exists() and (parent.parent/'platformio.ini').is_file()
            cache|=(target/'pyvenv.cfg').is_file()
            if cache and not protected(target,out) and not contains_source(target,root):
                caches.append({'path':str(target.relative_to(root))});dirs.remove(name)
        for name in files:
            path=parent/name
            if path.suffix.lower()=='.zip' and not path.is_symlink() and path.stat().st_size>=1_000_000:
                archives.append(path)
    sizes=defaultdict(list)
    for path in archives:
        info=path.stat();sizes[(info.st_dev,info.st_size,info.st_uid,info.st_gid,info.st_mode&0o555)].append(path)
    deleted=[];links=[]
    hashes={}
    for (_,size,uid,gid,mode),paths in sizes.items():
        matches=defaultdict(list)
        for path in sorted(paths):
            possible_public=any(name==path.name and length==size for name,length,_ in public)
            if len(paths)<2 and not possible_public:continue
            before=fingerprint(path);identity=tuple(before[:4])
            digest=hashes.get(identity)
            if digest is None:digest=hashes[identity]=filehash(path)
            if fingerprint(path)!=before:raise RuntimeError('archive_changed_during_preview')
            row={'path':str(path.relative_to(root)),'fingerprint':before,'sha256':digest}
            url=public.get((path.name,size,digest))
            if url and not protected(path,out):deleted.append({**row,'restore_url':url})
            elif uid==os.geteuid() and (path.stat().st_nlink==1 or before[4]&0o222==0):matches[digest].append(row)
        for digest,rows in matches.items():
            if len(rows)<2:continue
            canonical=min(rows,key=lambda row:(bool(row['fingerprint'][4]&0o222),-Path(root/row['path']).stat().st_nlink))
            different=[row for row in rows if row['fingerprint'][:2]!=canonical['fingerprint'][:2]]
            if different:links.append({'sha256':digest,'original_mode':canonical['fingerprint'][4],'files':[canonical,*different]})
    return {'schema':1,'root':str(root),'retained_release_tags':sorted(retained),
            'generated_caches':caches,'published_archive_removals':deleted,'identical_archive_groups':links}


def inside(root, relative):
    path=root/relative;out=root/'out'
    if path==out or not path.resolve().is_relative_to(out.resolve()):raise ValueError('cleanup_path_outside_out')
    current=path
    while current!=root:
        if current.is_symlink():raise ValueError('cleanup_symlink_refused')
        current=current.parent
    return path


def report_destination(root,path):
    path=Path(path)
    path=inside(root,path.relative_to(root) if path.is_absolute() else path)
    if path.suffix!='.json' or protected(path,root/'out'):raise ValueError('use_a_local_cleanup_json_report_in_out')
    if path.exists():
        saved=json.loads(path.read_text())
        if not isinstance(saved,dict) or saved.get('schema')!=1 or 'generated_caches' not in saved or saved.get('root')!=str(root):
            raise ValueError('refusing_to_overwrite_an_unrelated_report')
    return path


def apply(report):
    root=Path(report['root']).resolve();before=shutil.disk_usage(root).free
    # Validate every archive before changing any of them. A stale plan must be regenerated.
    rows=report['published_archive_removals']+[row for group in report['identical_archive_groups'] for row in group['files']]
    for row in rows:
        if fingerprint(inside(root,row['path']))!=row['fingerprint']:raise RuntimeError('archive_changed_since_preview')
    removed=linked=0
    for row in report['generated_caches']:
        target=inside(root,row['path'])
        if protected(target,root/'out'):raise ValueError('delivery_or_backup_tree_protected')
        if contains_source(target,root):raise ValueError('tracked_source_or_nested_repository_protected')
        shutil.rmtree(target);removed+=1
    for row in report['published_archive_removals']:
        inside(root,row['path']).unlink()
    for group in report['identical_archive_groups']:
        canonical=inside(root,group['files'][0]['path'])
        os.chmod(canonical,group['original_mode']&~0o222)
        for row in group['files'][1:]:
            duplicate=inside(root,row['path'])
            with tempfile.TemporaryDirectory(prefix='.ot-dedup-',dir=duplicate.parent) as temporary:
                link=Path(temporary)/'archive.zip'
                os.link(canonical,link);os.replace(link,duplicate)
            linked+=1
    return {'cache_directories_removed':removed,'published_archives_removed':len(report['published_archive_removals']),
            'duplicate_archives_linked':linked,'filesystem_free_bytes_delta':shutil.disk_usage(root).free-before}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--published-catalog',type=Path,help='Saved GitHub release API inventory; otherwise only caches/deduplication')
    parser.add_argument('--fetch-published',action='store_true',help='Read the public GitHub release catalog using gh')
    parser.add_argument('--keep-releases',type=int,default=3)
    parser.add_argument('--report',type=Path,required=True,help='Local report including restore URLs and archive identities')
    args=parser.parse_args()
    if args.fetch_published and args.published_catalog:parser.error('select one catalog source')
    root=Path(__file__).resolve().parents[1]
    try:args.report=report_destination(root,args.report)
    except (ValueError,OSError) as error:parser.error(str(error))
    releases=fetch('dielessen/open_thermostat') if args.fetch_published else json.loads(args.published_catalog.read_text()) if args.published_catalog else []
    report=plan(root,releases,args.keep_releases)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    result=apply(report) if args.apply else {'mode':'preview','cache_directories':len(report['generated_caches']),
        'old_published_archives':len(report['published_archive_removals']),'duplicate_archive_groups':len(report['identical_archive_groups'])}
    report['result']=result;args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':main()
