# 成果物JSON Schema設計（SYS.1〜SYS.3）

[er-design.md](../er-design.md) の `CONTENT_REVISION.content_json` に格納する、A-SPICE SYS.1〜SYS.3 成果物のJSON Schemaを定義する。

## 配置と生成

| パス | 内容 |
|---|---|
| `schemas/sys.artifact.schema.json` | 成果物の**単一スキーマ**。`JSON_SCHEMA.schema_json` に登録する対象 |
| `schemas/examples/<種別キー>.json` | 種別ごとの正常例（`valid`）と異常例（`invalid`） |
| `schemas/validate.py` | スキーマの妥当性と examples を検証する（要 `jsonschema` 4.x） |

スキーマを編集したら `python3 design/database/json/schemas/validate.py` を実行する。

## 方針

- JSON Schema draft 2020-12 を使う。`$id` は `urn:das:schema:<schema_key>:<schema_version>`。
- **1レコード = 1成果物**とする。工程（SYS.1など）ではなく、ユースケース1件、アクティビティ図の要素1件、システム要件1件のように分割する。`process` は検索用の属性として持つ。
- `JSON_SCHEMA` へは1行だけ登録する: `schema_key` = `sys.artifact`、`schema_version` = 1（`$id` 末尾の版）、`record_type` = `ARTIFACT`、`feature_domain` = NULL。`CONTENT_REVISION.schema_id` はこの1行を参照する。
- 単一スキーマはルートで `artifact_type` を必須とし、その値（下表）に応じて `allOf` の `if/then` で種別ごとの定義（`$defs` の `<種別キー>`、例: `sys2.use_case`）に切り替える。未定義の `artifact_type` は拒否され、エラーは該当種別の定義についてのみ報告される。
- 種別ごとのローカル定義は `<種別キー>.<名前>` として、共通定義（`Base`、`DataItem` など）はルートの `$defs` に1つだけ格納する。
- 成果物種別を追加・変更するときは、`$defs` の該当定義と `allOf` の分岐、`artifact_type` の `enum` を編集し、対応する examples を追加して `validate.py` を実行する。公開済みスキーマは更新せず、変更時は `$id` の版を上げて新しい行として登録する（整合性ルール8）。
- 図は独立した成果物にせず、モデル要素の成果物から構成する（例: ユースケース図 = ユースケース + アクター）。表示位置だけを `sys.diagram_view` に持たせ、ブラウザ編集（DAS_R19）で再生成しても配置が失われないようにする。
- 状態遷移図とシーケンス図は、状態・遷移・メッセージが図全体で意味を持つため、図1枚（シナリオ1件）を1レコードとする。
- 他の成果物への参照は `{record_id, revision_id?}`（`RecordRef`）。`revision_id` 省略時は、同一バージョン内で採用されたリビジョンを指す。
- 構造上必須の関係は専用フィールド（例: `use_case_ref`、`system_requirement_refs`）で表す。補足的な関係は共通の `traces[]` で、**上流方向のみ**保持する。下流は検索で求める。
- 共通項目（`Base`）は `name`、`description`、`status`、`sources[]`（顧客入力物・不具合などの根拠、Blob参照を含む）、`traces[]`、`attachments[]`。リビジョン番号・変更理由・派生元はDBの列と `REVISION_PARENT` で持つため含めない。

## スキーマ一覧

