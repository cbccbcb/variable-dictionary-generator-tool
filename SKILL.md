---
name: variable-dictionary-generator-tool
description: Generate structured Chinese variable dictionary and lineage documentation directly from source code paths, feature-engineering scripts, SQL, or optional variable lists. Use when the user wants code-driven variable discovery, business classification, time-window identification, lineage facts, and strict CSV output without relying on a fixed Python extractor or variable-name dictionary.
---

# Variable Dictionary Generator Tool

## Purpose

Use this skill to generate an 指标分类与血缘说明文档 from source code. Prefer this skill when the input is a code path, a complex multi-file Python/SQL project, or feature-generation logic with inconsistent naming formats.

The main workflow is LLM-driven: the LLM discovers variables and explains lineage, while scripts only read files, split code into chunks, merge batch outputs, and validate required fields.

## Workflow Modes

Choose the lightest mode that can produce reliable, evidence-backed lineage. If the user specifies a mode, follow it. If not specified, default to `standard`.

| Mode | Use When | Required Chain | Required Outputs |
|---|---|---|---|
| `quick` | Single file, direct feature assignments, simple SQL, or quick exploratory output. | code path -> scan chunks -> LLM extracts lineage facts -> final CSV -> validation | `code_chunks.jsonl`, `lineage_facts.jsonl`, `variable_lineage_dictionary.csv`, `validation_report.json` |
| `standard` | Default. Multi-file or moderately complex projects where variables can still be traced from feature-generation modules. | code path -> scan chunks -> lightweight project triage -> LLM extracts lineage facts -> final CSV -> validation | `code_chunks.jsonl`, `lineage_facts.jsonl`, `variable_lineage_dictionary.csv`, `validation_report.json` |
| `deep` | Large projects, many nested modules, complex data preparation, >1000 variables, unclear entrypoints, or audit requirements. | code path -> scan chunks -> `code_map.json` -> `data_preparation_facts.jsonl` -> `feature_discovery.jsonl` -> `lineage_facts.jsonl` -> final CSV -> review/validation | all standard outputs plus `code_map.json`, `data_preparation_facts.jsonl`, `feature_discovery.jsonl`, optional `review_issues.jsonl` |

## Mode Selection Heuristics

- Use `quick` when the code is a single `.py` or `.sql` file and final variables are visibly assigned by patterns such as `features["x"] = ...`, `out[f"..."] = ...`, or SQL `AS feature`.
- Use `standard` when the input is a folder or several files, but feature generation functions/modules are identifiable after scanning.
- Use `deep` when data preparation strongly affects variable meaning, variables depend on intermediate prepared fields, dynamic feature names are generated across files, or the first pass has low coverage.
- Escalate from `quick` to `standard`, or from `standard` to `deep`, if validation shows missing evidence, many template variables, duplicate/empty features, or poor coverage.

## Core Workflow

1. **Scan and chunk code**
   - Run `scripts/scan_codebase.py` on the user-provided file or directory.
   - Include `.py`, `.sql`, `.yaml`, `.yml`, `.json`, `.toml`, and `.csv` only when useful.
   - Exclude `.git`, virtual environments, cache directories, binary files, and generated outputs.

2. **Select mode**
   - Use the Workflow Modes table above.
   - In `quick` and `standard`, keep project triage internal unless useful to the user.
   - In `deep`, write `code_map.json` and `data_preparation_facts.jsonl` before extracting per-variable facts.

3. **Discover variables and generate lineage facts**
   - Read `references/prompts.md`.
   - For `quick`, use the Lineage Fact Extraction prompt directly on code chunks.
   - For `standard`, first identify likely entrypoints and feature-generation chunks, then use the Lineage Fact Extraction prompt.
   - For `deep`, use Project Triage, Data Preparation, Feature Discovery, and Lineage Fact Extraction prompts in sequence.
   - Recognize patterns such as `out["x"]`, `out[f"x_{w}d"]`, `df["x"]`, `features.update(...)`, `return {...}`, SQL `SELECT ... AS x`, config-driven feature loops, and dynamically generated names.
   - Expand dynamic variables when loop values or config values are visible. If not expandable, keep a template and mark the uncertainty.
   - Ask the LLM to output `lineage_facts.jsonl` using the schema in `references/schemas.md`.
   - Require every variable to include code evidence: `evidence_chunk_id` and `evidence_snippet`.
   - Do not invent logic. Use `代码中未明确体现` or `根据变量名推测` where needed.

4. **Generate the final CSV dictionary**
   - Read `references/csv_output_spec.md`.
   - Generate strict CSV with exactly the required fields and order.
   - The final answer or artifact must not be Markdown when the user asks for the CSV content itself.

5. **Validate**
   - Run `scripts/validate_lineage.py` on the final CSV.
   - Check row count, required columns, duplicate `feature`, empty required values, and optional evidence coverage when facts are available.
   - Fix validation failures before presenting the result.

## Recommended Outputs

Produce these files in `quick` and `standard` mode:

```text
output/code_chunks.jsonl
output/lineage_facts.jsonl
output/variable_lineage_dictionary.csv
output/validation_report.json
```

In `deep` mode, also produce:

```text
output/code_map.json
output/data_preparation_facts.jsonl
output/feature_discovery.jsonl
output/review_issues.jsonl
```

If the user specifies a project name or domain, prefix the outputs accordingly, for example `paydebt_lineage_facts.jsonl`.

## Required Final CSV Columns

The final CSV must contain exactly these columns in this order:

```text
feature,source_module,feature_name,time_window_cn,indicator_level1_category_cn,indicator_level2_category_cn,indicator_category_cn,source_function_cn,input_data_cn,processing_logic_cn,calculation_logic_cn,lineage_summary_cn
```

Load `references/csv_output_spec.md` before generating the final dictionary.

## Operating Rules

- Treat source code as the authority. Do not require a variable-name file.
- If a variable list is provided, use it as an optional coverage target, not as the only source of truth.
- Prefer evidence-backed statements. Every lineage fact should point to a code chunk and snippet.
- Separate facts from explanation: first create structured `lineage_facts.jsonl`, then create the Chinese CSV dictionary.
- Preserve uncertainty explicitly with `代码中未明确体现` or `根据变量名推测`; never leave required fields blank.
- Keep classification business-oriented, not code-oriented. 一级分类 and 二级分类 must describe business meaning or risk behavior.
- For large projects, process chunks in batches and merge outputs with `scripts/merge_jsonl.py`.

## Script Usage

Scan code:

```bash
python3 scripts/scan_codebase.py <code-path> --out output/code_chunks.jsonl
```

Merge batch JSONL:

```bash
python3 scripts/merge_jsonl.py output/batches --out output/lineage_facts.jsonl
```

Validate final CSV:

```bash
python3 scripts/validate_lineage.py output/variable_lineage_dictionary.csv --facts output/lineage_facts.jsonl --report output/validation_report.json
```

## References

- `references/schemas.md`: schemas for code chunks, feature discovery, and lineage facts.
- `references/prompts.md`: prompts for project triage, data preparation, feature discovery, lineage fact extraction, and final dictionary generation.
- `references/csv_output_spec.md`: final CSV field order, field definitions, and formatting rules.
