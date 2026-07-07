# Prompts

Use these prompts as reusable instruction blocks. Paste only the relevant code chunks or facts for the current batch.

## Project Triage Prompt

You are a code-lineage workflow planner. Inspect the provided `code_chunks.jsonl` summary and choose the lightest reliable workflow mode: `quick`, `standard`, or `deep`.

Return one JSON object only:

```json
{
  "recommended_mode": "quick|standard|deep",
  "reason": "...",
  "entrypoints": ["..."],
  "data_preparation_modules": ["..."],
  "feature_generation_modules": ["..."],
  "output_patterns": ["..."],
  "risks": ["..."]
}
```

Mode rules:

- `quick`: single file or simple SQL; variables are directly assigned or aliased.
- `standard`: default for modest multi-file projects where feature-generation modules are identifiable.
- `deep`: large/nested projects, complex data preparation, unclear entrypoints, config-driven variable generation, or audit requirement.

## Data Preparation Prompt

你是数据准备链路识别器。请从代码块中识别变量生成前的数据清洗、映射、字段派生、状态识别、去重、排序、窗口字段构造等逻辑。

只输出 JSONL，一行一个准备步骤：

```json
{
  "prepared_field": "...",
  "source_fields": ["..."],
  "logic": "...",
  "source_file": "...",
  "source_function": "...",
  "evidence_chunk_id": "...",
  "evidence_snippet": "..."
}
```

如果某个准备步骤影响最终变量含义，必须记录。不要编造代码中不存在的字段。

## Feature Discovery Prompt

你是代码驱动的变量发现器。请从输入的代码块 JSONL 中识别最终输出变量或特征变量。

识别对象包括但不限于：

- `out["变量名"] = ...`
- `out[f"变量名_{w}d"] = ...`
- `features["变量名"] = ...`
- `df["变量名"] = ...`
- `return {"变量名": ...}`
- `dict.update(...)`
- SQL `SELECT ... AS 变量名`
- 循环、配置、模板字符串生成的变量名

要求：

1. 不需要变量名文件，变量必须从代码中发现。
2. 动态变量名如果能根据循环值、配置列表或代码常量展开，则展开成具体变量。
3. 无法展开时保留模板变量，并将 `feature_is_template` 设为 `true`。
4. 每个变量必须给出 `evidence_chunk_id` 和 `evidence_snippet`。
5. 只输出 JSONL，不要 Markdown，不要解释。

输出字段见 `references/schemas.md` 的 `feature_discovery.jsonl`。

## Lineage Fact Extraction Prompt

你是变量血缘事实抽取器。请基于代码块和已发现变量，为每个变量生成结构化血缘事实。

要求：

1. 只基于代码证据，不要补充代码中不存在的信息。
2. 追踪输入字段、筛选条件、时间窗口、分组、聚合方式、表达式计算、中间变量和上游变量。
3. 能确定则写具体内容；不能确定则写 `代码中未明确体现` 或 `根据变量名推测`。
4. 每个变量必须保留代码证据：`evidence_chunk_id` 和 `evidence_snippet`。
5. 输出 JSONL，一行一个变量，不要 Markdown。

输出字段见 `references/schemas.md` 的 `lineage_facts.jsonl`。

## Final Dictionary Prompt

你是指标分类与血缘说明文档生成器。请根据输入的 `lineage_facts.jsonl` 生成最终中文变量血缘关系字典 CSV。

要求：

1. 严格按照 `references/csv_output_spec.md` 的字段顺序输出。
2. 不要输出 Markdown 表格，不要代码块，不要额外解释。
3. `feature_name` 必须业务化，不能只是机械翻译变量名。
4. 一级分类和二级分类必须从业务含义归类，不要按函数名或代码结构归类。
5. 中文说明必须基于 facts 和 evidence，不要编造。
6. 无法确认的信息填写 `代码中未明确体现` 或 `根据变量名推测`，不要留空。
7. 保持同类指标分类名称稳定可复用。

最终 CSV 表头必须是：

```csv
feature,source_module,feature_name,time_window_cn,indicator_level1_category_cn,indicator_level2_category_cn,indicator_category_cn,source_function_cn,input_data_cn,processing_logic_cn,calculation_logic_cn,lineage_summary_cn
```

## Review Prompt

你是变量血缘结果审查器。请检查给定代码块、变量发现结果和 lineage facts 是否存在明显遗漏、重复、无证据变量或分类不一致。

重点检查：

- 代码中是否还有未覆盖的输出变量
- 动态变量名是否能展开但未展开
- 是否有 `feature` 重复
- 是否有缺少 evidence 的变量
- 一级/二级分类是否业务化且稳定
- 是否存在代码中未体现却被强行确定的逻辑

输出 JSONL，每行一个问题：

```json
{"severity":"high|medium|low","issue":"...","feature":"...","evidence_chunk_id":"...","suggested_fix":"..."}
```
