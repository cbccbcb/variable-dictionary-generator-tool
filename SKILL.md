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

### Step 0: 分类体系协商（变量生成前必须完成）

**在生成变量字典之前，必须先确定一级/二级分类体系。** 默认 7 类不适用于所有业务领域。

1. **读取代码特征推断业务领域**：查看 SQL 表名、变量前缀（`paydebt_` = 还款行为, `bid_` = 发标, `overdue_` = 逾期, `limit_` = 额度）、section comment（`-- 3 结清标/账单数`）、数据源类型（银行流水/借还款行为/applist/短信/征信）。
2. **向用户确认分类体系**：根据推断的场景和数据源，建议一级/二级类别列表。参考以下分类体系（按场景×数据源组织）：

   - 银行流水（数据源：银行流水数据）：收入能力、支出结构、余额流出、负债与盈余、多头借贷、交易类别、资产资质、基础信息
   - 信贷还款（数据源：借还款行为数据）：还款行为、逾期行为、额度使用、多头借贷、代扣还款、账龄、基础信息
   - 信贷发标（数据源：借还款行为数据）：账户活跃度、额度使用、授信状态、待还状态、还款质量、营销触达、App行为
   - 信贷戳额（数据源：借还款行为数据）：新老客标识、戳额策略、额度管理、风控标记、客群分层、准入规则
   - 反欺诈（数据源：applist/设备数据）：设备指纹、行为异常、关联网络、身份核验
   - 短信风控（数据源：短信数据）：待补充
   - 征信（数据源：征信报告数据）：待补充

3. **用户确认后记录分类映射**：一级类别和二级类别一经确认，同类变量必须保持一致。

### Step 1: Scan and chunk code
   - Run `scripts/scan_codebase.py` on the user-provided file or directory.
   - Include `.py`, `.sql`, `.yaml`, `.yml`, `.json`, `.toml`, and `.csv` only when useful.
   - Exclude `.git`, virtual environments, cache directories, binary files, and generated outputs.

### Step 2: Select mode
   - Use the Workflow Modes table above.
   - In `quick` and `standard`, keep project triage internal unless useful to the user.
   - In `deep`, write `code_map.json` and `data_preparation_facts.jsonl` before extracting per-variable facts.

3. **Discover variables from code structure (no comments needed)**
   - Read `references/prompts.md` and use the **Variable Discovery Prompt**.
   - **Variables are found by parsing code, not by reading comments.** Comments are irrelevant at this stage.
   - SQL patterns to recognize:
     - **多阶段 CTAS 层级识别**：一个 SQL 文件可能包含多个连续的 `CREATE TABLE AS SELECT`。按表名优先级识别输出变量层：
       1. 包含 `_middle_allpro` 或 `_middle_sampro` 的表 → **这是输出变量层**，提取其 `AS variable_name`
       2. 只包含 `_middle` 但不含 `allpro`/`sampro` 的表 → 中间表，**跳过**（只提取其中间字段供溯源）
       3. 不含 `_middle` 的最终合并表（如 `variable_behavior_paydebt`）→ **跳过**，其中的 `nvl(t1.xxx, -1) as xxx` 与聚合层变量名相同但表达式不同，会导致变量重复 x2
     - **去重规则**：如果一个变量名在多个 CTAS 块中出现（最终合并表和聚合层），**仅保留聚合层（`_middle_allpro`/`_middle_sampro`）的版本**，跳过最终合并表的 `nvl()` 包装。
     - `CREATE TABLE ... AS SELECT ... nvl(...) AS variable_name` (final output table)
     - `SELECT ... AS variable_name` inside CREATE TABLE blocks
     - CTE/intermediate table aliases should be filtered out — only keep final output columns
   - Python patterns to recognize:
     - `out["variable_name"] = ...` / `out[f"prefix_{w}d"] = ...`
     - `features["variable_name"] = ...`
     - `return {"variable_name": ...}`
     - Config-driven or loop-generated dynamic variable names — expand when values are visible
   - Filter out: intermediate fields, temporary aliases (`t1`, `t2`, `sp`, `sub_table`), key fields (`user_id`, `sample_datetime`), and metadata columns (`tailno`).
   - Output: a list of all discovered output variables with their `evidence_chunk_id`, `evidence_snippet`, and `source_module`.

