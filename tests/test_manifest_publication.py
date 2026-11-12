import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication', ROOT / 'scripts/validate_manifest_publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def test_committed_schema(self):
        publication.validate_manifest(json.loads((ROOT / 'latest/macos-latest.json').read_text()))

    def test_invalid_schema(self):
        for key, value in [('manifest_version', True), ('runner_label', 'ubuntu-latest'), ('sdks', {}), ('observed_at', 'invalid')]:
            manifest = json.loads((ROOT / 'latest/macos-latest.json').read_text())
            manifest[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                publication.validate_manifest(manifest)

    def test_pr_guard(self):
        repo = {'full_name': 'mitchins/xcode-runner-watch'}
        pr = dict(state='open', draft=False, base=dict(ref='main', repo=repo),
                  head=dict(ref='bot/macos-latest-manifest', repo=repo, sha='expected'),
                  user=dict(login='github-actions[bot]'), changed_files=1)
        files = [dict(filename='latest/macos-latest.json', status='modified')]
        publication.validate_pr(pr, files, repo['full_name'], 'expected')
        for field, value in [('draft', True), ('changed_files', 2), ('head', dict(pr['head'], sha='raced')),
                             ('user', dict(login='someone')), ('base', dict(pr['base'], ref='other'))]:
            altered = copy.deepcopy(pr)
            altered[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                publication.validate_pr(altered, files, repo['full_name'], 'expected')
        for altered in [[], files * 2, [dict(filename='README.md', status='modified')],
                        [dict(filename='latest/macos-latest.json', status='removed')]]:
            with self.assertRaises(ValueError):
                publication.validate_pr(pr, altered, repo['full_name'], 'expected')

    def test_version_two_sdk_schema(self):
        manifest = json.loads((ROOT / 'latest/macos-latest.json').read_text())
        manifest['manifest_version'] = 2
        manifest['sdks'] = {name: dict(version=version, build=None)
                            for name, version in manifest['sdks'].items()}
        publication.validate_manifest(manifest)
        manifest['sdks']['iphoneos']['build'] = 123
        with self.assertRaises(ValueError):
            publication.validate_manifest(manifest)

    def test_health_is_separate_and_requires_current_date(self):
        import tempfile
        from datetime import datetime, timezone
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'health.txt'
            path.write_text(datetime.now(timezone.utc).strftime('%Y-%m-%d\n'))
            publication.validate_document(path, 'health')
            path.write_text('2020-01-01\n')
            with self.assertRaises(ValueError):
                publication.validate_document(path, 'health')
        repo = {'full_name': 'mitchins/xcode-runner-watch'}
        pr = dict(state='open', draft=False, base=dict(ref='main', sha='base', repo=repo),
                  head=dict(ref='bot/macos-latest-health', repo=repo, sha='head'),
                  user=dict(login='github-actions[bot]'), changed_files=1)
        files = [dict(filename='latest/last-successful-health.txt', status='added')]
        publication.validate_pr(pr, files, repo['full_name'], 'head', 'health', 'base')
        for kind, base in [('manifest', 'base'), ('health', 'advanced')]:
            with self.assertRaises(ValueError):
                publication.validate_pr(pr, files, repo['full_name'], 'head', kind, base)
        for altered in [files + [dict(filename='latest/macos-latest.json', status='modified')],
                        [dict(files[0], previous_filename='README.md')]]:
            with self.assertRaises(ValueError):
                publication.validate_pr(pr, altered, repo['full_name'], 'head', 'health', 'base')


if __name__ == '__main__':
    unittest.main()
