#!/usr/bin/env python3
"""sys.artifact.schema.json の妥当性と examples/ の正常例・異常例を検証する。

使い方: python3 validate.py   (要 jsonschema 4.x)
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).parent


def main():
    schema = json.loads((ROOT / "sys.artifact.schema.json").read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    failures = 0
    for instance, label in (({}, "空オブジェクト"), ({"artifact_type": "UNKNOWN"}, "未定義のartifact_type")):
        if validator.is_valid(instance):
            failures += 1
            print(f"FAIL {label} が通過した")

    covered = set()
    for path in sorted((ROOT / "examples").glob("*.json")):
        examples = json.loads(path.read_text(encoding="utf-8"))
        for section, expect_valid in (("valid", True), ("invalid", False)):
            for i, instance in enumerate(examples.get(section, [])):
                errors = list(validator.iter_errors(instance))
                if section == "valid":
                    covered.add(instance.get("artifact_type"))
                if bool(errors) == expect_valid:
                    failures += 1
                    detail = errors[0].message if errors else "エラーなし"
                    print(f"FAIL {path.stem} {section}[{i}]: {detail}")

    declared = set(schema["properties"]["artifact_type"]["enum"])
    if declared != covered:
        failures += 1
        print(f"FAIL 正常例のない artifact_type: {sorted(declared - covered)} / 未定義: {sorted(covered - declared)}")
    print("OK" if not failures else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