4. **Trace lineage + Extract variable patterns (no comments needed)**
   - Read `references/prompts.md` and use the **Lineage Fact Extraction Prompt**.
   - For each discovered variable, trace the full derivation chain from the code.
   - Output `lineage_facts.jsonl` using the schema in `references/schemas.md`.
   - **Pattern discovery**: Group variables by their source module and semantic prefix (stripping time window suffixes like `_l15d`, `_s30d`, `_l1t`). Each group shares the same calculation logic — only the time window varies. For each group:
     - Extract 1 representative variable name
     - Extract the `evidence_snippet` (the code line where it is assigned)
     - Extract `context_code` (10 lines surrounding the assignment in the SQL file)
     - Record `upstream_tables` (source data tables)
   - Output `pattern_groups.json` — typically 40-60 groups for a project with 2000+ variables. This is the input payload for Step 5.

5. **LLM generates naming templates — NO RULES, NO SCRIPTS, NO if/elif**
   - Read `references/prompts.md` and use the **Pattern Annotation Prompt**.
   - This step MUST be executed by the LLM in the conversation session. It CANNOT be replaced by a Python script with if/elif branches, keyword dictionaries, or hardcoded mappings.
   - **Input**: `patterns_for_llm.json` — pattern groups organized by domain (bid/paydebt/owing/limit/block/reach/ubt/misc). Each pattern contains:
     - `representative_var`: one sample variable name
     - `evidence_snippet`: the SQL code line where it is assigned
     - `context_code`: surrounding SQL lines (up to 10 lines) showing the calculation logic
     - `upstream_tables`: source data tables
     - `num_variables`: how many variables share this pattern
   - **What LLM does**: Reads the `context_code` to understand the true business meaning of each pattern, not just the variable name. For example:
     - Variable name: `bid_succ_bid_days_gap_l1t`
     - Context shows: `max(if(is_deal = 1 and nrow_desc_deal = 1, bid_bid_days_gap_l1t, null))`
     - LLM understands: this is the days gap between the last successful (settled) bid and the previous bid — so it's "结清天数间隔", not just "发标天数间隔"
   - **Output**: `pattern_templates.json` — for each pattern:
     ```json
     {
       "pattern_id": "bid_cnt_lXd_cash",
       "变量名称模板": "{TW}发标次数",
       "一级类别": "账户活跃度",
       "二级类别": "发标频率",
       "业务说明": "统计用户在指定时间窗口内的发标次数"
     }
     ```
   - `{TW}` is a placeholder — scripts substitute the actual time window in Step 6.
   - For misc/raw fields (e.g. `product_type`, `Is_connected`, `pay_diffmin`), the LLM reads their context_code to assign proper Chinese names and categories — no hardcoded MISC_MAP.
   - LLM processes patterns in domain batches. ~600 patterns are manageable because they share naming conventions across domains.

6. **Apply templates to all variables (script)**
   - Script reads `pattern_templates.json` + `lineage_facts.jsonl`.
   - For each variable, find its matching pattern group, substitute `{TW}` with the actual time window.
   - Generate `annotations.jsonl` with all four fields for every variable.
   - This step is pure data substitution — no LLM, no rules, instant.

7. **Generate the final CSV dictionary**
   - Read `references/csv_output_spec.md`.
   - Merge code-derived facts (Steps 3-4) with LLM-generated pattern templates (Step 5-6) into the final 12-column CSV.

8. **Validate**
   - Run `scripts/validate_lineage.py` on the final CSV.

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

Variables are output with different columns depending on their code language (`代码语言` field: `SQL` or `Python`).

