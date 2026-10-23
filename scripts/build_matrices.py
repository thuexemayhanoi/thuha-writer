"""Rebuild data/bilingual/matrix/{vi500,en500}.{json,csv} from data/bilingual/seeds/*.jsonl and validate them.

No network, no WordPress. IDs follow seed order inside plan.json category order, so rebuilding
after editing seeds renumbers rows: do it before any row is admitted to the factory, and keep
admitted topic IDs frozen afterwards (retire a row instead of deleting it).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thuha import matrix  # noqa: E402
from thuha.language import LANGUAGES  # noqa: E402

if __name__ == '__main__':
    code = 0
    for lang in LANGUAGES:
        built = matrix.build(lang)
        problems = matrix.validate(built, lang)
        print(json.dumps({'language': lang, 'summary': matrix.summary(built), 'problems': len(problems)}))
        for p in problems[:50]:
            print('  ', json.dumps(p, ensure_ascii=False))
        if problems:
            code = 1
            continue
        matrix.write(lang, built)
    sys.exit(code)
