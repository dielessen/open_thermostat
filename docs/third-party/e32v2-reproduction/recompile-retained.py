"""Bounded full retained C/C++ trial; uses reviewed sample recipe, no installation."""
from pathlib import Path
import argparse,concurrent.futures,importlib.util,json

out=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('sdk_sample_recipe',out/'recompile-samples.py')
recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
queue=[];missing=[]
for row in recipe.rows:
    for unit in row['compilation_units']:
        if not unit.get('name','').endswith(('.c','.cpp','.cc')):continue
        if recipe.resolve(unit['name']):queue.append((row,unit))
        else:missing.append(dict(archive=Path(row['path']).name,unit=unit,status='SOURCE_NOT_IN_ORIGINAL_OPEN_SNAPSHOTS'))
parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--all',action='store_true');parser.add_argument('--report',default='RECOMPILE-FULL.json');args=parser.parse_args()
assert Path(args.report).name==args.report and args.report.endswith('.json')
previous={'results':[]} if args.all else json.loads((out/'RECOMPILE-FULL-CMAKE-RECIPE.json').read_text())
results=[r for r in previous['results'] if r['status']=='EXACT_STRIPPED_OBJECT']
done={(r['archive'],r['member'],r['source']) for r in results}
queue=[(r,u) for r,u in queue if (Path(r['path']).name,u['member'],str(recipe.resolve(u['name']).relative_to(out))) not in done]
total=len(queue)+len(results)
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    futures={pool.submit(recipe.build_sample,row,unit=unit,group='source-offer-sdk' if args.all else 'recompile-full'):(row,unit) for row,unit in queue}
    for future in concurrent.futures.as_completed(futures):
        row,unit=futures[future]
        try:result=future.result()
        except Exception as error:result=dict(archive=Path(row['path']).name,member=unit['member'],status='ERROR',error=type(error).__name__,detail=str(error))
        results.append(result)
        (out/args.report).write_text(json.dumps(dict(scope='retained C/C++ source trial, no whole SDK release claim',queued=total,unavailable=missing,results=sorted(results,key=lambda r:(r['archive'],r['member']))),indent=2)+'\n')
        if len(results)%25==0 or len(results)==total:print('completed',len(results),'/',total,flush=True)

if len(results)!=total or any(r['status']!='EXACT_STRIPPED_OBJECT' for r in results):raise SystemExit(1)
