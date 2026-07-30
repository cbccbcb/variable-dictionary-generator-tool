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

## Variable Discovery Prompt

你是代码驱动的变量发现器。请从输入的代码块中识别**最终输出变量**。

**这是纯粹的代码解析任务。不要查看注释。注释与变量发现无关。**

识别对象：

- SQL: `CREATE TABLE ... AS SELECT` 块中的 `AS variable_name` 别名
- **多阶段 CTAS 层级识别规则**：
  1. 按表名判断 CTAS 块的类型：
     - `_middle_allpro` / `_middle_sampro` → **输出变量聚合层**，提取其 `AS variable_name`
     - `_middle`（不含 allpro/sampro）→ **中间表**，不提取变量，仅记录其中间字段供血缘溯源
     - 不含 `_middle` 的表（如 `variable_behavior_paydebt`）→ **最终合并表**，跳过（`nvl(t1.xxx, -1) as xxx` 与聚合层变量名重复）
  2. **去重规则**：如果同一变量名出现在聚合层和最终合并表，仅保留聚合层版本。
- Python: `out["variable_name"] = ...` / `out[f"prefix_{w}d"] = ...`
- Python: `features["variable_name"] = ...` / `return {"variable_name": ...}`
- 配置驱动的循环、模板字符串生成的变量名

过滤规则（这些不是输出变量，必须排除）：

- 内层子查询的别名 (`t`, `t1`, `t2`, `t3`, `t4`, `t5`, `t6`, `sp`, `sub_table`)
- 分组键字段 (`user_id`, `sample_datetime`)
- 元数据字段 (`tailno`, `dt`, `inserttime`)
- SQL 关键字和类型名 (`decimal`, `integer`, `varchar`, `string`, `bigint`, `double`, `timestamp`)
- 窗口函数别名 (`nrow`, `nrow_desc`, `nrow_asc`, `nrow_desc_deal`, `nrow_desc_prod`, `rnum`)

要求：

1. 不需要变量名文件，变量必须从代码中发现。
2. 动态变量名如果能根据循环值或配置列表展开，则展开成具体变量。
3. 无法展开时保留模板变量，将 `feature_is_template` 设为 `true`。
4. 每个变量必须给出：`feature`, `source_file`, `source_module`, `evidence_chunk_id`, `evidence_snippet`。
5. 只输出 JSONL，不要 Markdown，不要解释。

输出字段见 `references/schemas.md` 的 `feature_discovery.jsonl`。

## Lineage Fact Extraction Prompt

你是变量血缘事实抽取器。请基于代码块和已发现的变量，为每个变量生成结构化血缘事实。

**这是纯粹的代码解析任务。不要依赖注释来填充事实字段。注释在后续步骤中单独处理。**

对每个变量，从代码中追踪：

1. `input_fields`: 参与计算的源表字段（从子查询的 SELECT 和 JOIN 中识别）
2. `filter_conditions`: WHERE 子句中的筛选条件（时间范围、状态过滤等）
3. `groupby_keys`: GROUP BY 中的分组维度
4. `aggregation_method`: 聚合方式（sum/max/min/avg/count/case when 条件聚合）
5. `calculation_expression`: 变量赋值的完整表达式（包含 nvl、if、case when 等）
6. `time_window`: 从变量名后缀（`_l15d`, `_l30d`, `_l90d`, `_l1t` 等）或 WHERE 条件中提取
7. `time_window_unit`: `d`（天）或 `t`（次）
8. `source_file`, `source_module`, `source_function`: 变量所在的代码位置
9. `upstream_features`: 该变量依赖的上游中间字段（在子查询中定义的）
10. `code_language`: `SQL`（.sql 或 Python 内构造的 SQL）或 `Python`（纯 Python 逻辑）
11. `null_value`: **最终输出值的缺失值替换值**。按以下优先级确定：
    1. **最高优先级**：检查最终合并表（表名不含 `_middle`）中 `nvl(聚合变量, default)` → 以 `default` 为准
    2. 其次：检查聚合层表达式中显式的 `else` / `nvl` 默认值
    3. 最后：按聚合函数特征推断（`sum`→0, `max/min/avg`→null, `count`→0）
    - 常见错误：`-min(if(cond, val, 2))` 的内部填充值 `2` 只是 CTAS 聚合层中间值，最终合并表 `nvl(..., -1)` 覆盖后，缺失值取值应为 `-1`
12. `comment_snippet`: 变量行 `-- ` 后的中文注释原文（如 `总 MOP 账户数`），无则填 `null`

