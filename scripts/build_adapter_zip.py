"""Rebuild dist/thuha-native-vi-publisher-<version>.zip reproducibly from wordpress/."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from thuha import package  # noqa: E402

if __name__ == '__main__':
    findings = package.scan()
    if findings:
        sys.exit('Refusing to package: ' + '; '.join(findings))
    print(json.dumps(package.build(), indent=2))
