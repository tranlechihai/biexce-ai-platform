from pathlib import Path
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
AGENTS_ROOT = REPOSITORY_ROOT / 'src' / 'global' / 'agents'
SKILLS_ROOT = REPOSITORY_ROOT / 'src' / 'global' / 'skills'
SECURITY_POLICY = SKILLS_ROOT / 'company' / 'security-policy' / 'SKILL.md'


def read(path):
    return path.read_text(encoding='utf-8')


class AgentBehaviorContractTests(unittest.TestCase):
    def test_each_agent_leaves_model_choice_to_the_user(self):
        for path in AGENTS_ROOT.glob('bx-*.md'):
            frontmatter = read(path).split('---', 2)[1]
            self.assertIn(
                'user may bind any connected provider/model',
                frontmatter,
                path.name,
            )
            self.assertNotRegex(frontmatter, r'(?i)runs? on the local model')

    def test_static_agent_delegation_is_fail_closed(self):
        for path in AGENTS_ROOT.glob('bx-*.md'):
            frontmatter = read(path).split('---', 2)[1]
            self.assertRegex(
                frontmatter,
                r'(?m)^\s*task:\s*deny\s*$',
                path.name,
            )
        director = read(AGENTS_ROOT / 'bx-director.md')
        self.assertIn('built-in `task` permission is permanently denied', director)
        self.assertIn('call `biexce_drive` and let the runtime own Explore, Plan', director)
        self.assertIn('Do not manually dispatch Explore, Plan, Plan Review', director)
        self.assertIn('`biexce_run_next`', director)
        self.assertIn('`biexce_drive`', director)
        self.assertIn('`biexce_start_job`', director)
        self.assertIn('Never bypass a scheduler refusal', director)

    def test_director_cannot_substitute_for_specialist_artifacts(self):
        director = read(AGENTS_ROOT / 'bx-director.md')
        frontmatter = director.split('---', 2)[1]
        self.assertNotIn('.biexce/**: ask', frontmatter)
        self.assertIn('.biexce/PROJECT_BRIEF.md: allow', frontmatter)
        self.assertIn('.biexce/reports/FINAL_REPORT.md: allow', frontmatter)
        self.assertIn(
            'Never write, repair or replace any file under `.biexce/state/`',
            director,
        )
        self.assertIn(
            'Never\ncreate or repair `CODEBASE_BRIEF.md`, `MASTER_PLAN.md`',
            director,
        )
        self.assertIn('driver creates visible\nspecialist sessions', director)

    def test_plan_requires_brief_and_preserves_defect_evidence(self):
        plan = read(AGENTS_ROOT / 'bx-plan.md')
        frontmatter = plan.split('---', 2)[1]
        self.assertNotIn('.biexce/**: ask', frontmatter)
        self.assertIn('.biexce/MASTER_PLAN.md: allow', frontmatter)
        self.assertIn('.biexce/tasks/**: allow', frontmatter)
        self.assertIn('ROUTE: bx-explore - CODEBASE_BRIEF required', plan)
        self.assertIn('A denied source read is not permission to infer', plan)
        self.assertIn('keep the failing test read-only', plan)
        self.assertIn('requirement/test conflict as a blocker', plan)
        self.assertIn('if the request says no file', plan)
        self.assertIn('Never edit `PROJECT_BRIEF.md` or `CODEBASE_BRIEF.md`', plan)

    def test_task_spec_separates_owner_writes_and_evidence(self):
        task_spec = read(SKILLS_ROOT / 'core' / 'task-spec' / 'SKILL.md')
        self.assertIn('Owner role:', task_spec)
        self.assertIn('Writable files:', task_spec)
        self.assertIn('Read-only inputs:', task_spec)
        self.assertIn('test đó là **read-only evidence**', task_spec)
        self.assertIn('đánh dấu blocker và escalate', task_spec)

    def test_explore_and_review_do_not_overstate_evidence(self):
        explore = read(AGENTS_ROOT / 'bx-explore.md')
        review = read(AGENTS_ROOT / 'bx-review.md')
        self.assertIn('Never say everything is verified', explore)
        self.assertIn('test counts do not reveal', review)
        self.assertIn('State evidence', review)
        self.assertIn('bounds instead of claiming zero risk', review)

    def test_cloud_review_raw_diff_exception_is_role_and_phase_bounded(self):
        review = read(AGENTS_ROOT / 'bx-review.md')
        policy = read(SECURITY_POLICY)
        frontmatter = review.split('---', 2)[1]

        self.assertIn('standing\nZone A exception', review)
        self.assertIn('`TASK_REVIEW` and `INTEGRATION_REVIEW`', review)
        self.assertIn('This does not apply to\n`PLAN_REVIEW`', review)
        self.assertIn('raw diff', policy)
        self.assertIn('`bx-review`', policy)
        self.assertIn('không cho phép Zone C', policy)
        for pattern in ('*.env', '*.pem', '*.key', '*credentials*.json'):
            self.assertIn(f'"{pattern}": deny', frontmatter)

    def test_explore_can_write_the_managed_codebase_brief(self):
        explore = read(AGENTS_ROOT / 'bx-explore.md')
        frontmatter = explore.split('---', 2)[1]
        self.assertRegex(
            frontmatter,
            r'(?m)^    \.biexce/CODEBASE_BRIEF\.md: allow$',
        )
        self.assertRegex(
            frontmatter,
            r'(?m)^    .+\.biexce/CODEBASE_BRIEF\.md.: allow$',
        )
        self.assertNotIn('CODEBASE_BRIEF.md: ask', frontmatter)

    def test_fix_uses_canonical_classification_and_bounded_risk(self):
        fix = read(AGENTS_ROOT / 'bx-fix.md')
        self.assertIn('exact `evidence-format` labels', fix)
        self.assertIn('`patch` (introduced by', fix)
        self.assertNotIn('`patch-defect`', fix)
        self.assertIn('never use a comment alone', fix)
        self.assertIn('classification MUST be `pre-existing`', fix)
        self.assertIn('before/after inventory', fix)
        self.assertIn('modified files and read-only inputs as separate lists', fix)
        self.assertIn('none observed within checked scope', fix)

    def test_code_handles_non_git_and_bounds_residual_risk(self):
        code = read(AGENTS_ROOT / 'bx-code.md')
        self.assertIn('Use `git diff` only after', code)
        self.assertIn('In a non-Git repo', code)
        self.assertIn('none observed within', code)
        self.assertIn('Writable files', code)
        self.assertIn('Modified files` and `Read-only inputs consulted', code)

    def test_execution_agents_forbid_unbounded_development_servers(self):
        for name in ('bx-code.md', 'bx-fix.md', 'bx-test.md'):
            content = read(AGENTS_ROOT / name)
            self.assertIn('server', content, name)
            self.assertIn('unbounded server commands', content, name)
        self.assertIn('TestClient', read(AGENTS_ROOT / 'bx-test.md'))

    def test_execution_agents_use_the_applicable_quality_pipeline(self):
        code = read(AGENTS_ROOT / 'bx-code.md')
        test = read(AGENTS_ROOT / 'bx-test.md')
        fix = read(AGENTS_ROOT / 'bx-fix.md')
        task_spec = read(SKILLS_ROOT / 'core' / 'task-spec' / 'SKILL.md')
        definition = read(
            SKILLS_ROOT / 'company' / 'definition-of-done' / 'SKILL.md'
        )

        for content in (code, test, fix, task_spec, definition):
            normalized = content.lower()
            self.assertIn('lint/static', normalized)
            self.assertIn('typecheck', normalized)
            self.assertIn('build/package', normalized)
        self.assertIn('formatter **check**', test)
        self.assertIn('verdict is `INCONCLUSIVE`', test)
        self.assertIn('never\n  invent a command', code)

    def test_bx_test_can_write_evidence_but_never_source(self):
        test = read(AGENTS_ROOT / 'bx-test.md')
        frontmatter = test.split('---', 2)[1]
        self.assertIn('.biexce/reports/**: allow', frontmatter)
        self.assertRegex(frontmatter, r"(?m)^\s*['\"]\*['\"]:\s*deny$")
        self.assertIn('never edit product source or test code', test)

    def test_autopilot_execution_agents_do_not_require_manual_edit_clicks(self):
        for name in ('bx-code.md', 'bx-fix.md'):
            frontmatter = read(AGENTS_ROOT / name).split('---', 2)[1]
            self.assertRegex(frontmatter, r'(?m)^\s*edit:\s*allow\s*$', name)
        self.assertIn(
            'RUNTIME-AUTHORITATIVE PRIOR TASK EVIDENCE',
            read(AGENTS_ROOT / 'bx-review.md'),
        )
        self.assertIn(
            'RUNTIME-AUTHORITATIVE PRIOR TASK EVIDENCE',
            read(AGENTS_ROOT / 'bx-fix.md'),
        )


if __name__ == '__main__':
    unittest.main()
