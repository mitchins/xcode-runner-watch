#!/usr/bin/env python3
"""Fail closed before merging a captured manifest through normal repository rules."""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def validate_manifest(value):
    def fields(obj, shape):
        if not isinstance(obj, dict) or set(obj) != set(shape):
            raise ValueError('Unexpected manifest fields')
        for key, kind in shape.items():
            if not isinstance(obj[key], kind):
                raise ValueError(f'Invalid type for {key}')

    fields(value, dict(manifest_version=int, observed_at=str, runner_label=str,
                       system=dict, xcode=dict, swift=dict, sdks=dict, simulators=dict))
    if type(value['manifest_version']) is not int or value['manifest_version'] not in (1, 2):
        raise ValueError('Unsupported manifest version')
    if value['runner_label'] != 'macos-latest':
        raise ValueError('Unexpected runner')
    datetime.strptime(value['observed_at'], '%Y-%m-%dT%H:%M:%SZ')
    fields(value['system'], dict(product_name=str, product_version=str, build_version=str, uname=str))
    fields(value['xcode'], dict(selected_path=str, xcodebuild_version=dict))
    fields(value['xcode']['xcodebuild_version'], dict(raw=str, xcode=(str, type(None)), build=(str, type(None))))
    fields(value['swift'], dict(swift_version=dict))
    fields(value['swift']['swift_version'], dict(raw=str, version=(str, type(None)), target=(str, type(None))))
    if value['manifest_version'] == 1:
        fields(value['sdks'], dict(iphoneos=str, iphonesimulator=str, macosx=str))
    else:
        fields(value['sdks'], dict(iphoneos=dict, iphonesimulator=dict, macosx=dict))
        for sdk in value['sdks'].values():
            fields(sdk, dict(version=str, build=(str, type(None))))
    fields(value['simulators'], dict(runtimes=dict, device_types=dict, devices_available=dict))
    fields(value['simulators']['runtimes'], dict(runtimes=list))
    fields(value['simulators']['device_types'], dict(devicetypes=list))
    for devices in value['simulators']['devices_available'].values():
        if not isinstance(devices, list):
            raise ValueError('Invalid devices')
        for device in devices:
            fields(device, dict(name=(str, type(None)), deviceTypeIdentifier=(str, type(None)), isAvailable=(bool, type(None))))


PUBLICATIONS = {
    'manifest': ('latest/macos-latest.json', 'bot/macos-latest-manifest'),
    'health': ('latest/last-successful-health.txt', 'bot/macos-latest-health'),
}


def validate_document(path, kind):
    if kind == 'manifest':
        validate_manifest(json.loads(path.read_text()))
    elif kind == 'health':
        if path.read_text() != datetime.now(timezone.utc).strftime('%Y-%m-%d\n'):
            raise ValueError('Health publication must record today in UTC')
    else:
        raise ValueError('Unexpected publication kind')


def validate_pr(pr, files, repo, head, kind='manifest', base=None):
    expected_path, expected_branch = PUBLICATIONS[kind]
    if (pr['state'] != 'open' or pr['draft'] or pr['base']['ref'] != 'main'
            or pr['base']['repo']['full_name'] != repo
            or pr['head']['ref'] != expected_branch
            or pr['head']['repo']['full_name'] != repo or pr['head']['sha'] != head
            or pr['user']['login'] != 'github-actions[bot]' or pr['changed_files'] != 1
            or (base is not None and pr['base']['sha'] != base)):
        raise ValueError('Unexpected publication PR identity or head')
    if (len(files) != 1 or files[0]['filename'] != expected_path
            or files[0]['status'] not in ('modified', 'added')
            or 'previous_filename' in files[0]):
        raise ValueError('Publication must change only its expected document')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('path', type=Path)
    parser.add_argument('pr_number', nargs='?')
    parser.add_argument('head', nargs='?')
    parser.add_argument('--kind', choices=PUBLICATIONS, default='manifest')
    parser.add_argument('--base')
    args = parser.parse_args()
    path, kind = args.path, args.kind
    validate_document(path, kind)
    if args.pr_number is None:
        return
    if not args.head:
        parser.error('PR validation requires an exact head')
    pr_number, head, base = args.pr_number, args.head, args.base
    repo = os.environ['GITHUB_REPOSITORY']

    def api(endpoint):
        return json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/{endpoint}']))

    validate_pr(api(f'pulls/{pr_number}'), api(f'pulls/{pr_number}/files?per_page=100'), repo, head, kind, base)
    committed = subprocess.check_output(['git', 'show', f'{head}:{PUBLICATIONS[kind][0]}'])
    if committed != path.read_bytes():
        raise ValueError('PR manifest differs from validated capture')


if __name__ == '__main__':
    main()