### Common columns (all variables)

```
变量, 变量名称, 一级类别, 二级类别, 三级类别, 来源模块, 代码语言, 时间窗口, 缺失值取值, 衍生过程
```

### SQL-specific columns

After `时间窗口`, insert: `筛选逻辑`, `聚合逻辑`

SQL variables (11 columns total):
```
变量, 变量名称, 一级类别, 二级类别, 三级类别, 来源模块, 代码语言, 时间窗口, 筛选逻辑, 聚合逻辑, 缺失值取值, 衍生过程
```

### Python-specific columns

After `时间窗口`, insert: `来源函数`, `输入字段`

Python variables (11 columns total):
```
变量, 变量名称, 一级类别, 二级类别, 三级类别, 来源模块, 代码语言, 时间窗口, 来源函数, 输入字段, 缺失值取值, 衍生过程
```

### Code language determination

- `.sql` files → `SQL`
- `.py` files that construct SQL strings (contain `SELECT ... FROM ...`) → `SQL`
- `.py` files with pure Python business logic (pandas, numpy, sklearn) → `Python`

### Column mapping

| English | Chinese | Applicability |
|---|---|---|
| `feature` | `变量` | All |
| `feature_name` | `变量名称` | All |
| `indicator_level1_category_cn` | `一级类别` | All |
| `indicator_level2_category_cn` | `二级类别` | All |
| `indicator_category_cn` | `三级类别` | All |
| `source_module` | `来源模块` | All |
| `code_language` | `代码语言` | All |
| `time_window_cn` | `时间窗口` | All |
| `filter_logic` | `筛选逻辑` | SQL only |
| `agg_logic` | `聚合逻辑` | SQL only |
| `source_function_cn` | `来源函数` | Python only |
| `input_data_cn` | `输入字段` | Python only |
| `null_value` | `缺失值取值` | All |
| `lineage_summary_cn` | `衍生过程` | All |

Load `references/csv_output_spec.md` before generating the final dictionary.

## Operating Rules

### Variable Discovery Rules (Steps 3-4: code parsing phase)

- **Code is the only authority for variable existence.** A variable exists if and only if it appears as a final output column in a CREATE TABLE AS SELECT statement (SQL) or an output assignment (Python). Comments are not consulted for discovery.
- If a variable list is provided, use it as an optional coverage target, not as a source of truth — variables found in code that are not in the list are still valid.
- Filter out intermediate artifacts: CTE/internal aliases, `GROUP BY` keys (`user_id`, `sample_datetime`), metadata columns (`tailno`), and non-output expressions.
- Expand dynamic variable names (f-strings, loops, config-driven) when the iteration values are visible in code. Mark unexpandable templates with `_template` suffix.
- Every discovered variable must have code evidence: `evidence_chunk_id` and `evidence_snippet` pointing to the exact assignment line.
- Every lineage fact (input_fields, filters, aggregations, expressions) must be traceable to specific code lines. Use `代码中未明确体现` when code is ambiguous.

- **缺失值取值优先级**（最终输出值，不是中间聚合层的值）：
  1. **最高优先级**：检查最终合并表（不含 `_middle` 的表名）中是否有 `nvl(聚合变量, default_value) as xxx` 覆盖 → 以 `default_value` 为准（如 `-1`）
  2. 其次：检查聚合层表达式中显式的 `else` / `nvl` 默认值
  3. 最后：按聚合函数特征推断（`sum` → 空集返回0, `max/min/avg` → 空集返回null）
  - 常见陷阱：`-min(if(cond, val, 2))` 中内部填充值 `2`（取负后 `-2`）只是 CTAS 聚合层值，最终合并表 `nvl(..., -1)` 覆盖后 → **缺失值取值应为 `-1`**

### Chinese Annotation Rules (Step 5: LLM-only, no scripts)

