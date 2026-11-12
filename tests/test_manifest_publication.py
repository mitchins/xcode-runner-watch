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
        pr = dict(state='open', draft=False, base=dict(ref='main', sha='base', repo=repo),
                  head=dict(ref='bot/macos-latest-manifest', repo=repo, sha='expected'),
                  user=dict(login='github-actions[bot]'), changed_files=1)
        files = [dict(filename='latest/macos-latest.json', status='modified')]
        publication.validate_pr(pr, files, repo['full_name'], 'expected', 'base')
        with self.assertRaises(ValueError):
            publication.validate_pr(pr, files, repo['full_name'], 'expected', 'advanced-base')
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


if __name__ == '__main__':
    unittest.main()