**完整性要求（必须遵守）：**

- `evidence_snippet` 必须是**完整**的 SQL 表达式，括号必须平衡。
  如果代码跨多行，向前搜索并合并直到括号平衡。
  正确: `, nvl(avg(CAST(limitecredito_2 AS FLOAT)),-2) AS credit_limit_avg`
  错误: `nvl(avg(CAST(limitecredito_2`（括号不平衡，被截断）
- 对于 Python f-string 中的模板参数（`{day}`, `{stat}` 等），如果能从上下文中确定具体值，必须展开为具体值。
- 跨行的 AS 变量（AS 关键字单独一行），必须向前搜索多行合并直到括号平衡。
- `context_code` 必须至少包含 300 字符的周围代码。

要求：

1. 只基于代码证据，不要补充代码中不存在的信息。
2. 能确定则写具体内容；不能确定则写 `代码中未明确体现`。
3. 每个变量必须保留代码证据：`evidence_chunk_id` 和 `evidence_snippet`。
4. 输出 JSONL，一行一个变量，不要 Markdown。
5. 此阶段输出的 facts 不包含任何中文命名或分类字段——这些在下一阶段由 Chinese Annotation Prompt 处理。

输出字段见 `references/schemas.md` 的 `lineage_facts.jsonl`。

## Pattern Annotation Prompt (MANDATORY — LLM ONLY, NO RULES)

你是变量语义标注器。你需要为**变量模式组**生成命名模板和分类。

**这是 LLM 独有的步骤。不能用 Python if/elif、关键词字典或正则模板替代。你的价值在于理解 context_code 中的 SQL 计算逻辑和 comment_snippet 中的业务含义。**

### 输入

脚本输出的 `patterns_for_llm.json`，按 domain 分组：

```json
{
  "bid": [
    {
      "pattern_id": "bid_succ_bid_days_gap_lXt",
      "representative_var": "bid_succ_bid_days_gap_l1t",
      "num_variables": 1,
      "evidence_snippet": ", max(if(is_deal = 1 and nrow_desc_deal = 1, bid_bid_days_gap_l1t, null)) as bid_succ_bid_days_gap_l1t",
      "context_code": "...10 lines of surrounding SQL...",
      "upstream_tables": ["dwd_mex_loan_biz_loan_apply_case"],
      "comment_snippet": "成功发标距上次发标天数间隔"
    }
  ]
}
```

### 变量名称模板优先级

对每个 pattern 按以下优先级确定 `变量名称模板`：

1. **代码注释（最高优先级）**：如果 `comment_snippet` 非空，直接使用注释（适当精简，去掉过长的括号说明）
2. **context_code 计算逻辑**：理解 SQL 表达式后推断业务含义命名
3. **pattern_id 推断**：从英文变量名推测（最后手段）

### 如何分析 context_code

1. **识别聚合方式**：`max(if(...))` → 条件取最大值；`sum(1)` → 计数；`avg(case when...)` → 条件均值
2. **识别筛选条件**：`if(is_deal = 1, ...)` → 只统计成交；`if(product_type in (50), ...)` → 只统计单期产品
3. **识别窗口函数**：`lag(inserttime)` → 上一条记录的时间；`row_number() over(...)` → 排序
4. **识别字段含义**：`datediff(sample_datetime, loan_time)` → 发标距今天数；`owing_principal / principal` → 待还本金比例

### 输出

为每个 pattern 输出一行 JSON：

```json
{
  "pattern_id": "bid_succ_bid_days_gap_lXt",
  "变量名称模板": "成功发标距上次发标天数间隔",
  "一级类别": "账户活跃度",
  "二级类别": "发标明细",
  "业务说明": "最近一次成功成交(结清)的发标与上一次发标的天数间隔"
}
```

### 变量名称模板规则

- `{TW}`：单窗口占位符（如近7天、近30天、全历史等），脚本自动替换。无时间窗口时不使用。
- `{NUM_TW}`：分子窗口占位符（双窗口比值），如近7天。
- `{DEN_TW}`：分母窗口占位符（双窗口比值），如近30天。
- `{AGG}`：聚合方式占位符（总和/平均值/最大值/最小值/中位数）。
- 纯中文，无英文，4-15字优先但不强制。

### 常见命名错误避免

- 双窗口比值（`_within_X_over_Y` / `_over_`）：体现分子/分母窗口
  ✓ `{NUM_TW}查询次数与{DEN_TW}对应值之比`
  ✗ `{TW}查询次数比`（看不出是两个窗口的比值）
