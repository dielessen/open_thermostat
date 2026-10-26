"""Rebuild the eleven retained open SDK assembly members; original binaries stay untouched."""
from pathlib import Path
import importlib.util,json,concurrent.futures
out=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('sdk_recipe',out/'recompile-samples.py');recipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(recipe)
queue=json.loads((out/'ASSEMBLY-QUEUE.json').read_text())
def build(item):
    row=next(r for r in recipe.rows if r['path']==item['path'])
    return recipe.build_sample(row,unit=item['unit'],group='recompile-assembly')
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(build,queue))
(out/'RECOMPILE-ASSEMBLY.json').write_text(json.dumps(results,indent=2)+'\n')
for row in results:print(row['archive'],row['member'],row['status'])
