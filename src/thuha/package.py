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
    mine = manifest()
    drift = [k for k in ('contract', 'namespace', 'create_fields', 'seo_fields', 'yoast_meta', 'site')
             if contract.get(k) != mine[k]]
    if {k: list(v) for k, v in mine['routes'].items()} != contract['routes']:
        drift.append('routes')
    if drift:
        raise ValueError('contract.json differs from src/thuha/adapter.py: ' + ','.join(drift))
    if contract['plugin']['version'] != version() or contract['plugin']['slug'] != SLUG:
        raise ValueError('contract.json plugin version/slug differs from the plugin header')
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
