#!/usr/bin/env python3
"""Fail closed before merging a captured manifest through normal repository rules."""
import json
import os
import subprocess
import sys
from datetime import datetime
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
    if type(value['manifest_version']) is not int or value['manifest_version'] != 1:
        raise ValueError('Unsupported manifest version')
    if value['runner_label'] != 'macos-latest':
        raise ValueError('Unexpected runner')
    datetime.strptime(value['observed_at'], '%Y-%m-%dT%H:%M:%SZ')
    fields(value['system'], dict(product_name=str, product_version=str, build_version=str, uname=str))
    fields(value['xcode'], dict(selected_path=str, xcodebuild_version=dict))
    fields(value['xcode']['xcodebuild_version'], dict(raw=str, xcode=(str, type(None)), build=(str, type(None))))
    fields(value['swift'], dict(swift_version=dict))
    fields(value['swift']['swift_version'], dict(raw=str, version=(str, type(None)), target=(str, type(None))))
    fields(value['sdks'], dict(iphoneos=str, iphonesimulator=str, macosx=str))
    fields(value['simulators'], dict(runtimes=dict, device_types=dict, devices_available=dict))
    fields(value['simulators']['runtimes'], dict(runtimes=list))
    fields(value['simulators']['device_types'], dict(devicetypes=list))
    for devices in value['simulators']['devices_available'].values():
        if not isinstance(devices, list):
            raise ValueError('Invalid devices')
        for device in devices:
            fields(device, dict(name=(str, type(None)), deviceTypeIdentifier=(str, type(None)), isAvailable=(bool, type(None))))


def validate_pr(pr, files, repo, head, base=None):
    if (pr['state'] != 'open' or pr['draft'] or pr['base']['ref'] != 'main'
            or pr['base']['repo']['full_name'] != repo
            or pr['head']['ref'] != 'bot/macos-latest-manifest'
            or pr['head']['repo']['full_name'] != repo or pr['head']['sha'] != head
            or pr['user']['login'] != 'github-actions[bot]' or pr['changed_files'] != 1
            or (base is not None and pr['base']['sha'] != base)):
        raise ValueError('Unexpected publication PR identity or head')
    if len(files) != 1 or files[0]['filename'] != 'latest/macos-latest.json' or files[0]['status'] != 'modified':
        raise ValueError('Publication must modify only the manifest')


def main():
    path = Path(sys.argv[1])
    validate_manifest(json.loads(path.read_text()))
    if len(sys.argv) == 2:
        return
    pr_number, head = sys.argv[2:4]
    base = sys.argv[4] if len(sys.argv) > 4 else None
    repo = os.environ['GITHUB_REPOSITORY']

    def api(endpoint):
        return json.loads(subprocess.check_output(['gh', 'api', f'repos/{repo}/{endpoint}']))

    validate_pr(api(f'pulls/{pr_number}'), api(f'pulls/{pr_number}/files?per_page=100'), repo, head, base)
    committed = subprocess.check_output(['git', 'show', f'{head}:latest/macos-latest.json'])
    if committed != path.read_bytes():
        raise ValueError('PR manifest differs from validated capture')


if __name__ == '__main__':
    main()
