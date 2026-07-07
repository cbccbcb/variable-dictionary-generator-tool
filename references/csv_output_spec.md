# CSV Output Specification

Generate an 指标分类与血缘说明文档 as strict CSV.

## Required Header

The first row must be exactly:

```csv
feature,source_module,feature_name,time_window_cn,indicator_level1_category_cn,indicator_level2_category_cn,indicator_category_cn,source_function_cn,input_data_cn,processing_logic_cn,calculation_logic_cn,lineage_summary_cn
```

## Field Definitions

### feature

变量英文名。

### source_module

变量来源模块，通常来自源代码文件名、模块名、SQL 脚本名或特征加工脚本名。

### feature_name

变量中文名。要求体现业务含义，不要只是机械翻译英文变量名。

### time_window_cn

时间窗口中文说明，例如 `近14天`、`近168天`。如果没有固定窗口，填写 `全历史/无固定窗口`。如果代码中无法确认，填写 `代码中未明确体现`。

### indicator_level1_category_cn

指标一级分类，即最高层业务主题分类，用来回答“这个变量属于哪类业务能力或风险视角”。分类必须业务化，例如：

- 余额稳定性
- 资金流入流出
- 账户活跃度
- 趋势变化
- 异常波动
- 分布结构
- 收入识别
- 支出行为
- 贷款/还款行为

### indicator_level2_category_cn

指标二级分类，即一级分类下的细分分析方向，用来回答“这个变量具体衡量什么”。例如：

- 余额波动
- 余额趋势
- 入账频率
- 出账集中度
- 异常天数
- 最大回撤
- 贷方入账强度
- 还款稳定性

### indicator_category_cn

指标所属中文细分类。建议采用 `一级业务主题-具体统计方向`，例如：

- 余额-异常波动统计
- 余额-贷方入账统计
- 余额-趋势变化统计
- 交易-借方支出统计

### source_function_cn

来源函数的中文说明，用于解释该变量由哪类特征加工逻辑生成。

### input_data_cn

输入数据字段及含义说明。需要包括原始字段名、字段业务含义、字段参与计算的方式。

### processing_logic_cn

数据加工逻辑说明。需要包括能从代码确认的时间窗口截取、数据筛选、分组、中间字段生成、状态识别、去重、排序等。

### calculation_logic_cn

计算逻辑说明。描述变量如何通过聚合、统计、排序、条件判断或表达式计算得到。

### lineage_summary_cn

一句话血缘摘要，使用：

```text
原始数据 -> 加工处理 -> 计算 -> 输出变量
```

## Classification Rules

1. 一级分类必须有明确业务含义，不要只按技术字段、函数名或代码结构分类。
2. 二级分类必须比一级分类更具体，说明该指标实际衡量的业务行为、风险特征或统计方向。
3. 相似指标应归入相同或相近的一级/二级分类，分类名称要稳定、可复用。
4. `feature_name` 要业务化，能够让业务人员理解变量含义，不要只是直译英文变量名。
5. 时间窗口需要优先从变量名、函数参数、代码逻辑或过滤条件中识别。
6. 血缘说明必须尽量清楚描述原始输入字段、筛选逻辑、时间窗口、分组维度、聚合方式、计算公式、最终输出变量。
7. 如果无法从代码或变量清单中确认具体逻辑，不要强行编造，填写 `根据变量名推测` 或 `代码中未明确体现`。
8. 如果同一变量涉及多个来源字段或多个中间处理步骤，需要在 `processing_logic_cn` 和 `lineage_summary_cn` 中完整说明。

## CSV Formatting Rules

1. 只输出 CSV 内容，不要输出 Markdown 表格。
2. 第一行必须是表头。
3. 每个 `feature` 输出一行。
4. 字段顺序必须严格保持 Required Header 的顺序。
5. 所有字段都必须用英文逗号分隔。
6. 如果字段内容中包含英文逗号、换行或双引号，必须用英文双引号包裹。
7. 双引号内部如果再次出现双引号，需要转义为两个双引号。
8. 不要额外输出解释文字。
9. 不要使用代码块包裹最终 CSV。
10. 不要遗漏任何字段。
11. 无法确认的信息不要留空，统一填写 `代码中未明确体现` 或 `根据变量名推测`。
