"""Preserve validated private Z2M pins between two verified public templates.

Offline artifact preparation only. Never executes JavaScript, installs an
extension, modifies the inputs, prints pins or grants control qualification.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import stat

MAX_BYTES=32768
DECLARATION=re.compile(rb'^const DEVICE_BINDINGS = Object\.freeze\((\[[\s\S]*?\])\);$',re.MULTILINE)
PROFILES=('original_temperature','original_tv02')


def digest(value):
    return hashlib.sha256(value).hexdigest()


def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('duplicate_pin_field')
        result[key]=value
    return result


def inspect_template(raw, profile):
    if profile not in PROFILES or not isinstance(raw,bytes) or not 0<len(raw)<=MAX_BYTES:
        raise ValueError('invalid_producer_template')
    marker=b'module.exports = class '+(b'OpenThermostatOriginalTv02' if profile=='original_tv02' else b'OpenThermostatOriginalTemperature')+b' {'
    if raw.count(marker)!=1:raise ValueError('producer_profile_does_not_match_source')
    matches=list(DECLARATION.finditer(raw))
    if len(matches)!=1:raise ValueError('ambiguous_pin_declaration')
    match=matches[0]
    try:pins=json.loads(match[1],object_pairs_hook=unique_object)
    except (UnicodeError,json.JSONDecodeError) as error:raise ValueError('pins_are_not_JSON_data') from error
    if type(pins) is not list or len(pins)>64:raise ValueError('invalid_pin_count')
    seen=set()
    for pin in pins:
        keys={'ieee','model'} | ({'manufacturer','endpoint'} if profile=='original_tv02' else set())
        if type(pin) is not dict or pin.keys()!=keys:raise ValueError('invalid_pin_fields')
        ieee=pin['ieee']
        if type(ieee) is not str or not re.fullmatch(r'0x[0-9a-f]{16}',ieee) or ieee in seen:
            raise ValueError('invalid_or_duplicate_pin_identity')
        seen.add(ieee)
        if pin['model']!=('TV02-Zigbee' if profile=='original_tv02' else 'WSDCGQ11LM'):
            raise ValueError('unsupported_pin_model')
        if profile=='original_tv02' and (pin['manufacturer'] not in ('_TZE200_hue3yfsn','_TZE200_lllliz3p')
                or type(pin['endpoint']) is not int or not 1<=pin['endpoint']<=240):
            raise ValueError('unsupported_pin_fingerprint')
    normalized=raw[:match.start(1)]+b'[]'+raw[match.end(1):]
    return pins,normalized,match


def prepare(previous, installed, candidate, profile, *, expected_previous, expected_installed, expected_candidate):
    for raw,expected in [(previous,expected_previous),(installed,expected_installed),(candidate,expected_candidate)]:
        if type(expected) is not str or not re.fullmatch('[0-9a-f]{64}',expected) or digest(raw)!=expected:
            raise ValueError('source_hash_mismatch')
    old_pins,old_public,_=inspect_template(previous,profile)
    pins,installed_public,_=inspect_template(installed,profile)
    new_pins,new_public,match=inspect_template(candidate,profile)
    if old_pins or new_pins:raise ValueError('public_templates_must_have_empty_pins')
    if installed_public!=old_public:raise ValueError('installed_code_differs_outside_private_pins')
    encoded=json.dumps(pins,ensure_ascii=True,separators=(',',':')).encode()
    output=candidate[:match.start(1)]+encoded+candidate[match.end(1):]
    checked,normalized,_=inspect_template(output,profile)
    if checked!=pins or normalized!=new_public:raise ValueError('prepared_source_readback_conflict')
    return output,dict(schema=1,profile=profile,source_kind='offline_prepared_private_pins',
        previous_template_sha256=expected_previous,installed_source_sha256=expected_installed,
        candidate_template_sha256=expected_candidate,prepared_source_sha256=digest(output),
        preserved_pin_count=len(pins),installed=False,authorizes_control=False)


def bounded_read(path):
    # Linux/POSIX private staging only. NONBLOCK prevents opening a FIFO from
    # blocking before we can reject it; regular files ignore this flag.
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as source:
        before=os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode):raise ValueError('producer_source_must_be_regular')
        if before.st_size>MAX_BYTES:raise ValueError('producer_source_too_large')
        raw=source.read(MAX_BYTES+1)
        after=os.fstat(source.fileno())
        if (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns)!=(after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns):
            raise ValueError('producer_source_changed_during_read')
    if len(raw)>MAX_BYTES:raise ValueError('producer_source_too_large')
    return raw


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--previous-template',type=Path,required=True)
    parser.add_argument('--installed-source',type=Path,required=True)
    parser.add_argument('--candidate-template',type=Path,required=True)
    parser.add_argument('--expected-previous-sha256',required=True)
    parser.add_argument('--expected-installed-sha256',required=True)
    parser.add_argument('--expected-candidate-sha256',required=True)
    parser.add_argument('--profile',choices=PROFILES,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if not hasattr(os,'O_NOFOLLOW') or not hasattr(os,'O_NONBLOCK'):
        parser.error('Use the existing Linux/POSIX administration workspace for private staging')
    output,report=prepare(bounded_read(args.previous_template),bounded_read(args.installed_source),
        bounded_read(args.candidate_template),args.profile,expected_previous=args.expected_previous_sha256,
        expected_installed=args.expected_installed_sha256,expected_candidate=args.expected_candidate_sha256)
    # New private artifact only, never overwrite/replace a running extension.
    fd=os.open(args.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,'wb') as target:target.write(output)
        if bounded_read(args.output)!=output:raise ValueError('private_artifact_readback_failed')
    except BaseException:
        args.output.unlink(missing_ok=True)
        raise
    print(json.dumps(report))
