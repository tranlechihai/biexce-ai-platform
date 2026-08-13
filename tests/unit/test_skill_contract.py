import json
import subprocess
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class SkillContractTests(unittest.TestCase):
    def test_skill_tree_and_required_baseline_are_valid(self):
        result = subprocess.run(
            [sys.executable, str(REPOSITORY_ROOT / 'scripts' / 'validate_skills.py')],
            capture_output=True,
            text=True,
            encoding='utf-8',
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('baseline skills=18 ready', result.stdout)
        self.assertIn('role skills=45 ready', result.stdout)

    def test_social_mobile_backend_skill_pack_is_ready(self):
        manifest = json.loads(
            (
                REPOSITORY_ROOT / 'src' / 'harness-manifest.json'
            ).read_text(encoding='utf-8')
        )
        required = {
            'social-graph-feed',
            'media-upload-delivery',
            'push-notification-delivery',
            'realtime-event-delivery',
            'mobile-offline-sync',
            'abuse-moderation',
        }
        skills = {
            skill['id']: skill
            for skill in manifest['skills']
            if skill['id'] in required
        }
        self.assertEqual(set(skills), required)
        for skill in skills.values():
            self.assertEqual(skill['area'], 'roles/backend')
            self.assertEqual(skill['status'], 'ready')
            self.assertIn('bx-plan', skill['applies_to'])
            self.assertIn('bx-code', skill['applies_to'])
            self.assertIn('bx-test', skill['applies_to'])
            self.assertIn('bx-review', skill['applies_to'])

    def test_browser_exploratory_is_optional_local_first_bx_test_only(self):
        skill = (
            REPOSITORY_ROOT
            / 'src'
            / 'global'
            / 'skills'
            / 'roles'
            / 'qa-testing'
            / 'browser-exploratory'
            / 'SKILL.md'
        ).read_text(encoding='utf-8')
        bx_test = (
            REPOSITORY_ROOT / 'src' / 'global' / 'agents' / 'bx-test.md'
        ).read_text(encoding='utf-8')
        self.assertIn('applies_to: bx-test', skill)
        self.assertIn('không phải bước bắt buộc', skill)
        self.assertIn('Không khởi tạo cloud browser', skill)
        self.assertIn('Không thay Playwright', skill)
        self.assertIn('Load `qa-testing/browser-exploratory` only when', bx_test)


if __name__ == '__main__':
    unittest.main()
