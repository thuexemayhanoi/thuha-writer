"""Strict canonical-form HTML policy shared by QA and the WordPress plugin.

Rather than interpret arbitrary markup (parsers disagree with browsers, which is how filter bypasses
happen), the policy REJECTS anything outside one narrow form: lower-case allow-listed tags, double-quoted
allow-listed attributes with no duplicates, URL values free of entities other than &amp; and of whitespace,
control characters and unsafe schemes, no comments, declarations or processing instructions, and no bare
'<' in text. The plugin implements the identical algorithm in PHP from the same allow-lists
(wordpress/thuha-native-vi-publisher/contract.json); a shared vector file keeps them in step.
"""
import re
from .policy import HTML_POLICY

WS = '[ \\t\\r\\n\\f]'  # ASCII whitespace only, so Python and PHP (bytewise PCRE) agree
TAG = re.compile('<(/?)([a-z][a-z0-9]*)((?:' + WS + '+[a-z][a-z0-9-]*="[^"<>]*")*)' + WS + '*(/?)>')
ATTR = re.compile(WS + '+([a-z][a-z0-9-]*)="([^"<>]*)"')
SCHEME = re.compile(r'^[a-z][a-z0-9+.-]*:')
UNSAFE_URL = re.compile(r'[^\x21-\x7e]|[\\"\'`<>]')  # URLs must be printable ASCII; percent-encode anything else


def violations(markup):
    """Reasons `markup` falls outside the policy; an empty list means it is acceptable."""
    tags, voids = set(HTML_POLICY['tags']), set(HTML_POLICY['void_tags'])
    glob, per = set(HTML_POLICY['global_attributes']), HTML_POLICY['attributes']
    urls, schemes, values = set(HTML_POLICY['url_attributes']), set(HTML_POLICY['url_schemes']), HTML_POLICY['attribute_values']
    out, i = [], 0
    while True:
        i = markup.find('<', i)
        if i < 0:
            return out
        m = TAG.match(markup, i)
        if not m:
            out.append('malformed-markup')
            i += 1
            continue
        closing, tag, attrs, selfclose = m.groups()
        i = m.end()
        if tag not in tags:
            out.append('tag:' + tag)
            continue
        if closing and (attrs.strip(' \t\r\n\f') or selfclose or tag in voids):
            out.append('closing-tag-form:' + tag)
        if selfclose and tag not in voids:
            out.append('self-closing:' + tag)
        seen = set()
        for name, value in ATTR.findall(attrs):
            if name in seen:
                out.append('duplicate-attribute:' + tag + '.' + name)
            seen.add(name)
            if name not in glob and name not in per.get(tag, []):
                out.append('attribute:' + tag + '.' + name)
                continue
            if name in values and value not in values[name]:
                out.append('attribute-value:' + tag + '.' + name)
            if name in urls:
                if '&' in value.replace('&amp;', '') or UNSAFE_URL.search(value):
                    out.append('url-form:' + tag + '.' + name)
                    continue
                low = value.replace('&amp;', '&').lower()
                if SCHEME.match(low) and low.split(':', 1)[0] not in schemes:
                    out.append('url-scheme:' + tag + '.' + name)
