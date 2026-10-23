"""Small deterministic primitives; no third-party runtime dependencies."""
import datetime as dt
import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
SITE = 'https://rentbikehanoi.com'
REPO = 'thuexemayhanoi/thuha-writer'


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def age(stamp):
    parsed = dt.datetime.fromisoformat(stamp)
    if parsed.tzinfo is None:
        raise ValueError('Timestamp must include timezone')
    return (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds()


def fresh(stamp, max_age):
    """Younger than `max_age` seconds and not dated in the future."""
    return 0 <= age(stamp) < max_age


def canonical_json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()


def digest(value):
    return hashlib.sha256(value if isinstance(value, bytes) else canonical_json(value)).hexdigest()


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    """fsync + atomic rename: an interrupted write never leaves partial JSON."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode() + b'\n'
    fd, temp = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def fold(text):
    """Strip diacritics; unlike bare NFKD this keeps the Vietnamese đ as d."""
    text = str(text).replace('đ', 'd').replace('Đ', 'D')
    return unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode()


def norm(text):
    return ' '.join(re.findall(r'[a-z0-9]+', fold(text).lower()))


def urlkey(url):
    p = urlsplit(url)
    if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Expected a credential-free HTTPS URL')
    return urlunsplit(('https', p.netloc.lower(), p.path.rstrip('/') or '/', '', ''))


def signature(text):
    words = norm(text).split()
    # Bottom-k fingerprints are an overlap signal, not a semantic proof.
    return sorted({hashlib.sha256(' '.join(words[i:i+5]).encode()).hexdigest()[:16]
                   for i in range(max(0, len(words)-4))})[:96]


def validate_inventory(inv, max_age=21600):
    if inv.get('site') != SITE or not inv.get('complete') or inv.get('errors'):
        raise ValueError('Complete inventory for the exact production site is required')
    if not 0 <= age(inv['captured_at']) <= max_age:
        raise ValueError('Inventory is stale or future-dated')


def category_path(category_id, categories):
    by_id = {x['id']: x for x in categories}
    path, seen = [], set()
    while category_id:
        if category_id in seen or category_id not in by_id:
            raise ValueError('Missing or cyclic taxonomy ancestry')
        seen.add(category_id)
        cat = by_id[category_id]
        path.insert(0, cat['id'])
        category_id = cat['parent']
    if not path:
        raise ValueError('No category selected')
    return path