- 查询信贷比（`_over_credit_`）：这是 查询次数/账户数 = 户均查询
  ✓ `{TW}户均查询次数`
  ✗ `值与对应值之比`
- `_not_paidoff`：当前未结清 ✗ 当前结清
- `_never_overdue`：历史无逾期 ✗ 历史逾期
- `_prop`：占全量之比 ✗ 占比

### 分类推断

**一级类别没有默认值，必须根据实际业务场景和数据源协商确定**。从代码中的模块名、变量前缀、数据源类型推导场景，然后参考以下按数据源组织的分类体系：

- **银行流水数据**（变量前缀 `bank_txn_*`）：收入能力、支出结构、余额流出、负债与盈余、多头借贷、交易类别、资产资质、基础信息。二级类别常见：基础统计（求和/均值/最大值/最小值/中位数/次数/标准差/变异系数/最新值）、窗口对比分析、占比分析、增长率分析、趋势分析、波动分析、时间间隔分析、多样性分析。
- **借还款行为数据**（变量前缀 `paydebt_*` / `bid_*` / `limit_*` / `owing_*`）：还款行为、逾期行为、账户活跃度、额度使用、额度管理、授信状态、待还状态、还款质量、多头借贷、代扣还款、账龄、营销触达、App行为、新老客标识、客群分层、准入规则、基础信息。
- **AppList 数据**（变量前缀 `LG*` / `LI*` / `LU*`）：App行为（APP在装/安装/更新总览与标记、各类时间间隔分布、分类计数与占比、安装密度/持续性/爆发度、周末/夜间偏好、观察期特征、跨窗口对比）、风控标记（风险共存/叠加/密度/维度命中数）。
- **短信数据**（变量前缀 `cnt_*` / `dys_*` / `inst_*` / `amount_*`，通常按机构类型 `loan`/`cred`/`loanA`/`levelA` 分层）：账户活跃度（时间间隔/时间跨度/最新短信状态/短信数量/活跃天数/机构数量/活跃波动/活跃峰值/活跃均值/新增机构/机构终态分布/机构聚合统计/短信类型占比/新增机构占比/短信类型交叉比例/时间窗口交叉比例/机构类型交叉比例）、还款金额（短信金额统计）、全量统计（短信总量/时间范围）。
- **征信报告数据**（变量前缀 `credit_*` / `query_*` / `address_*` / `job_*`）：账户活跃度（查询频率/查询多样性/查询机构类型/查询趋势/查询信贷关联/账户数量/机构多样性/账户多样性/账户类型分布/信贷类型分布/抵押情况/账户时长/还款时间/还款活跃度/银行非银行分布/特殊机构/地址/工作/收入/地理一致性/跨域特征/数据完整性）、待还状态（待还总览/还款状态分布/逾期金额/结清未结清逾期无逾期账户/银行非银行待还/信贷类型逾期待还/还款趋势/余额趋势）、还款质量（逾期历史/逾期严重度/逾期时间/逾期趋势/逾期占比/逾期期数/逾期等级分布/连续逾期/还款历史总览/还款历史/银行非银行逾期）、额度使用（额度总览/额度使用总览/结清未结清逾期无逾期账户额度/银行非银行额度/微型金融个人金融额度/额度趋势）、还款金额（应还总览/还款总览/结清逾期无逾期历史逾期账户应还/结清逾期无逾期历史逾期账户还款）、授信状态（风险标记/银行非银行风险标记）。

**必须在生成前和用户确认分类体系**。同类变量必须归入相同的一级/二级分类。
**SQL section comment 优先**：代码中的分组注释（如 `-- 3.1 结清标数`、`-- ----金额专项----`）直接作为二级分类来源。

二级类别：根据业务含义细分，同一 domain 内保持一致

### 变量名解码参考

- `l1t`=最近1次, `l15d`=近15天, `l30d`=近30天, `l90d`=近90天
- `max`=最大值, `min`=最小值, `avg`=平均值, `cnt`=次数, `sum`=总和, `rto`/`rate`=比率
- `bid`=发标, `paydebt`=还款, `owing`=待还, `limit`=额度, `overdue`=逾期
- `succ`=仅成交, `cash`=全产品, `pdl`=单期, `ins`=分期
- `elapsedday`=距今天数, `gap`=间隔, `prop`=比例, `principal`=本金

---

