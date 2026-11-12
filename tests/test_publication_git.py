"""Exercise the publisher with real local Git and a small GitHub API stand-in."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
FAKE_GH = r'''#!/usr/bin/env python3
import json, os, subprocess, sys, tempfile
from pathlib import Path
args = sys.argv[1:]
remote = os.environ['TEST_REMOTE']

def git(*args, cwd=None):
    return subprocess.check_output(['git', *args], cwd=cwd, stderr=subprocess.DEVNULL).decode().strip()

def ref(name):
    return git('--git-dir', remote, 'rev-parse', name)

branch = git('branch', '--show-current')
if args[:2] == ['auth', 'setup-git']:
    if os.environ.get('TEST_RACE') == 'branch':
        # Another writer changes the remote after checkout fetched its tracking ref.
        subprocess.check_call(['git', '--git-dir', remote, 'update-ref', 'refs/heads/' + branch, ref('refs/heads/main')])
    sys.exit(0)
if args[:2] == ['pr', 'list']:
    sys.exit(0)
if args[:2] == ['pr', 'create']:
    print('https://github.com/test/repo/pull/10')
    sys.exit(0)
if args[0] == 'api':
    if '--method' in args:
        wanted = next(x[4:] for x in args if x.startswith('sha='))
        if os.environ.get('TEST_RACE') == 'head-after-validation':
            subprocess.check_call(['git', '--git-dir', remote, 'update-ref', 'refs/heads/' + branch, ref('refs/heads/main')])
        if wanted != ref('refs/heads/' + branch):
            sys.exit('Head SHA changed; refusing merge')
        with tempfile.TemporaryDirectory() as tmp:
            git('clone', '--branch', 'main', remote, tmp)
            git('config', 'user.name', 'test', cwd=tmp)
            git('config', 'user.email', 'test@example.invalid', cwd=tmp)
            git('merge', '--squash', 'origin/' + branch, cwd=tmp)
            git('commit', '-m', 'Squash publication', cwd=tmp)
            git('push', 'origin', 'main', cwd=tmp)
            print(ref('refs/heads/main'))
        sys.exit(0)
    if '/files?' in args[1]:
        lines = git('--git-dir', remote, 'diff', '--name-status', 'main...' + branch).splitlines()
        print(json.dumps([dict(filename=line.split('\t')[-1], status={'M':'modified','A':'added'}.get(line[0], 'removed')) for line in lines]))
    else:
        if os.environ.get('TEST_RACE') == 'main':
            with tempfile.TemporaryDirectory() as tmp:
                git('clone', '--branch', 'main', remote, tmp)
                git('config', 'user.name', 'test', cwd=tmp)
                git('config', 'user.email', 'test@example.invalid', cwd=tmp)
                Path(tmp, 'concurrent-main.txt').write_text('Concurrent main advancement')
                git('add', '.', cwd=tmp)
                git('commit', '-m', 'Concurrent main advancement', cwd=tmp)
                git('push', 'origin', 'main', cwd=tmp)
        base = ref('refs/heads/main')
        print(json.dumps(dict(state='open', draft=False, changed_files=1,
            base=dict(ref='main', sha=base, repo=dict(full_name='test/repo')),
            head=dict(ref=branch, sha=ref('refs/heads/' + branch), repo=dict(full_name='test/repo')),
            user=dict(login='github-actions[bot]'))))
    sys.exit(0)
sys.exit('Unexpected gh call: ' + repr(args))
'''


class PublicationGitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.remote = self.root / 'remote.git'
        self.work = self.root / 'work'
        self.run_git('init', '--bare', str(self.remote), cwd=self.root)
        self.run_git('clone', str(self.remote), str(self.work), cwd=self.root)
        self.run_git('checkout', '-b', 'main')
        self.run_git('config', 'user.name', 'test')
        self.run_git('config', 'user.email', 'test@example.invalid')
        for directory in ['scripts', 'latest']:
            (self.work / directory).mkdir()
        for name in ['publish_runner_update.sh', 'validate_manifest_publication.py']:
            shutil.copy(ROOT / 'scripts' / name, self.work / 'scripts' / name)
        shutil.copy(ROOT / 'latest/macos-latest.json', self.work / 'latest/macos-latest.json')
        self.run_git('add', '.')
        self.run_git('commit', '-m', 'Initial main')
        self.run_git('push', '-u', 'origin', 'main')
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        (self.bin / 'gh').write_text(FAKE_GH)
        (self.bin / 'gh').chmod(0o755)
        self.env = {**os.environ, 'PATH': str(self.bin) + os.pathsep + os.environ['PATH'],
                    'GITHUB_REPOSITORY': 'test/repo', 'TEST_REMOTE': str(self.remote)}

    def run_git(self, *args, cwd=None):
        return subprocess.check_output(['git', *args], cwd=cwd or self.work, stderr=subprocess.DEVNULL).decode().strip()

    def change_manifest(self, version):
        path = self.work / 'latest/macos-latest.json'
        value = json.loads(path.read_text())
        value['system']['product_version'] = version
        path.write_text(json.dumps(value, indent=2) + '\n')

    def publish(self, kind='manifest', race=None):
        env = {**self.env, **({'TEST_RACE': race} if race else {})}
        return subprocess.run(['bash', 'scripts/publish_runner_update.sh', kind], cwd=self.work,
                              env=env, capture_output=True, text=True)

    def test_repeated_capture_after_squash_and_independent_health(self):
        self.change_manifest('first')
        health = self.work / 'latest/last-successful-health.txt'
        health.write_text(datetime.now(timezone.utc).strftime('%Y-%m-%d\n'))
        first = self.publish()
        self.assertEqual(first.returncode, 0, first.stderr)
        # The next publisher must start at newly advanced main, not the pre-squash branch.
        second = self.publish('health')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.run_git('diff', '--name-only', 'HEAD^', 'HEAD'), 'latest/last-successful-health.txt')
        self.change_manifest('second')
        repeated = self.publish()
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn('second', self.run_git('--git-dir', str(self.remote), 'show', 'main:latest/macos-latest.json'))
        quiet = self.publish()
        self.assertEqual(quiet.returncode, 0, quiet.stderr)
        self.assertEqual(quiet.stdout, '')

    def test_concurrent_bot_branch_change_rejects_stale_lease(self):
        self.change_manifest('first')
        self.assertEqual(self.publish().returncode, 0)
        original_main = self.run_git('--git-dir', str(self.remote), 'rev-parse', 'main')
        self.change_manifest('second')
        result = self.publish(race='branch')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('stale info', result.stderr)
        self.assertEqual(self.run_git('--git-dir', str(self.remote), 'rev-parse', 'main'), original_main)

    def test_main_advancement_and_late_head_change_refuse_merge(self):
        for race, message in [('main', 'Unexpected publication PR'), ('head-after-validation', 'Head SHA changed')]:
            with self.subTest(race=race):
                self.run_git('reset', '--hard', 'origin/main')
                self.change_manifest(race)
                original = self.run_git('--git-dir', str(self.remote), 'rev-parse', 'main')
                result = self.publish(race=race)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(message, result.stderr)
                published = self.run_git('--git-dir', str(self.remote), 'show', 'main:latest/macos-latest.json')
                self.assertNotIn(race, published)
                if race == 'head-after-validation':
                    self.assertEqual(self.run_git('--git-dir', str(self.remote), 'rev-parse', 'main'), original)
                self.run_git('fetch', 'origin')
