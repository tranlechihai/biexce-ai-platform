#!/usr/bin/env python3

import re
from pathlib import Path
import sys

from update_manifest import SOURCE_ROOT, STATUSES, frontmatter


SKILLS_ROOT = SOURCE_ROOT / 'skills'
REQUIRED_TOP_LEVEL = {'name', 'description', 'compatibility'}
REQUIRED_METADATA = {'owner', 'status', 'applies_to', 'sources'}
AGENT_IDS = {
    'bx-director',
    'bx-plan',
    'bx-explore',
    'bx-code',
    'bx-fix',
    'bx-test',
    'bx-review',
}
BASELINE_SKILL_PATHS = {
    'company/definition-of-done/SKILL.md',
    'company/security-policy/SKILL.md',
    'roles/planning-ba/prd/SKILL.md',
    'roles/planning-ba/user-story/SKILL.md',
    'roles/planning-ba/acceptance-criteria/SKILL.md',
    'roles/planning-ba/estimate/SKILL.md',
    'roles/architecture/system-design/SKILL.md',
    'roles/architecture/adr/SKILL.md',
    'roles/architecture/api-contract/SKILL.md',
    'roles/architecture/data-model/SKILL.md',
    'roles/backend/api-design/SKILL.md',
    'roles/backend/database-migration/SKILL.md',
    'roles/backend/auth-security/SKILL.md',
    'roles/backend/testing-backend/SKILL.md',
    'roles/backend/performance/SKILL.md',
    'roles/qa-testing/test-strategy/SKILL.md',
    'roles/qa-testing/unit-integration-e2e/SKILL.md',
    'roles/qa-testing/regression/SKILL.md',
}
REQUIRED_BASELINE_HEADINGS = (
    '## Khi nào dùng',
    '## Nội dung',
    '## Chống chỉ định / giới hạn',
)
REQUIRED_ROLE_HEADINGS = REQUIRED_BASELINE_HEADINGS


def body(path):
    text = path.read_text(encoding='utf-8')
    parts = text.split('---', 2)
    if len(parts) != 3:
        raise ValueError(f'Invalid frontmatter delimiters: {path}')
    return parts[2]


def validate_skill(path):
    relative = path.relative_to(SKILLS_ROOT).as_posix()
    data = frontmatter(path)
    metadata = data.get('metadata', {})
    missing_top = REQUIRED_TOP_LEVEL - set(data)
    missing_meta = REQUIRED_METADATA - set(metadata)
    if missing_top or missing_meta:
        raise ValueError(
            f'{relative}: missing fields top={sorted(missing_top)} '
            f'metadata={sorted(missing_meta)}'
        )
    if data['compatibility'] != 'opencode':
        raise ValueError(f'{relative}: compatibility must be opencode')
    if data['name'] != path.parent.name:
        raise ValueError(f'{relative}: name must match parent directory')
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', data['name']):
        raise ValueError(f'{relative}: invalid kebab-case skill name')
    if metadata['status'] not in STATUSES:
        raise ValueError(f'{relative}: invalid status {metadata["status"]}')
    for field in ('description',):
        value = data[field].strip()
        if len(value) < 40 or '<' in value or 'TODO' in value:
            raise ValueError(f'{relative}: incomplete {field}')
    for field in REQUIRED_METADATA - {'status'}:
        value = metadata[field].strip()
        if not value or '<' in value or 'TODO' in value:
            raise ValueError(f'{relative}: incomplete metadata.{field}')

    content = body(path)
    if metadata['status'] == 'ready':
        if '[SKELETON]' in content or re.search(r'(?m)^TODO\s*$', content):
            raise ValueError(f'{relative}: ready skill contains placeholder')
        if len(content.strip()) < 200:
            raise ValueError(f'{relative}: ready skill body is too short')
    if relative in BASELINE_SKILL_PATHS:
        if metadata['status'] != 'ready':
            raise ValueError(f'{relative}: baseline skill must be ready')
        for heading in REQUIRED_BASELINE_HEADINGS:
            if heading not in content:
                raise ValueError(f'{relative}: missing heading {heading}')
        if 'Ví dụ' not in content:
            raise ValueError(f'{relative}: baseline skill needs a concise example')
    if relative.startswith('roles/'):
        if metadata['status'] != 'ready':
            raise ValueError(f'{relative}: generic role skill must be ready')
        for heading in REQUIRED_ROLE_HEADINGS:
            if heading not in content:
                raise ValueError(f'{relative}: missing heading {heading}')
        if 'Ví dụ' not in content:
            raise ValueError(f'{relative}: role skill needs a concise example')
        source_items = [
            item.strip() for item in metadata['sources'].split(';') if item.strip()
        ]
        if len(source_items) < 2:
            raise ValueError(
                f'{relative}: role skill needs at least two named sources'
            )
        applies_to = {
            item.strip()
            for item in metadata['applies_to'].split(',')
            if item.strip()
        }
        invalid_agents = applies_to - AGENT_IDS
        if not applies_to or invalid_agents:
            raise ValueError(
                f'{relative}: invalid metadata.applies_to {sorted(invalid_agents)}'
            )
    return relative, metadata['status']


def validate_all():
    paths = sorted(
        path for path in SKILLS_ROOT.rglob('SKILL.md')
        if '_TEMPLATE' not in path.parts
    )
    discovered = {
        path.relative_to(SKILLS_ROOT).as_posix()
        for path in paths
    }
    missing_baseline = BASELINE_SKILL_PATHS - discovered
    if missing_baseline:
        raise ValueError(f'Missing baseline skills: {sorted(missing_baseline)}')
    counts = {status: 0 for status in sorted(STATUSES)}
    for path in paths:
        _, status = validate_skill(path)
        counts[status] += 1
    role_count = sum(
        1 for path in paths
        if path.relative_to(SKILLS_ROOT).as_posix().startswith('roles/')
    )
    return len(paths), counts, role_count


def main():
    count, statuses, role_count = validate_all()
    summary = ', '.join(
        f'{status}={statuses[status]}' for status in ('ready', 'draft', 'skeleton')
    )
    print(
        f'Validated {count} skills ({summary}); '
        f'baseline skills=18 ready; role skills={role_count} ready.'
    )
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
