"""Shared contract data: byte limits, the HTML allow-lists and the plugin answers that prove nothing was created."""
# Byte limits enforced by the plugin (UTF-8 bytes, not characters: Vietnamese averages ~1.5 bytes per character).
LIMITS = {'content_bytes': 200000, 'title_bytes': 300, 'seo_bytes': 400, 'slug_bytes': 90}
# One strict, canonical-form HTML policy shared by QA (Python) and the plugin (PHP, read from contract.json).
HTML_POLICY = {
    'tags': ['a', 'abbr', 'b', 'blockquote', 'br', 'caption', 'cite', 'code', 'div', 'em', 'figcaption', 'figure', 'h2', 'h3', 'h4',
             'h5', 'h6', 'hr', 'i', 'img', 'li', 'mark', 'ol', 'p', 'pre', 'small', 'span', 'strong', 'sub', 'sup', 'table',
             'tbody', 'td', 'tfoot', 'th', 'thead', 'time', 'tr', 'ul'],
    'void_tags': ['br', 'hr', 'img'],
    'global_attributes': ['class', 'dir', 'id', 'lang', 'title'],
    'attributes': {'a': ['href', 'hreflang', 'rel', 'target'], 'img': ['alt', 'height', 'loading', 'src', 'width'],
                   'td': ['colspan', 'rowspan', 'scope'], 'th': ['colspan', 'rowspan', 'scope'], 'ol': ['start', 'type'],
                   'time': ['datetime'], 'blockquote': ['cite']},
    'url_attributes': ['cite', 'href', 'src'],
    'url_schemes': ['http', 'https', 'mailto', 'tel'],
    'attribute_values': {'target': ['_blank', '_self'], 'loading': ['eager', 'lazy']},
}
# Plugin answers that prove NO post or draft was created, so an intent can be closed instead of left unresolved.
DEFINITIVE_REJECTIONS = ('thuha_schema', 'thuha_language_mismatch', 'thuha_marker', 'thuha_unsafe_html', 'thuha_key_payload_mismatch',
                         'thuha_topic_already_created', 'thuha_category_language_mismatch', 'thuha_media_invalid', 'thuha_slug_conflict',
                         'thuha_insert_failed', 'thuha_native_vi_missing', 'thuha_unauthenticated', 'thuha_app_password_required',
                         'thuha_origin_forbidden', 'thuha_forbidden')
