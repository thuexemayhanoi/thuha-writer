"""Reproducible ZIP of the companion plugin, plus offline integrity and safety checks.

`build` writes dist/thuha-native-vi-publisher-<version>.zip byte-for-byte reproducibly
(sorted entries, fixed timestamps, fixed permissions). `verify` rebuilds it in memory,
compares it with the committed archive, cross-checks the contract and statically scans
the PHP for constructs the contract forbids. None of this installs or contacts WordPress.
"""
import hashlib
import io
import re
import zipfile
from .adapter import manifest
from .common import ROOT, load

SLUG = 'thuha-native-vi-publisher'
SOURCE = ROOT / 'wordpress' / SLUG
DIST = ROOT / 'dist'
STAMP = (2026, 10, 22, 0, 0, 0)
FORBIDDEN = {
    'raw SQL / wpdb': r'\$wpdb|->query\s*\(|mysqli_|PDO\b',
    'code execution': r'\b(?:eval|exec|shell_exec|system|passthru|proc_open|popen|assert|create_function)\s*\(|`[^`\n]+`',
    'dynamic include': r'\b(?:include|require)(?:_once)?\s*\(?\s*\$',
    'unsafe deserialization': r'\bunserialize\s*\(',
    'outbound HTTP': r'\bwp_remote_(?:get|post|request|head)\b|\bcurl_|file_get_contents\s*\(\s*[\'"]https?',
    'filesystem write': r'\b(?:file_put_contents|fwrite|fputs|unlink|rename|copy|mkdir|move_uploaded_file)\s*\(',
    'public route': r'__return_true|nopriv|permission_callback[\'"]?\s*=>\s*(?:null|false)',
    'direct superglobal use': r'\$_(?:GET|POST|REQUEST|COOKIE|SERVER|FILES)\b',
}


ERROR_CODES = ('thuha_unauthenticated', 'thuha_app_password_required', 'thuha_origin_forbidden', 'thuha_forbidden', 'thuha_schema',
               'thuha_language_mismatch', 'thuha_marker', 'thuha_unsafe_html', 'thuha_key_payload_mismatch', 'thuha_topic_already_created',
               'thuha_category_language_mismatch', 'thuha_media_invalid', 'thuha_slug_conflict', 'thuha_insert_failed', 'thuha_content_altered',
               'thuha_language_marker_failed', 'thuha_seo_failed', 'thuha_media_failed', 'thuha_category_failed', 'thuha_slug_changed',
               'thuha_permalink_mismatch', 'thuha_publish_failed', 'thuha_revert_failed', 'thuha_in_progress', 'thuha_duplicate_key',
               'thuha_foreign_post', 'thuha_inventory_filtered', 'thuha_native_vi_missing')


def contract_document():
    """The machine-readable contract. The plugin itself reads its limits and HTML allow-lists from this file."""
    doc = manifest()
    doc['plugin'] = {'slug': SLUG, 'version': version(),
                     'requires_native_plugin': 'rentbikehanoi-native-vi (class RBHVI_Language, taxonomy rbhvi_language)'}
    doc['auth'] = {'credential': 'WordPress Application Password only', 'cookie_sessions': 'refused',
                   'browser_origin': 'refused unless listed in option thuha_adapter_allowed_origins',
                   'capabilities': {'read': 'edit_posts', 'write': 'publish_posts'}}
    doc['safety'] = {'public_routes': 0, 'raw_sql': False, 'request_supplied_code': False, 'create_only': True,
                     'draft_before_publish': True, 'language_marker_before_publish': True, 'permalink_checked_before_publish': True,
                     'replay_mutates': False, 'html_policy': 'strict canonical form, shared with QA'}
    doc['error_codes'] = list(ERROR_CODES)
    doc['live_status'] = 'NOT_DEPLOYED_NOT_TESTED_AGAINST_WORDPRESS'
    doc['routes'] = {k: list(v) for k, v in doc['routes'].items()}
    return doc


def write_contract():
    import json
    (SOURCE / 'contract.json').write_text(json.dumps(contract_document(), indent=2, ensure_ascii=False, sort_keys=True) + '\n', encoding='utf-8')


def files():
    return sorted(p for p in SOURCE.rglob('*') if p.is_file() and not p.name.startswith('.'))


def version():
    header = (SOURCE / (SLUG + '.php')).read_text(encoding='utf-8')
    match = re.search(r'^\s*\*\s*Version:\s*(\S+)', header, re.M)
    if not match:
        raise ValueError('Plugin header has no Version')
    return match.group(1)


def archive_name():
    return SLUG + '-' + version() + '.zip'


def build_bytes():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for path in files():
            info = zipfile.ZipInfo(SLUG + '/' + path.relative_to(SOURCE).as_posix(), STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            archive.writestr(info, path.read_bytes(), compresslevel=9)
    return buffer.getvalue()


def build():
    DIST.mkdir(exist_ok=True)
    data = build_bytes()
    target = DIST / archive_name()
    target.write_bytes(data)
    sha = hashlib.sha256(data).hexdigest()
    (DIST / (archive_name() + '.sha256')).write_text(sha + '  ' + archive_name() + '\n')
    return {'archive': 'dist/' + archive_name(), 'sha256': sha, 'bytes': len(data), 'files': len(files())}


def scan():
    """Findings from the static safety scan of every PHP file (empty means clean)."""
    findings = []
    for path in files():
        if path.suffix != '.php':
            continue
        text = path.read_text(encoding='utf-8')
        code = re.sub(r'/\*.*?\*/', '', text, flags=re.S)
        code = re.sub(r'(?m)^\s*//.*$', '', code)
        for label, pattern in FORBIDDEN.items():
            if re.search(pattern, code):
                findings.append(path.name + ': ' + label)
        if "defined( 'ABSPATH' )" not in text:
            findings.append(path.name + ': direct access guard missing')
    return findings


def verify():
    """Raise unless the committed archive, contract and source agree. Returns evidence."""
    contract = load(SOURCE / 'contract.json')
    if contract != contract_document():
        raise ValueError('contract.json is out of date with src/thuha/adapter.py and policy.py; run scripts/build_adapter_zip.py')
    unknown = [c for c in contract['definitive_rejections_before_insert'] if c not in contract['error_codes']]
    if unknown:
        raise ValueError('Definitive rejection codes missing from the plugin error list: ' + ','.join(unknown))
    findings = scan()
    if findings:
        raise ValueError('Plugin safety scan failed: ' + '; '.join(findings))
    committed = DIST / archive_name()
    if not committed.exists():
        raise ValueError('Run `python -m thuha.cli package` is read-only; build the archive with scripts/build_adapter_zip.py')
    data = build_bytes()
    if committed.read_bytes() != data:
        raise ValueError('dist archive is out of date with wordpress/' + SLUG + '; rebuild with scripts/build_adapter_zip.py')
    sha = hashlib.sha256(data).hexdigest()
    recorded = (DIST / (archive_name() + '.sha256')).read_text().split()[0]
    if recorded != sha:
        raise ValueError('dist checksum file does not match the archive')
    return {'archive': 'dist/' + archive_name(), 'sha256': sha, 'version': version(), 'files': len(files()),
            'safety_scan': 'clean', 'live_status': contract['live_status']}
