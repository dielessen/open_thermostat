"""Run the unmodified accepted alpha36 discovery code against a beta package.

Local host proof only: no HTTP, device, flash or physical acceptance. The final
package must separately pass verify_e32v2_release and the native update gate.
Requires retained git source and a local native cJSON dependency.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import tempfile

PREDECESSOR = '7ddf3410666d814850275433d9dddd266e5d83ba'
HEADERS = {
    'src/update/ReleasePolicy.h': '33ae0c5bc67bfb33ce45dbc7f23a812ff4109816a6ca89a97e82d206909187aa',
    'src/update/ReleaseCatalog.h': '2e1c8a6f3fb99921c6493a370e64213a697017f2b92a87a69cca832a1d1a2192',
    'src/update/IndexedReleaseCatalog.h': '39f6bea7b771e1635e149b7291feec4d6548628210200109d845465f88863d14',
    'src/control/BoundedJson.h': 'f569fc2470c32e411be5fa4456d686827a16887994689f31c69d2298f2097249',
}
RUNNER = r'''
#include "update/IndexedReleaseCatalog.h"
#include <fstream>
#include <iostream>
#include <iterator>
#include <map>
using namespace heating::update;
int main(int argc,char**argv) {
    if(argc!=2)return 1;
    std::ifstream input(argv[1]);
    std::string bytes((std::istreambuf_iterator<char>(input)),{});
    auto doc=releaseJson(bytes);if(!doc)return 2;
    const auto tag=string(doc.get(),"version");Manifest manifest;
    if(!parseManifest(bytes,tag,manifest))return 3;
    const auto refs="[{\"ref\":\"refs/tags/"+tag+"\",\"object\":{\"type\":\"commit\",\"sha\":\""+manifest.source+"\"}}]";
    unsigned calls=0;std::vector<Release> choices{{"previous",false}};std::string error;
    auto indexed=[&](const std::string&url,size_t limit,std::string&out,std::string&,int&status) {
        ++calls;if(url!=releaseReferenceApi||refs.size()>limit)return false;
        out=refs;status=200;return true;
    };
    if(discoverIndexedReleases(indexed,choices,error)!=IndexedCatalogResult::Legacy
        ||calls!=1||choices.size()!=1||choices[0].tag!="previous")return 4;
    auto entry="[{\"tag_name\":\""+tag+"\",\"draft\":false,\"prerelease\":true,\"published_at\":\"2026-10-25T00:00:00Z\",\"assets\":[{\"name\":\"e32v2-update.json\"},{\"name\":\"firmware.bin\"}]}]";
    // Prove all twelve possible positions of a newly published beta. Entries
    // for HA are intentionally skipped; the thirteenth position is NOT covered.
    for(unsigned position=1;position<=maxReleasePages;++position) {
        calls=0;choices={{"previous",false}};
        auto fetch=[&](const std::string&url,size_t limit,std::string&out,std::string&) {
            ++calls;
            if(url==assetUrl(tag,"e32v2-update.json"))out=bytes;
            else {
                unsigned page=1;while(page<=maxReleasePages&&url!=releasePageUrl(page))++page;
                if(page>maxReleasePages)return false;
                out=page==position?entry:"[{\"tag_name\":\"ha-v0.4.0b1\",\"draft\":false}]";
            }
            return out.size()<=limit;
        };
        if(!discoverReleases(fetch,choices,error)||choices.size()!=1
            ||choices[0].tag!=tag||!choices[0].prerelease||calls!=13)return 5;
    }
    // A failed manifest transfer preserves previous choices; no partial result.
    calls=0;choices={{"previous",false}};
    auto failed=[&](const std::string&url,size_t,std::string&out,std::string&) {
        ++calls;if(url==releasePageUrl(1)){out=entry;return true;}return false;
    };
    if(discoverReleases(failed,choices,error)||choices.size()!=1||choices[0].tag!="previous")return 6;
    std::cout<<"PASS: retained alpha36 beta manifest, index fallback, 12 bounded positions, failed-fetch preservation\n";
}
'''


def verify(root, manifest_path, image_path):
    root = Path(root).resolve()
    raw = Path(manifest_path).read_bytes()
    manifest = json.loads(raw)
    if not re.fullmatch(r'v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)-e32v2-beta\.(?:0|[1-9]\d*)', manifest['version']):
        raise ValueError('expected_beta_candidate')
    image = Path(image_path).read_bytes()
    marker = f"OT_E32V2_OTA_V1:{manifest['version']}:{manifest['source_commit']}:{manifest['web_sha256']}:END".encode()
    if len(image) != manifest['size'] or hashlib.sha256(image).hexdigest() != manifest['sha256'] or marker not in image:
        raise ValueError('candidate_image_identity_mismatch')
    cjson = root / '.pio/libdeps/native/cJSON'
    with tempfile.TemporaryDirectory(prefix='opth-alpha36-') as temp:
        work = Path(temp)
        for name, digest in HEADERS.items():
            source = subprocess.check_output(['git', 'show', PREDECESSOR+':'+name], cwd=root)
            if hashlib.sha256(source).hexdigest() != digest:
                raise ValueError('retained_header_changed:'+name)
            target = work/name; target.parent.mkdir(parents=True, exist_ok=True);target.write_bytes(source)
        (work/'runner.cpp').write_text(RUNNER)
        subprocess.run(['cc','-std=c99','-O1','-I'+str(cjson),'-c',str(cjson/'cJSON.c'),'-o',str(work/'cjson.o')],check=True)
        subprocess.run(['g++','-std=c++17','-O1','-Wall','-Wextra','-Werror','-I'+str(work/'src'),'-I'+str(cjson),str(work/'runner.cpp'),str(work/'cjson.o'),'-o',str(work/'check')],check=True)
        subprocess.run([str(work/'check'),str(Path(manifest_path).resolve())],check=True)
    return {'result':'PASS','predecessor_source':PREDECESSOR,'retained_headers':HEADERS,
            'candidate':manifest['version'],'source_commit':manifest['source_commit'],
            'manifest_sha256':hashlib.sha256(raw).hexdigest(),'firmware_sha256':manifest['sha256'],
            'cjson_sha256':hashlib.sha256((cjson/'cJSON.c').read_bytes()).hexdigest(),
            'release_positions_tested':12,'network_used':False,'physical_update_tested':False}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest',type=Path);parser.add_argument('image',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    report=verify(Path(__file__).resolve().parents[1],args.manifest,args.image)
    encoded=json.dumps(report,indent=2)+'\n'
    if args.output:args.output.write_text(encoded)
    print(encoded)
