"""Exercise the receipt-bound accepted updater against an actual candidate image.

Retained Git source is compiled unchanged. HTTP and flash are host fixtures;
this neither installs firmware nor accepts a physical update or successor release.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import tempfile

from verify_e32_update_gate import POLICY, verify as verify_gate, version

RETAINED = ('src/update/ReleasePolicy.h', 'src/update/ReleaseCatalog.h',
            'src/update/IndexedReleaseCatalog.h', 'src/update/VerifiedOta.h',
            'src/control/BoundedJson.h', 'test/updates/image_check.cpp')
RUNNER = r'''
#include "update/IndexedReleaseCatalog.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace heating::update;
int main(int argc,char**argv) {
    if(argc!=3)return 1;
    std::ifstream input(argv[1]);
    std::string bytes((std::istreambuf_iterator<char>(input)),{});
    auto doc=releaseJson(bytes);if(!doc)return 2;
    if(maxReleasePages!=12)return 8;
    const auto tag=string(doc.get(),"version");Manifest manifest;
    if(!parseManifest(bytes,tag,manifest))return 3;
    const auto refs="[{\"ref\":\"refs/tags/"+tag+"\",\"object\":{\"type\":\"commit\",\"sha\":\""+manifest.source+"\"}}]";
    // As published: a stable tag (vX.Y.Z-e32v2) is a normal release, every other tag a pre-release.
    const bool preview=tag.find("-e32v2-")!=std::string::npos;
    const auto entry="{\"tag_name\":\""+tag+"\",\"draft\":false,\"prerelease\":"+std::string(preview?"true":"false")+",\"published_at\":\"2026-10-26T00:00:00Z\",\"assets\":[{\"name\":\"e32v2-update.json\"},{\"name\":\"firmware.bin\"}]}";
    // Actual accepted fast path: a matching tag, public release and manifest.
    // Failures must retain the old choices rather than publish a partial list.
    for(int mode=0;mode<3;++mode) {
        std::vector<Release> choices{{"previous",false}};std::string error;
        unsigned calls=0;
        auto fetch=[&](const std::string&url,size_t limit,std::string&out,std::string&,int&status) {
            ++calls;status=200;
            if(url==releaseReferenceApi) {
                out=refs;
                if(mode==2)out.replace(out.find(manifest.source),40,std::string(40,manifest.source[0]=='a'?'b':'a'));
            } else if(url==std::string(releaseApi)+"/tags/"+tag)out=entry;
            else if(url==assetUrl(tag,"e32v2-update.json")) {if(mode==1)return false;out=bytes;}
            else return false;
            return out.size()<=limit;
        };
        const auto result=discoverIndexedReleases(fetch,choices,error);
        if(calls!=3)return 4;
        if(mode==0) {
            if(result!=IndexedCatalogResult::Complete||choices.size()!=1||choices[0].tag!=tag
                ||choices[0].prerelease!=preview||newerFirmwareRelease(argv[2],choices)!=tag)return 5;
        } else if(result!=IndexedCatalogResult::Failed||choices.size()!=1||choices[0].tag!="previous")return 6;
    }
    // General discovery still works in every bounded release-list position.
    for(unsigned position=1;position<=maxReleasePages;++position) {
        std::vector<Release> choices{{"previous",false}};std::string error;unsigned calls=0;
        auto fetch=[&](const std::string&url,size_t limit,std::string&out,std::string&) {
            ++calls;
            if(url==assetUrl(tag,"e32v2-update.json"))out=bytes;
            else {
                unsigned page=1;while(page<=maxReleasePages&&url!=releasePageUrl(page))++page;
                if(page>maxReleasePages)return false;
                out=page==position?"["+entry+"]":"[{\"tag_name\":\"ha-v0.4.0b3\",\"draft\":false}]";
            }
            return out.size()<=limit;
        };
        if(!discoverReleases(fetch,choices,error)||calls!=13||choices.size()!=1||choices[0].tag!=tag)return 7;
    }
    std::cout<<"PASS: accepted updater fast path, failed-fetch/source-mismatch preservation and 12 fallback positions\n";
}
'''


def accepted_source(root):
    root = Path(root).resolve()
    policy = json.loads((root / POLICY).read_text())
    verify_gate(root, policy)
    if policy['accepted'] is None:
        raise ValueError('accepted_update_receipt_required')
    receipt = root / policy['accepted']['receipt']
    record = json.loads(receipt.read_text())
    if version(record['tag'])[3] < 1:
        raise ValueError('accepted_beta_or_later_required')
    return record, hashlib.sha256(receipt.read_bytes()).hexdigest()


def verify(root, manifest_path, image_path):
    root = Path(root).resolve()
    accepted, receipt_sha = accepted_source(root)
    raw = Path(manifest_path).read_bytes()
    manifest = json.loads(raw)
    target = version(manifest['version'])
    if target is None or target <= version(accepted['tag']):
        raise ValueError('candidate_must_be_newer_than_accepted')
    image = Path(image_path).read_bytes()
    marker = f'OT_E32V2_OTA_V1:{manifest["version"]}:{manifest["source_commit"]}:{manifest["web_sha256"]}:END'.encode()
    if len(image) != manifest['size'] or hashlib.sha256(image).hexdigest() != manifest['sha256'] or marker not in image:
        raise ValueError('candidate_image_identity_mismatch')
    cjson = root / '.pio/libdeps/native/cJSON'
    retained = {}
    with tempfile.TemporaryDirectory(prefix='ot-accepted-updater-') as temp:
        work = Path(temp)
        for name in RETAINED:
            # No current-header fallback: missing retained source stops packaging.
            data = subprocess.check_output(['git', 'show', accepted['source_commit'] + ':' + name], cwd=root)
            retained[name] = hashlib.sha256(data).hexdigest()
            path = work / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (work / 'catalog.cpp').write_text(RUNNER)
        subprocess.run(['cc', '-std=c99', '-O1', '-I'+str(cjson), '-c', str(cjson/'cJSON.c'), '-o', str(work/'cjson.o')], check=True)
        common = ['g++', '-std=c++20', '-O1',
                  '-I'+str(work/'src'), '-I'+str(cjson)]
        subprocess.run(common + ['-Wall', '-Wextra', '-Werror', str(work/'catalog.cpp'), str(work/'cjson.o'), '-o', str(work/'catalog')], check=True)
        subprocess.run([str(work/'catalog'), str(Path(manifest_path).resolve()), accepted['tag']], check=True)
        # The image harness and production commit gate both come from the same
        # accepted commit. OpenSSL checks hashes; flash/boot remain host fakes.
        subprocess.run(common + [str(work/'test/updates/image_check.cpp'), str(work/'cjson.o'),
                                '-l:libcrypto.so.3', '-o', str(work/'image-check')], check=True)
        checked = subprocess.run([str(work/'image-check'), str(Path(manifest_path).resolve()), str(Path(image_path).resolve())],
                                 check=True, capture_output=True, text=True)
        print(checked.stdout, end='')
        match = re.search(r'^(\d+) actual-image production-gate/OpenSSL scenarios PASS', checked.stdout, re.M)
        if not match or int(match[1]) < 5:
            raise ValueError('accepted_image_gate_coverage_missing')
        image_cases = int(match[1])
    return {'result': 'PASS', 'accepted_tag': accepted['tag'], 'accepted_source': accepted['source_commit'],
            'acceptance_receipt_sha256': receipt_sha, 'retained_sources': retained,
            'candidate': manifest['version'], 'source_commit': manifest['source_commit'],
            'manifest_sha256': hashlib.sha256(raw).hexdigest(), 'firmware_sha256': manifest['sha256'],
            'cjson_sha256': hashlib.sha256((cjson/'cJSON.c').read_bytes()).hexdigest(),
            'indexed_catalog_cases': 3, 'fallback_positions_tested': 12, 'image_commit_gate_cases': image_cases,
            'network_used': False, 'physical_update_tested': False, 'successor_publication_approved': False}


def verify_report(root, report, manifest_path, source_root=None):
    """Check a delivered report against the packaged receipt and exact payload."""
    accepted, receipt_sha = accepted_source(root)
    raw = Path(manifest_path).read_bytes()
    manifest = json.loads(raw)
    if version(manifest['version']) is None or version(manifest['version']) <= version(accepted['tag']):
        raise ValueError('candidate_must_be_newer_than_accepted')
    expected = {'result': 'PASS', 'accepted_tag': accepted['tag'], 'accepted_source': accepted['source_commit'],
                'acceptance_receipt_sha256': receipt_sha, 'candidate': manifest['version'],
                'source_commit': manifest['source_commit'], 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
                'firmware_sha256': manifest['sha256'], 'indexed_catalog_cases': 3,
                'fallback_positions_tested': 12,
                'network_used': False, 'physical_update_tested': False, 'successor_publication_approved': False}
    if any(type(report.get(key)) is not type(value) or report[key] != value for key,value in expected.items()):
        raise ValueError('accepted_updater_report_identity_or_scope_mismatch')
    if type(report.get('image_commit_gate_cases')) is not int or report['image_commit_gate_cases'] < 5:
        raise ValueError('accepted_updater_report_identity_or_scope_mismatch')
    sources = report.get('retained_sources', {})
    if not isinstance(sources,dict) or set(sources) != set(RETAINED) or any(not isinstance(value,str) or not re.fullmatch('[0-9a-f]{64}',value)
                                          for value in list(sources.values())+[report.get('cjson_sha256')]):
        raise ValueError('accepted_updater_retained_sources_missing')
    if source_root is not None:
        for name in RETAINED:
            data = subprocess.check_output(['git','show',accepted['source_commit']+':'+name],cwd=source_root)
            if hashlib.sha256(data).hexdigest() != sources[name]:
                raise ValueError('accepted_updater_retained_source_mismatch')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(Path(__file__).resolve().parents[1], args.manifest, args.image)
    encoded = json.dumps(result, indent=2)+'\n'
    if args.output:
        args.output.write_text(encoded)
    print(encoded)