## Annotation Validation Prompt (optional post-hoc check)

你是注释校验器。将 LLM 生成的四个字段与原始代码中的中文注释进行对比。

### 输入

```json
{
  "feature": "bid_hh_l1t",
  "llm_变量名称": "最近1次发标小时",
  "llm_一级类别": "账户活跃度",
  "llm_二级类别": "发标明细",
  "code_comment": "最近1次发标小时"
}
```

### 规则

- 如果 LLM 输出与注释一致或语义等价 → 无需标记
- 如果 LLM 与注释存在实质性差异 → 在 `validation_note` 中记录，但**以 LLM 为准**
- 输出的 annotation 保持不变，注释校验仅用于记录差异

### 输出

```json
{"feature": "...", "validation_note": "LLM: '最近3次发标可用额度使用率', 注释: '额度占用率' — 以LLM为准"}
```
或无差异时输出空行（不记录）。
```

**衍生逻辑分析指南：**

1. **变量名解码**：从英文变量名中识别关键语义元素：
   - 时间窗口：`l1t`=最近1次, `l3t`=最近3次, `l15d`=近15天, `l30d`=近30天, `l90d`=近90天, `l180d`=近180天
   - 统计类型：`max`=最大值/最远, `min`=最小值/最近, `avg`=平均值, `cnt`=计数, `sum`=求和, `prop`/`rate`/`rto`=比例
   - 业务对象：`bid`=发标, `paydebt`=还款, `owing`=待还, `limit`=额度, `elapsedday`=距今天数, `principal`=本金, `overdue`=逾期
   - 产品类型：`cash`=全产品(PDL+分期), `pdl`=单期贷款, `ins`=分期贷款
   - 成交状态：`succ`=成交成功的子集

2. **聚合推断**：从context_code中识别聚合函数（max/min/avg/sum/count）→ 对应计算逻辑和业务含义

3. **来源表推断**：从upstream_table推断数据领域 → 影响一级分类

4. **分类推断**：
   - 涉及发标/申请行为 → 账户活跃度
   - 涉及还款/逾期/提前 → 还款质量
   - 涉及待还/在贷/债务 → 待还状态
   - 涉及额度/授信 → 授信状态 或 额度使用
   - 涉及App启动/点击/时长 → App行为

5. **如果是比例类变量**（rto/rate/prop），`calculation_logic_cn` 中明确分子和分母

要求：
- 不要编造代码中不存在的信息，无法确认时写 `根据衍生逻辑推测`
- `feature_name` 必须业务化，使用中文完整描述变量含义，不能只是机械翻译
- 分类名称保持与已标注变量一致（参考已标注变量的分类体系）
- 每个变量只输出一行 JSON，不要 Markdown 包裹

## Final Dictionary Prompt

你是指标分类与血缘说明文档生成器。请根据 `lineage_facts.jsonl` 和中文标注结果生成最终中文变量字典 CSV。

要求：

1. 严格按照 `references/csv_output_spec.md` 的字段顺序输出。
2. 不要输出 Markdown 表格，不要代码块，不要额外解释。
3. 每个变量输出一行，字段顺序必须正确。
4. 所有字段值用英文逗号分隔，含逗号/换行的内容用双引号包裹。
5. 无法确认的信息填写 `代码中未明确体现` 或 `根据变量名推测`，不要留空。

最终 CSV 表头根据代码语言不同：

SQL 变量（11 列）：
```csv
变量,变量名称,一级类别,二级类别,三级类别,来源模块,代码语言,时间窗口,筛选逻辑,聚合逻辑,缺失值取值,衍生过程
```

Python 变量（11 列）：
```csv
变量,变量名称,一级类别,二级类别,三级类别,来源模块,代码语言,时间窗口,来源函数,输入字段,缺失值取值,衍生过程
```

字段定义详见 `references/csv_output_spec.md`。

## Review Prompt

你是变量血缘结果审查器。请检查给定代码块、变量发现结果和 lineage facts 是否存在明显遗漏、重复、无证据变量或分类不一致。

重点检查：

- 代码中是否还有未覆盖的输出变量
- 动态变量名是否能展开但未展开
- 是否有 `变量` 重复
- 是否有缺少 evidence 的变量
- 一级/二级分类是否业务化且稳定
- 是否存在代码中未体现却被强行确定的逻辑

输出 JSONL，每行一个问题：

```json
{"severity":"high|medium|low","issue":"...","feature":"...","evidence_chunk_id":"...","suggested_fix":"..."}
```
