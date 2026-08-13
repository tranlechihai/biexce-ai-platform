import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / 'src' / 'global'
MANIFEST_PATH = REPOSITORY_ROOT / 'src' / 'harness-manifest.json'
SCHEMA_PATH = REPOSITORY_ROOT / 'src' / 'harness-manifest.schema.json'
CONFIG_PATH = SOURCE_ROOT / 'opencode.json'
EXPECTED_AGENTS = {
    'bx-director', 'bx-plan', 'bx-explore', 'bx-code',
    'bx-fix', 'bx-test', 'bx-review',
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


class HarnessManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding='utf-8'))
        cls.config = json.loads(CONFIG_PATH.read_text(encoding='utf-8'))

    def test_schema_and_generator_are_current(self):
        self.assertEqual(self.manifest['schema_version'], 2)
        self.assertEqual(
            self.manifest['$schema'], './harness-manifest.schema.json'
        )
        self.assertEqual(self.schema['properties']['schema_version']['const'], 2)
        result = subprocess.run(
            [sys.executable, str(REPOSITORY_ROOT / 'scripts' / 'update_manifest.py'), '--check'],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_agent_identity_mode_binding_and_hashes(self):
        agents = self.manifest['agents']
        self.assertEqual({agent['id'] for agent in agents}, EXPECTED_AGENTS)
        self.assertEqual(len({agent['path'] for agent in agents}), 7)
        for agent in agents:
            path = SOURCE_ROOT / agent['path']
            self.assertEqual(sha256(path), agent['sha256'])
            frontmatter = path.read_text(encoding='utf-8').split('---', 2)[1]
            mode = re.search(r'(?m)^mode:\s*(\S+)\s*$', frontmatter)
            model = re.search(r'(?m)^model:\s*(\S+)\s*$', frontmatter)
            self.assertIsNotNone(mode)
            self.assertEqual(mode.group(1), agent['mode'])
            self.assertEqual(model.group(1) if model else None, agent['model'])

    def test_skill_tree_status_and_hashes(self):
        skills = self.manifest['skills']
        source_paths = {
            path.relative_to(SOURCE_ROOT).as_posix()
            for path in (SOURCE_ROOT / 'skills').rglob('SKILL.md')
            if '_TEMPLATE' not in path.parts
        }
        self.assertEqual({skill['path'] for skill in skills}, source_paths)
        self.assertEqual(len({skill['id'] for skill in skills}), len(skills))
        self.assertNotIn('skills/_TEMPLATE/SKILL.md', source_paths)
        for skill in skills:
            self.assertIn(skill['status'], {'skeleton', 'draft', 'ready'})
            self.assertEqual(sha256(SOURCE_ROOT / skill['path']), skill['sha256'])

    def test_runtime_files_are_hash_managed(self):
        runtime_files = self.manifest['runtime_files']
        self.assertEqual(
            {runtime['id'] for runtime in runtime_files},
            {
                'biexce-control-plugin',
                'biexce-failure-policy-runtime',
                'biexce-job-board-runtime',
                'biexce-observability-runtime',
                'biexce-reconciler-runtime',
                'biexce-resilience-runtime',
                'biexce-scheduler-runtime',
                'biexce-scope-policy-runtime',
                'biexce-session-registry-runtime',
                'biexce-supervisor-runtime',
                'biexce-workflow-policy-runtime',
            },
        )
        for runtime in runtime_files:
            self.assertEqual(
                sha256(SOURCE_ROOT / runtime['path']),
                runtime['sha256'],
            )

    def test_manifest_matches_canonical_config(self):
        for name, value in self.manifest['defaults'].items():
            self.assertEqual(self.config[name], value)
        for name, value in self.manifest['model_binding']['global'].items():
            self.assertEqual(self.config.get(name), value)
        binding_values = list(self.manifest['model_binding']['global'].values())
        binding_values += list(self.manifest['model_binding']['agents'].values())
        expected_state = 'bound' if any(binding_values) else 'unset'
        self.assertEqual(self.manifest['model_binding']['state'], expected_state)
        for agent in self.manifest['disabled_builtin_agents']:
            self.assertTrue(self.config['agent'][agent]['disable'])

        contract = self.manifest['provider']
        provider = self.config['provider'][contract['id']]
        self.assertEqual(provider['name'], contract['name'])
        self.assertEqual(provider['npm'], contract['npm'])
        self.assertEqual(provider['options']['baseURL'], contract['base_url'])
        model_contract = contract['model']
        self.assertEqual(list(provider['models']), [model_contract['id']])
        model = provider['models'][model_contract['id']]
        self.assertEqual(model['name'], model_contract['name'])
        self.assertEqual(model['limit']['context'], model_contract['context'])
        self.assertEqual(model['limit']['output'], model_contract['output'])


if __name__ == '__main__':
    unittest.main()
