from __future__ import annotations

import argparse
import json
import re
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, SchemaError

from .config import REPOSITORY_DIR

NAMESPACE = uuid.NAMESPACE_URL
SAMPLE_IDS = {
    "customer_id": "10000000-0000-4000-8000-000000000001",
    "platform_id": "10000000-0000-4000-8000-000000000002",
    "platform_version_id": "10000000-0000-4000-8000-000000000003",
    "product_id": "10000000-0000-4000-8000-000000000004",
    "product_version_id": "10000000-0000-4000-8000-000000000005",
    "record_id": "10000000-0000-4000-8000-000000000006",
    "revision_1_id": "10000000-0000-4000-8000-000000000007",
    "revision_2_id": "10000000-0000-4000-8000-000000000008",
}


@dataclass(frozen=True)
class SchemaDesign:
    markdown: Path
    schema_path: Path
    examples_dir: Path
    schema_key: str
    schema_version: int
    record_type: str
    feature_domain: str | None


def _json_bytes(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _read_settings(repository_dir: Path) -> tuple[Path, Path]:
    spec_file = repository_dir / "design" / "requiments" / "enviroment.md"
    if not spec_file.is_file():
        raise FileNotFoundError(f"Environment specification not found: {spec_file}")
    content = spec_file.read_text(encoding="utf-8")

    def setting(key: str) -> Path:
        match = re.search(rf"^\| `{re.escape(key)}` \| `([^`]+)` \|", content, flags=re.MULTILINE)
        if match is None:
            raise ValueError(f"Setting {key} is missing from {spec_file}")
        return repository_dir / match.group(1)

    return setting("ER_DESIGN_FILE"), setting("JSON_SCHEMA_DESIGN_DIR")


def _schema_designs(schema_dir: Path, er_design: Path) -> tuple[list[SchemaDesign], list[Path]]:
    markdown_files = sorted(schema_dir.rglob("*.md"))
    if not schema_dir.is_dir():
        raise FileNotFoundError(f"JSON schema design directory not found: {schema_dir}")
    if not markdown_files:
        raise ValueError(f"No Markdown schema design files found under {schema_dir}")

    designs: list[SchemaDesign] = []
    excluded: list[Path] = []
    for markdown in markdown_files:
        if markdown.resolve() == er_design.resolve():
            excluded.append(markdown)
            continue
        content = markdown.read_text(encoding="utf-8")
        schema_match = re.search(r"`(schemas/[^`| ]+\.schema\.json)`", content)
        has_registration = "JSON_SCHEMA" in content and "schema_key" in content
        if schema_match is None and not has_registration:
            discusses_schemas = re.search(r"JSON\s*Schema|JSONスキーマ", content, re.IGNORECASE)
            if markdown.name.lower() == "readme.md" or not discusses_schemas:
                excluded.append(markdown)
                continue
            raise ValueError(
                f"Cannot determine whether {markdown} is a JSON Schema design; "
                "user clarification is required"
            )
        if schema_match is None or not has_registration:
            raise ValueError(
                f"Cannot determine the JSON Schema file and registration mapping in "
                f"{markdown}; user clarification is required"
            )

        path = markdown.parent / schema_match.group(1)
        if not path.is_file():
            raise FileNotFoundError(f"Schema declared by {markdown} does not exist: {path}")
        key_match = re.search(r"`schema_key` = `([^`]+)`", content)
        version_match = re.search(r"`schema_version` = (\d+)", content)
        type_match = re.search(r"`record_type` = `([^`]+)`", content)
        domain_match = re.search(r"`feature_domain` = (NULL|`([^`]+)`)", content)
        if not all((key_match, version_match, type_match, domain_match)):
            raise ValueError(
                f"Schema registration mapping is incomplete in {markdown}; "
                "user clarification is required"
            )
        feature_domain = None if domain_match.group(1) == "NULL" else domain_match.group(2)
        designs.append(
            SchemaDesign(
                markdown=markdown,
                schema_path=path,
                examples_dir=path.parent / "examples",
                schema_key=key_match.group(1),
                schema_version=int(version_match.group(1)),
                record_type=type_match.group(1),
                feature_domain=feature_domain,
            )
        )
    if not designs:
        raise ValueError(
            f"No JSON Schema design could be identified under {schema_dir}; "
            "user confirmation is required"
        )
    return designs, excluded


def _load_schema(design: SchemaDesign) -> dict[str, Any]:
    schema = json.loads(design.schema_path.read_text(encoding="utf-8"))
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise ValueError(f"Invalid JSON Schema in {design.schema_path}: {exc.message}") from exc
    identifier = schema.get("$id")
    match = re.fullmatch(r"urn:[^:]+:schema:(.+):(\d+)", identifier or "")
    if match is None:
        raise ValueError(f"Unexpected or missing $id in {design.schema_path}: {identifier!r}")
    if match.group(1) != design.schema_key or int(match.group(2)) != design.schema_version:
        raise ValueError(
            f"$id in {design.schema_path} conflicts with the mapping in {design.markdown}"
        )
    return schema


def _schema_row(design: SchemaDesign, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": str(uuid.uuid5(NAMESPACE, schema["$id"])),
        "schema_key": design.schema_key,
        "schema_version": design.schema_version,
        "record_type": design.record_type,
        "feature_domain": design.feature_domain,
        "schema_json": schema,
    }


def _schema_seed_rows(
    designs: list[SchemaDesign], seed_dir: Path
) -> tuple[list[dict[str, Any]], dict[Path, tuple[SchemaDesign, dict[str, Any]]]]:
    rows_by_key: dict[tuple[str, int], dict[str, Any]] = {}
    schema_lookup: dict[Path, tuple[SchemaDesign, dict[str, Any]]] = {}
    for design in designs:
        schema = _load_schema(design)
        row = _schema_row(design, schema)
        key = (row["schema_key"], row["schema_version"])
        prior = rows_by_key.get(key)
        if prior is not None:
            if prior["schema_json"] != row["schema_json"]:
                raise ValueError(f"Conflicting schema definition for {key[0]} version {key[1]}")
            raise ValueError(f"Duplicate schema definition for {key[0]} version {key[1]}")
        rows_by_key[key] = row
        schema_lookup[design.schema_path] = (design, schema)

    existing_path = seed_dir / "10_json_schema.json"
    if existing_path.is_file():
        existing = json.loads(existing_path.read_text(encoding="utf-8"))
        for row in existing.get("JSON_SCHEMA", []):
            key = (row["schema_key"], row["schema_version"])
            current = rows_by_key.get(key)
            if current is not None and current["schema_json"] != row["schema_json"]:
                raise ValueError(
                    f"Schema {key[0]} version {key[1]} is immutable; increase schema_version"
                )
            if current is None:
                rows_by_key[key] = row
    return (
        sorted(
            rows_by_key.values(),
            key=lambda row: (row["schema_key"], row["schema_version"], row["schema_id"]),
        ),
        schema_lookup,
    )


def _example_seed_rows(
    schema_lookup: dict[Path, tuple[SchemaDesign, dict[str, Any]]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    revisions: list[dict[str, Any]] = []
    used_keys: set[str] = set()
    for schema_path in sorted(schema_lookup):
        design, schema = schema_lookup[schema_path]
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        if not design.examples_dir.is_dir():
            continue
        for example_path in sorted(design.examples_dir.glob("*.json")):
            examples = json.loads(example_path.read_text(encoding="utf-8"))
            for index, content in enumerate(examples.get("valid", []), start=1):
                errors = list(validator.iter_errors(content))
                if errors:
                    detail = "; ".join(error.message for error in errors)
                    raise ValueError(
                        f"Invalid valid example {example_path} at index {index - 1}: {detail}"
                    )
                logical_key = f"{example_path.stem}.{index:03}"
                if logical_key in used_keys:
                    raise ValueError(f"Duplicate generated logical_key: {logical_key}")
                used_keys.add(logical_key)
                record_id = str(uuid.uuid5(NAMESPACE, f"urn:das:seed:record:{logical_key}"))
                revision_id = str(uuid.uuid5(NAMESPACE, f"urn:das:seed:revision:{logical_key}:1"))
                records.append(
                    {
                        "record_id": record_id,
                        "origin_platform_id": None,
                        "origin_product_id": None,
                        "record_type": design.record_type,
                        "feature_domain": design.feature_domain,
                        "logical_key": logical_key,
                    }
                )
                revisions.append(
                    {
                        "revision_id": revision_id,
                        "record_id": record_id,
                        "schema_id": str(uuid.uuid5(NAMESPACE, schema["$id"])),
                        "revision_no": 1,
                        "content_json": content,
                        "change_reason": "JSON Schema 設計の正常例から生成",
                    }
                )
    return records, revisions


def _table_names(er_design: Path) -> set[str]:
    content = er_design.read_text(encoding="utf-8")
    diagram = re.search(r"```mermaid\s+erDiagram(.*?)```", content, flags=re.DOTALL)
    if diagram is None:
        raise ValueError(f"No ER diagram found in {er_design}")
    return set(re.findall(r"^\s{4}([A-Z][A-Z0-9_]*)\s*\{", diagram.group(1), flags=re.MULTILINE))


def _master_sample(
    table_names: set[str],
    er_design: Path,
    schema_lookup,
):
    system_example_file = None
    schema = None
    for design, candidate_schema in schema_lookup.values():
        candidate_example = design.examples_dir / "sys1.system.json"
        if design.record_type == "ARTIFACT" and candidate_example.is_file():
            schema = candidate_schema
            system_example_file = candidate_example
            break
    if schema is None or system_example_file is None:
        raise ValueError("A registered ARTIFACT schema and sys1.system example are required")
    sample_schema_id = str(uuid.uuid5(NAMESPACE, schema["$id"]))
    system_example = json.loads(system_example_file.read_text(encoding="utf-8"))["valid"][0]

    ids = SAMPLE_IDS
    master = {
        "CUSTOMER": [{"customer_id": ids["customer_id"], "name": "サンプル顧客"}],
        "PLATFORM": [{"platform_id": ids["platform_id"], "name": "サンプルプラットフォーム"}],
        "PLATFORM_VERSION": [
            {
                "platform_version_id": ids["platform_version_id"],
                "platform_id": ids["platform_id"],
                "version_label": "1.0.0",
                "released_at": "2026-01-01T00:00:00Z",
            }
        ],
        "PRODUCT": [
            {
                "product_id": ids["product_id"],
                "customer_id": ids["customer_id"],
                "base_platform_version_id": ids["platform_version_id"],
                "name": "サンプル製品",
            }
        ],
        "PRODUCT_VERSION": [
            {
                "product_version_id": ids["product_version_id"],
                "product_id": ids["product_id"],
                "version_label": "1.0.0",
                "released_at": "2026-02-01T00:00:00Z",
            }
        ],
        "CONTENT_RECORD": [
            {
                "record_id": ids["record_id"],
                "origin_platform_id": None,
                "origin_product_id": None,
                "record_type": "ARTIFACT",
                "feature_domain": None,
                "logical_key": "sample.master.system",
            }
        ],
        "CONTENT_REVISION": [
            {
                "revision_id": ids["revision_1_id"],
                "record_id": ids["record_id"],
                "schema_id": sample_schema_id,
                "revision_no": 1,
                "content_json": system_example,
                "change_reason": "サンプル初版",
            },
            {
                "revision_id": ids["revision_2_id"],
                "record_id": ids["record_id"],
                "schema_id": sample_schema_id,
                "revision_no": 2,
                "content_json": system_example,
                "change_reason": "サンプル更新",
            },
        ],
        "REVISION_PARENT": [
            {
                "revision_id": ids["revision_2_id"],
                "parent_revision_id": ids["revision_1_id"],
                "relationship": "PREVIOUS",
                "ordinal": 1,
            }
        ],
        "PLATFORM_SCHEMA_BINDING": [
            {"platform_id": ids["platform_id"], "schema_id": sample_schema_id}
        ],
        "PLATFORM_VERSION_CONTENT": [
            {
                "platform_version_id": ids["platform_version_id"],
                "record_id": ids["record_id"],
                "revision_id": ids["revision_1_id"],
            }
        ],
        "PRODUCT_VERSION_CONTENT": [
            {
                "product_version_id": ids["product_version_id"],
                "record_id": ids["record_id"],
                "revision_id": ids["revision_2_id"],
            }
        ],
    }
    expected_tables = table_names - {"JSON_SCHEMA"}
    if set(master) != expected_tables:
        missing = sorted(expected_tables - set(master))
        extra = sorted(set(master) - expected_tables)
        raise ValueError(
            f"Master sample templates do not match {er_design}; missing={missing}, extra={extra}"
        )
    return {table: master[table] for table in sorted(master)}


def build_seed(repository_dir: Path = REPOSITORY_DIR, check: bool = False) -> bool:
    er_design, schema_dir = _read_settings(repository_dir)
    if not er_design.is_file():
        raise FileNotFoundError(f"ER design file not found: {er_design}")
    designs, excluded = _schema_designs(schema_dir, er_design)
    seed_dir = repository_dir / "backend" / "seed"
    schema_rows, schema_lookup = _schema_seed_rows(designs, seed_dir)
    records, revisions = _example_seed_rows(schema_lookup)
    tables = _table_names(er_design)
    master = _master_sample(tables, er_design, schema_lookup)
    generated_examples = {
        "CONTENT_RECORD": records,
        "CONTENT_REVISION": revisions,
    }
    outputs = {
        "00_sample_master.json": master,
        "10_json_schema.json": {"JSON_SCHEMA": schema_rows},
        "20_artifact_examples.json": generated_examples,
    }
    if not check:
        seed_dir.mkdir(parents=True, exist_ok=True)

    matching = True
    for filename, content in outputs.items():
        path = seed_dir / filename
        expected = _json_bytes(content)
        actual = path.read_text(encoding="utf-8") if path.is_file() else None
        if actual != expected:
            matching = False
            if check:
                print(f"OUTDATED {path.relative_to(repository_dir)}")
            else:
                path.write_text(expected, encoding="utf-8")
                print(f"Wrote {path.relative_to(repository_dir)}")
    if excluded:
        print(
            "Excluded Markdown files without JSON Schema design: "
            + ", ".join(str(path.relative_to(repository_dir)) for path in excluded)
        )
    return matching


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate JSON seed files from design documents")
    parser.add_argument(
        "--check", action="store_true", help="Check generated files without writing"
    )
    args = parser.parse_args(argv)
    try:
        matches = build_seed(check=args.check)
    except (FileNotFoundError, ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"Seed generation failed: {exc}", file=sys.stderr)
        return 1
    if args.check and not matches:
        return 1
    print("Seed files match their design sources." if args.check else "Seed files generated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
