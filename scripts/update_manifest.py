#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / 'src' / 'global'
MANIFEST_PATH = REPOSITORY_ROOT / 'src' / 'harness-manifest.json'
SCHEMA_PATH = REPOSITORY_ROOT / 'src' / 'harness-manifest.schema.json'
AGENT_ORDER = (
    'bx-director',
    'bx-plan',
    'bx-explore',
    'bx-code',
    'bx-fix',
    'bx-test',
    'bx-review',
)
STATUSES = {'skeleton', 'draft', 'ready'}
DEFAULT_FIELDS = ('default_agent', 'subagent_depth', 'share', 'autoupdate')
MODEL_FIELDS = ('model', 'small_model', 'variant')
RUNTIME_FILES = (
    ('biexce-control-plugin', 'plugins/biexce-control.js'),
)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def scalar(text):
    value = text.strip()
    if ' #' in value:
        value = value.split(' #', 1)[0].rstrip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {chr(34), chr(39)}:
        value = value[1:-1]
    return value


def frontmatter(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    if not lines or lines[0].strip() != '---':
        raise ValueError(f'Missing YAML frontmatter: {path}')
    try:
        end = lines.index('---', 1)
    except ValueError as error:
        raise ValueError(f'Unclosed YAML frontmatter: {path}') from error

    result = {}
    metadata = {}
    in_metadata = False
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        indent = len(line) - len(line.lstrip(' '))
        if indent == 0:
            in_metadata = False
            if ':' not in line:
                continue
            key, value = line.split(':', 1)
            key = key.strip()
            if key == 'metadata' and not value.strip():
                in_metadata = True
                continue
            result[key] = scalar(value)
        elif in_metadata and indent >= 2 and ':' in line:
            key, value = line.strip().split(':', 1)
            metadata[key.strip()] = scalar(value)
    result['metadata'] = metadata
    return result


def relative(path):
    return path.relative_to(SOURCE_ROOT).as_posix()


def build_agents():
    discovered = {}
    for path in (SOURCE_ROOT / 'agents').glob('bx-*.md'):
        data = frontmatter(path)
        agent_id = path.stem
        mode = data.get('mode')
        if mode not in {'primary', 'all', 'subagent'}:
            raise ValueError(f'Invalid mode for {agent_id}: {mode}')
        discovered[agent_id] = {
            'id': agent_id,
            'mode': mode,
            'model': data.get('model') or None,
            'path': relative(path),
            'sha256': sha256(path),
        }
    if set(discovered) != set(AGENT_ORDER):
        raise ValueError(
            f'Expected agents {list(AGENT_ORDER)}, got {sorted(discovered)}'
        )
    return [discovered[agent_id] for agent_id in AGENT_ORDER]


def build_skills():
    skills = []
    for path in sorted((SOURCE_ROOT / 'skills').rglob('SKILL.md')):
        if '_TEMPLATE' in path.parts:
            continue
        data = frontmatter(path)
        metadata = data['metadata']
        skill_id = data.get('name')
        status = metadata.get('status')
        if not skill_id or status not in STATUSES:
            raise ValueError(f'Invalid skill metadata: {path}')
        parts = path.relative_to(SOURCE_ROOT / 'skills').parts
        area = f'roles/{parts[1]}' if parts[0] == 'roles' else parts[0]
        applies_to = [
            value.strip()
            for value in metadata.get('applies_to', '').split(',')
            if value.strip()
        ]
        skills.append(
            {
                'id': skill_id,
                'area': area,
                'status': status,
                'applies_to': applies_to,
                'sources': metadata.get('sources', ''),
                'path': relative(path),
                'sha256': sha256(path),
            }
        )
    ids = [skill['id'] for skill in skills]
    paths = [skill['path'] for skill in skills]
    if len(ids) != len(set(ids)) or len(paths) != len(set(paths)):
        raise ValueError('Skill ids and paths must be unique.')
    return skills


def build_provider(config, previous):
    providers = config.get('provider', {})
    provider_id = previous.get('provider', {}).get('id', 'biexce-local')
    if provider_id not in providers:
        raise ValueError(f'Canonical provider is missing: {provider_id}')
    provider = providers[provider_id]
    models = provider.get('models', {})
    if len(models) != 1:
        raise ValueError('Canonical Biexce provider must define exactly one model.')
    model_id, model = next(iter(models.items()))
    limits = model.get('limit', {})
    return {
        'id': provider_id,
        'name': provider['name'],
        'npm': provider['npm'],
        'base_url': provider['options']['baseURL'],
        'model': {
            'id': model_id,
            'name': model['name'],
            'context': limits['context'],
            'output': limits['output'],
        },
    }


def build_runtime_files():
    return [
        {
            'id': runtime_id,
            'path': relative_path,
            'sha256': sha256(SOURCE_ROOT / relative_path),
        }
        for runtime_id, relative_path in RUNTIME_FILES
    ]


def build_manifest():
    config = json.loads((SOURCE_ROOT / 'opencode.json').read_text(encoding='utf-8'))
    previous = json.loads(MANIFEST_PATH.read_text(encoding='utf-8'))
    agents = build_agents()
    global_bindings = {field: config.get(field) for field in MODEL_FIELDS}
    agent_bindings = {agent['id']: agent['model'] for agent in agents}
    bound = any(global_bindings.values()) or any(agent_bindings.values())
    disabled = sorted(
        agent_id
        for agent_id, definition in config.get('agent', {}).items()
        if definition.get('disable') is True
    )
    manifest = {
        '$schema': './harness-manifest.schema.json',
        'schema_version': 2,
        'supported_opencode': previous['supported_opencode'],
        'defaults': {field: config[field] for field in DEFAULT_FIELDS},
        'model_binding': {
            'state': 'bound' if bound else 'unset',
            'global': global_bindings,
            'agents': agent_bindings,
        },
        'disabled_builtin_agents': disabled,
        'agents': agents,
        'skills': build_skills(),
        'runtime_files': build_runtime_files(),
        'provider': build_provider(config, previous),
    }
    validate_manifest(manifest)
    return manifest


def validate_manifest(manifest):
    required = {
        '$schema',
        'schema_version',
        'supported_opencode',
        'defaults',
        'model_binding',
        'disabled_builtin_agents',
        'agents',
        'skills',
        'runtime_files',
        'provider',
    }
    if set(manifest) != required or manifest['schema_version'] != 2:
        raise ValueError('Manifest v2 root contract is invalid.')
    for collection in ('agents', 'skills', 'runtime_files'):
        values = manifest[collection]
        for field in ('id', 'path', 'sha256'):
            items = [value[field] for value in values]
            if len(items) != len(set(items)):
                raise ValueError(f'Duplicate {collection}.{field}.')
        for value in values:
            path = SOURCE_ROOT / value['path']
            if not path.is_file() or sha256(path) != value['sha256']:
                raise ValueError('Invalid source contract: ' + value['path'])
    if any(skill['status'] not in STATUSES for skill in manifest['skills']):
        raise ValueError('Manifest contains an invalid skill status.')


def main():
    parser = argparse.ArgumentParser(
        description='Generate the deterministic Biexce harness manifest v2.'
    )
    parser.add_argument(
        '--check',
        action='store_true',
        help='Fail when the checked-in manifest is not generated from source.',
    )
    arguments = parser.parse_args()
    if not SCHEMA_PATH.is_file():
        raise ValueError(f'Manifest schema is missing: {SCHEMA_PATH}')
    manifest = build_manifest()
    generated = json.dumps(manifest, indent=2, ensure_ascii=False) + '\n'
    if arguments.check:
        current = MANIFEST_PATH.read_text(encoding='utf-8')
        if current != generated:
            raise ValueError(
                'Harness manifest is stale. Run scripts/update_manifest.py.'
            )
        print('Harness manifest v2 is current.')
        return 0
    MANIFEST_PATH.write_text(generated, encoding='utf-8', newline='\n')
    agent_count = len(manifest['agents'])
    skill_count = len(manifest['skills'])
    print(f'Updated {MANIFEST_PATH}: {agent_count} agents, {skill_count} skills.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