| 種別キー（`$defs` 名 / examples のファイル名） | `artifact_type` | 1レコードの内容 | 主な参照 |
|---|---|---|---|
| `sys1.stakeholder_requirement` | `STAKEHOLDER_REQUIREMENT` | 利害関係者要求1件 | `system_ref` |
| `sys1.system` | `SYSTEM` | 開発対象システム1件 | `parent_system_ref` |
| `sys1.actor` | `ACTOR` | アクター1件 | `stakeholder_requirement_refs` |
| `sys1.system_boundary` | `SYSTEM_BOUNDARY` | システム境界1件（外部アクターと交換する情報） | `system_ref`, `external_entities[].actor_ref` |
| `sys2.use_case` | `USE_CASE` | ユースケース1件 | `system_ref`, `primary_actor_refs`, `stakeholder_requirement_refs`, `includes`, `extends` |
| `sys2.activity_element` | `ACTIVITY_ELEMENT` | アクティビティ図の要素1件（ACTION, DECISION, FORK等）。出力フローを保持 | `use_case_ref`, `performer_ref`, `next[].target_element_ref`, `next[].interface_spec_ref` |
| `sys2.interface_spec` | `INTERFACE_SPEC` | 端点間の入出力情報1件。`abstraction_level` が `ACTION` / `LOGICAL` / `PHYSICAL` | `source`, `target` |
| `sys2.functional_requirement` | `FUNCTIONAL_REQUIREMENT` | アクティビティ図の要素1つに対する機能要件。入出力と変換仕様（ディシジョンテーブルまたは変換式） | `target_element_ref`, `stakeholder_requirement_refs` |
| `sys2.nonfunctional_requirement` | `NONFUNCTIONAL_REQUIREMENT` | 非機能要件1件（処理性能など、`metric` で定量化） | `stakeholder_requirement_refs`, `scope_refs` |
| `sys2.diagnostic_requirement` | `DIAGNOSTIC_REQUIREMENT` | DIDまたはRID1件。Dcmのコンフィグ内容を決める仕様 | `stakeholder_requirement_refs`, `behavior_ref` |
| `sys2.config_requirement` | `CONFIG_REQUIREMENT` | ダイアグ以外のBSWコンフィグ。BSWモジュール単位の項目と値 | `stakeholder_requirement_refs`, `related_element_refs` |
| `sys3.logical_function` | `LOGICAL_FUNCTION` | 論理機能1件（機能ブロック図のブロック） | `parent_function_ref`, `allocated_requirement_refs`, `allocated_element_refs` |
| `sys3.logical_connector` | `LOGICAL_CONNECTOR` | 内部ブロック図の接続1件（論理機能のポート間をインタフェース仕様で結ぶ） | `owner_function_ref`, `source`, `target`, `interface_spec_ref` |
| `sys3.state_machine` | `STATE_MACHINE` | 状態遷移図1枚 | `owner_function_ref` |
| `sys3.sequence_diagram` | `SEQUENCE_DIAGRAM` | シーケンス図1枚（1シナリオ） | `use_case_ref`, `lifelines[].represents_ref` |
| `sys3.hardware_requirement` | `HARDWARE_REQUIREMENT` | システム要件から分解したハードウェア要件1件 | `system_requirement_refs`, `target_block_refs` |
| `sys3.software_requirement` | `SOFTWARE_REQUIREMENT` | システム要件から分解したソフトウェア要件1件 | `system_requirement_refs`, `target_block_refs` |
| `sys3.physical_block` | `PHYSICAL_BLOCK` | HW／SWの物理ブロック1件（物理ブロック定義図のブロック） | `parent_block_ref`, `allocated_function_refs` |
| `sys3.physical_connector` | `PHYSICAL_CONNECTOR` | 物理内部ブロック図の接続1件 | `owner_block_ref`, `source`, `target`, `interface_spec_ref` |
| `sys3.hsi` | `HSI` | HW/SW間のインタフェース項目（信号）1件 | `hardware_block_ref`, `software_block_ref` |
| `sys.diagram_view` | `DIAGRAM_VIEW` | 図1枚の表示レイアウト | `context_ref`, `nodes[].element_ref` |

## 設計上の取り決め

- アクティビティ図のフローは出力側の要素が `next[]` で保持する。DECISIONは分岐ごとに `guard` が必須。アクション間の入出力は `next[].interface_spec_ref` で参照するインタフェース仕様で定義する。
- インタフェース仕様の端点は `source` / `target` を正とする。`activity_element.next` や各コネクタとの整合はMCPサーバーで検証する。
- 機能要件の変換仕様は `DECISION_TABLE`（規則ごとの `when` 条件のAND結合と `then` の出力、`hit_policy`、`default_then`）または `FORMULA`（式、変数、単位、飽和範囲）。
- ダイアグ要件のDID／RIDは、`diag_kind` に応じて `did` / `rid` を必須とする。項目名はAUTOSAR Dcmのパラメータ（`DcmDspDataType`、`DcmDspDataUsePort` など）に対応させ、セッション・セキュリティレベル・モード条件を `Access` で定義する。
- コンフィグ仕様は、AUTOSARのコンテナパス・パラメータ名・値型・値で表す。`value_type` と `value` の型一致をスキーマで検証する。
- 物理ブロックは `domain`（`HARDWARE` / `SOFTWARE`）に応じて `block_kind` を制限し、`hw_attributes` / `sw_attributes` を排他的に使う。

## スキーマで検証できないこと（MCPサーバーで検証）

- `RecordRef` の参照先の存在、アクセス権、参照先の成果物種別（例: `use_case_ref` が実際にユースケースか）。
- `local_id` 系の整合（`transitions` の状態ID、メッセージのライフラインID、機能要件 `transformations[].output` と `outputs[].name` など）。
- インタフェース仕様の端点とアクティビティ要素の `next`、コネクタ端点とポートの整合。
- 製品バージョン内の必須成果物（例: 機能要件を持たないアクションの検出）。