- **Four fields are LLM-only.** `变量名称`, `一级类别`, `二级类别`, `三级类别` are generated by the LLM in the conversation session by reading `patterns_for_llm.json`. The LLM understands the calculation logic from `context_code` (SQL expressions) and produces naming templates.
- **Forbidden**: Python if/elif branches, keyword-to-Chinese dictionaries (MISC_MAP), regex-based name assembly. Any script that tries to generate these four fields without LLM is a violation.
- **Scripts may extract objective facts**: time_window, aggregation_method, input_fields, source_module, evidence_snippet, context_code, null_value, comment_snippet. These are deterministic code-level facts fed as input to the LLM.
- **Pattern templates are the LLM's output.** Each pattern gets one template with `{TW}` (single window), `{NUM_TW}`/`{DEN_TW}` (double window ratio) placeholders. Step 6 (script) mechanically substitutes time windows — no semantic decisions.
- **Code comments are the primary source.** When `comment_snippet` is available (inline `-- 中文说明`), use it directly as the variable name template. Only fall back to context_code inference when comments are absent.
- **变量名称 formatting**: Concise Chinese phrase. Format `[时间窗口][业务对象][统计方式]`. Pure Chinese. No English, no variable names. No hard truncation.
- Never leave required CSV fields blank. Use `代码中未明确体现` or `根据变量名推测` as last resort.
- 一级分类 and 二级分类 must be business-oriented, consistent across similar variables.
- **分类体系必须根据业务领域协商确定，不可硬编码默认值**。参照 Step 0 的协商流程。
- **Section comment 优先**：SQL 中的分组注释（如 `-- 3.1 结清标数`、`-- 3.2 结清账单数`）是二级分类的直接来源，优先级高于 LLM 自行归类。

### Common naming mistakes to avoid

- `_within_X_over_Y` / `_over_` double-window ratios: use `{NUM_TW}...与{DEN_TW}对应值之比` format. ✗ `查询次数比`
- `_over_credit_` ratios (query count / credit account count): this is "户均查询次数", ✗ "值与对应值之比"
- `_not_paidoff`: label as "未结清", ✗ "结清"
- `_never_overdue`: label as "历史无逾期", ✗ "历史逾期"
- `_prop` proportions: label as "占全量之比", ✗ just "占比"

### Lineage Evidence Quality Rules

- `evidence_snippet` must be a **complete** SQL expression with **balanced parentheses**. If the code spans multiple lines, merge into one complete line. Python f-string template parameters (`{day}`, `{stat}` etc.) must be expanded to concrete values.
  - Correct: `nvl(avg(CAST(limitecredito_2 AS FLOAT)),-2) AS credit_limit_avg`
  - Wrong: `nvl(avg(CAST(limitecredito_2`
- For cross-line SQL (AS keyword alone on a line), search backward and merge lines until parentheses balance.
- `context_code` must include at least 300 characters of surrounding code.

### General Rules

- Separate facts from explanation: first create structured `lineage_facts.jsonl` (Steps 3-4), then add Chinese annotations (Step 5).
- For large projects, process chunks in batches and merge outputs with `scripts/merge_jsonl.py`.

## Script Usage

Scan code:

```bash
python skills/variable-dictionary-generator-tool/scripts/scan_codebase.py <code-path> --out output/code_chunks.jsonl
```

Merge batch JSONL:

```bash
python skills/variable-dictionary-generator-tool/scripts/merge_jsonl.py output/batches --out output/lineage_facts.jsonl
```

Validate final CSV (supports `--format sql` and `--format python`, auto-detects if omitted):

```bash
python skills/variable-dictionary-generator-tool/scripts/validate_lineage.py output/variable_lineage_dictionary.csv --format sql --facts output/lineage_facts.jsonl --report output/validation_report.json
```

## References

- `references/schemas.md`: schemas for code chunks, feature discovery, and lineage facts.
- `references/prompts.md`: prompts for project triage, data preparation, feature discovery, lineage fact extraction, and final dictionary generation.
- `references/csv_output_spec.md`: final CSV field order, field definitions, and formatting rules.
