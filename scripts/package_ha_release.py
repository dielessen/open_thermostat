"""Package a clean Home Assistant integration commit; never includes firmware or HA storage."""
from pathlib import Path
import argparse
import ast
import hashlib
import json
import subprocess
import xml.etree.ElementTree as ET
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def native_summary(path):
    tree = ET.parse(path).getroot()
    suites = [tree] if tree.tag == 'testsuite' else list(tree.iter('testsuite'))
    counts=[{key:int(s.get(key,0)) for key in ('tests','failures','errors','skipped')} for s in suites]
    if not counts or any(value<0 for row in counts for value in row.values()):
        raise ValueError('native_HA_suite_not_passed')
    result = {key:sum(row[key] for row in counts) for key in ('tests','failures','errors','skipped')}
    if result['tests'] <= result['skipped'] or result['failures'] or result['errors']:
        raise ValueError('native_HA_suite_not_passed')
    return result


def native_evidence(path, root, head):
    from ha_test_evidence import snapshot
    properties={}
    for prop in ET.parse(path).getroot().iter('property'):
        name=prop.get('name','')
        if not name.startswith('opth.'):continue
        if name in properties:raise ValueError('native_HA_duplicate_source_evidence')
        properties[name]=prop.get('value')
    current=snapshot(root)
    expected={'opth.source_commit':head,'opth.source_sha256':current['source_sha256'],
              'opth.clean_source':'true','opth.unchanged_source':'true'}
    if not current['clean_source'] or any(properties.get(k)!=v for k,v in expected.items()):
        raise ValueError('native_HA_source_evidence_missing_or_stale')
    product=Path(root)/'ha/config/custom_components/open_thermostat/product.py'
    declarations=[node.value for node in ast.parse(product.read_text()).body
                  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name)
                  and t.id=='SUPPORTED_HA_VERSIONS' for t in node.targets)]
    if len(declarations)!=1:raise ValueError('native_HA_reviewed_core_declaration_invalid')
    reviewed=ast.literal_eval(declarations[0])
    if not isinstance(reviewed,tuple) or properties.get('opth.ha_core') not in reviewed:
        raise ValueError('native_HA_core_not_reviewed')
    return dict(source_commit=head,source_sha256=current['source_sha256'],
                ha_core=properties['opth.ha_core'],clean_source=True,unchanged_source=True,
                junit_sha256=digest(Path(path).read_bytes()))


def verified_archive(archive, files):
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as zip:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zip.writestr(info, data)
    with zipfile.ZipFile(archive) as zip:
        if zip.testzip() is not None or len(zip.namelist())!=len(set(zip.namelist())) or set(zip.namelist()) != set(files):
            raise ValueError('HA_archive_integrity_conflict')
        if any(zip.read(name) != data for name, data in files.items()):
            raise ValueError('HA_archive_payload_conflict')


def package(root, output, results):
    root = Path(root).resolve(); output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise ValueError('release_output_must_be_empty')
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=root):
        raise ValueError('HA_release_requires_clean_source')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    integration = root/'ha/config/custom_components/open_thermostat'
    manifest = json.loads((integration/'manifest.json').read_text())
    version = manifest['version']
    from organize_releases import classify, is_stable
    if manifest['domain'] != 'open_thermostat' or classify('ha-v'+version)[0] != 'ha':
        raise ValueError('invalid_HA_release_identity')
    tests = native_summary(results)
    evidence = native_evidence(results,root,head)
    from zigbee_report_companion import payload as companion_payload
    companion_files,companion_source=companion_payload(root,head)
    files = {}
    for path in sorted(integration.rglob('*')):
        relative = path.relative_to(integration)
        if '__pycache__' in relative.parts or path.suffix in ('.pyc', '.pyo'):
            continue
        if path.is_symlink():
            raise ValueError('HA_release_symlink_not_allowed')
        if not path.is_file():
            continue
        if any(part.startswith('.') for part in relative.parts) or path.suffix.lower() not in ('.py', '.json', '.js', '.css', '.html', '.yaml', '.yml', '.png', '.svg'):
            raise ValueError('unexpected_HA_source_file:'+relative.as_posix())
        files['custom_components/open_thermostat/'+relative.as_posix()] = path.read_bytes()
    tracked = set(subprocess.check_output(['git', 'ls-files', '-z', '--', str(integration.relative_to(root))], cwd=root).decode().split('\0'))
    if any('ha/config/'+name not in tracked for name in files):
        raise ValueError('untracked_HA_release_source')
    source_hashes = {name: digest(data) for name, data in files.items()}
    files['LICENSE'] = (root/'LICENSE').read_bytes()
    files['RELEASE-NOTES.md'] = (root/'docs/modern-thermostat/HA-RELEASE-NOTES.md').read_bytes()
    source = dict(source_commit=head, source_kind='clean_git_commit', integration_version=version,
                  source_files=source_hashes, native_test_summary=tests, native_test_evidence=evidence,
                  firmware_included=False, live_HA_data_included=False)
    files['SOURCE.json'] = (json.dumps(source, indent=2)+'\n').encode()
    files['notices/PLATFORM.txt'] = (b'Project source: MIT; original LICENSE included.\n'
        b'Home Assistant and its platform dependencies are not vendored.\n'
        b'No ESP32 SDK, firmware binary, CA bundle or live HA storage is included.\n'
        b'Firmware source/notice/update and physical acceptance remain separate.\n')
    files['SHA256SUMS.txt'] = ''.join(digest(data)+'  '+name+'\n' for name, data in sorted(files.items())).encode()
    output.mkdir(parents=True, exist_ok=True)
    archive = output/('OpenThermostat-HA-'+version+'.zip')
    verified_archive(archive,files)
    companion_archive=output/("OpenThermostat-Zigbee2MQTT-original-reports-"+version+".zip")
    verified_archive(companion_archive,companion_files)
    companion={**companion_source,"asset":companion_archive.name,
        "sha256":digest(companion_archive.read_bytes()),"size":companion_archive.stat().st_size,
        "archive_payloads_verified":len(companion_files)}
    metadata = dict(version=version, tag='ha-v'+version, source_commit=head, asset=archive.name,
                    sha256=digest(archive.read_bytes()), size=archive.stat().st_size,
                    integration_source_files=source_hashes, native_test_summary=tests, native_test_evidence=evidence,
                    firmware_included=False, prerelease=not is_stable(*classify('ha-v'+version)),
                    optional_companions=[companion])  # ha-v1.0.0 is a normal release, 1.0.0b1 a pre-release
    (output/'ha-release.json').write_text(json.dumps(metadata, indent=2)+'\n')
    report = dict(status='PASS_PACKAGE_INTEGRITY_ONLY', source_commit=head, integration_version=version,
                  integration_source_files=len(source_hashes), native_test_summary=tests, native_test_evidence=evidence,
                  archive_payloads_verified=len(files), optional_companions=[companion], firmware_included=False,
                  live_HA_data_included=False, physical_heating_approval=False)
    (output/'ha-software-verification.json').write_text(json.dumps(report, indent=2)+'\n')
    (output/'HA-SHA256SUMS.txt').write_text(''.join(digest(path.read_bytes())+'  '+path.name+'\n'
        for path in sorted(output.iterdir()) if path.name != 'HA-SHA256SUMS.txt'))
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-results', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package(Path(__file__).resolve().parents[1], args.output, args.native_results), indent=2))
