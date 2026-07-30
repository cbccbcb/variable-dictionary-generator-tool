# 变量字典生成工具

从特征工程源码中自动发现变量、追踪衍生链路，生成带业务分类和血缘说明的中文变量字典。

## 项目背景

本工具以特征工程源码为主要依据，自动解析 Python/SQL 代码中的输出变量，追踪衍生链路（原始字段 → 筛选 → 分组 → 聚合 → 最终变量），生成可追溯的血缘字典，减少对人工维护变量清单和代码注释的依赖。

## 输出物

最终生成一份 11 列的中文 CSV 变量字典。根据代码语言不同，列略有差异：

**Python 变量：**

```
变量,变量名称,一级类别,二级类别,三级类别,来源模块,代码语言,时间窗口,来源函数,输入字段,缺失值取值,衍生过程
```

**SQL 变量：**

```
变量,变量名称,一级类别,二级类别,三级类别,来源模块,代码语言,时间窗口,筛选逻辑,聚合逻辑,缺失值取值,衍生过程
```

各字段定义详见 [references/csv_output_spec.md](references/csv_output_spec.md)。

## 示例

以下是从 `txn_income_v1_1.py`（银行流水收入特征）生成的真实输出：

```csv
变量,变量名称,一级类别,二级类别,三级类别,来源模块,代码语言,时间窗口,来源函数,输入字段,缺失值取值,衍生过程
bank_txn_income_centrelink_1m_vs_3m,政府福利收入1月与3月均值之比,收入能力,窗口对比分析,收入能力-窗口对比分析,txn_income_v1_1,Python,全历史/无固定窗口,amount_comparison,"流水原始字段[user_id,amount,transaction_date,dr_cr,category,third_party,account_type,balance,bank_account_id] + finv映射表补充字段[tag_level1,tag_level2]",-1000000,流水原始数据 + finv映射 -> SingleApplicationIncomeFeatureEngineer -> amount_comparison(全历史/无固定窗口) -> bank_txn_income_centrelink_1m_vs_3m
bank_txn_income_centrelink_3m_vs_6m,政府福利收入3月与6月均值之比,收入能力,窗口对比分析,收入能力-窗口对比分析,txn_income_v1_1,Python,全历史/无固定窗口,amount_comparison,"流水原始字段[user_id,amount,transaction_date,dr_cr,category,third_party,account_type,balance,bank_account_id] + finv映射表补充字段[tag_level1,tag_level2]",-1000000,流水原始数据 + finv映射 -> SingleApplicationIncomeFeatureEngineer -> amount_comparison(全历史/无固定窗口) -> bank_txn_income_centrelink_3m_vs_6m
bank_txn_income_centrelink_3rdparty_carersbenefits_1m_vs_3m,政府福利收入-护理福利-1月与3月均值之比,收入能力,窗口对比分析,收入能力-窗口对比分析,txn_income_v1_1,Python,全历史/无固定窗口,third_party_amount_comparison,"流水原始字段[user_id,amount,transaction_date,dr_cr,category,third_party,account_type,balance,bank_account_id] + finv映射表补充字段[tag_level1,tag_level2]",-1000000,流水原始数据 + finv映射 -> SingleApplicationIncomeFeatureEngineer -> third_party_amount_comparison(全历史/无固定窗口) -> bank_txn_income_centrelink_3rdparty_carersbenefits_1m_vs_3m
bank_txn_income_centrelink_3rdparty_carersbenefits_3m_vs_6m,政府福利收入-护理福利-3月与6月均值之比,收入能力,窗口对比分析,收入能力-窗口对比分析,txn_income_v1_1,Python,全历史/无固定窗口,third_party_amount_comparison,"流水原始字段[user_id,amount,transaction_date,dr_cr,category,third_party,account_type,balance,bank_account_id] + finv映射表补充字段[tag_level1,tag_level2]",-1000000,流水原始数据 + finv映射 -> SingleApplicationIncomeFeatureEngineer -> third_party_amount_comparison(全历史/无固定窗口) -> bank_txn_income_centrelink_3rdparty_carersbenefits_3m_vs_6m
bank_txn_income_centrelink_3rdparty_carersbenefits_count_14d,近14天政府福利收入-护理福利次数,收入能力,基础统计-次数,收入能力-基础统计-次数,txn_income_v1_1,Python,近14天,third_party_amount,"流水原始字段[user_id,amount,transaction_date,dr_cr,category,third_party,account_type,balance,bank_account_id] + finv映射表补充字段[tag_level1,tag_level2]",-1000000,流水原始数据 + finv映射 -> SingleApplicationIncomeFeatureEngineer -> third_party_amount(近14天) -> bank_txn_income_centrelink_3rdparty_carersbenefits_count_14d
```

完整输出见 [examples/variable_lineage_dictionary.csv](examples/variable_lineage_dictionary.csv)。

## 功能

### 代码来源

| 来源 | 说明 |
|---|---|
| **本地文件夹** | `scripts/scan_codebase.py` 扫描 `.py`、`.sql`、`.yaml`、`.json` |
| **远程 GitHub / GitLab** | `scripts/index_remote_repo.py` 索引，无需 clone 到本地 |

### 语言支持

| 语言 | 识别模式 | CSV 差异列 |
|---|---|---|
| **Python** | `out["var"] = ...`、`features["var"]`、config 驱动循环/模板 | `来源函数`、`输入字段` |
| **SQL** | `CREATE TABLE AS SELECT ... AS var`、CTE 层级识别 | `筛选逻辑`、`聚合逻辑` |

### 工作流模式

| 模式 | 适用场景 | 典型变量数 |
|---|---|---|
| **quick** | 单文件 | < 100 |
| **standard**（默认） | 多文件、特征模块可识别 | 100 ~ 2000 |
| **deep** | 大型仓库、动态变量名、需审计 | > 1000 |

## 分类体系

工具不预设固定分类，而是从代码信号（模块名、变量前缀、数据源、聚合方向）推导候选分类，在 skill 执行时与用户协商确认。以下按数据源列出常见分类概览：

- **银行流水**（`bank_txn_*`）：收入能力、支出结构、余额流出、负债与盈余、多头借贷、交易类别、资产资质、基础信息
- **借还款行为**（`paydebt_*` / `bid_*` / `limit_*` / `owing_*`）：还款行为、逾期行为、账户活跃度、额度使用、额度管理、授信状态、待还状态、还款质量、多头借贷、代扣还款、账龄、营销触达、App行为、新老客标识、客群分层、准入规则、基础信息
- **AppList**（`{cate}\|LG*` / `{cate}\|LI*` / `{cate}\|LU*`）：App行为（在装/安装/更新总览、时间间隔分布、密度持续性爆发度、周末夜间偏好、跨窗口对比）、风控标记（风险共存/叠加/密度）
- **征信报告**（`credit_*` / `query_*`）：账户活跃度、待还状态、还款质量、额度使用、还款金额、授信状态
- **短信数据**（`cnt_*` / `dys_*` / `inst_*` / `amount_*`，按机构类型分层）：账户活跃度、还款金额、全量统计

详细的二级类别和变量示例在 skill 执行时根据实际代码动态确定。

## 项目目标

1. **自动化变量发现**：扫描 Python/SQL 源码，识别输出变量及其赋值逻辑
2. **血缘链路追溯**：追踪每个变量从原始字段到最终输出的完整加工过程（筛选、分组、聚合、时间窗口）
3. **业务化分类**：按数据源和业务场景归入一/二/三级分类，输出业务可读的中文说明
4. **标准化输出**：固定格式 11 列 CSV，可作为特征治理、模型审计、数据资产管理的标准输入

## 目录结构

| 路径 | 说明 |
|---|---|
| `SKILL.md` | 核心工作流（Step 0-8） |
| `references/prompts.md` | LLM 提示词 |
| `references/schemas.md` | 中间产物 JSONL schema |
| `references/csv_output_spec.md` | 最终 CSV 字段规范 |
| `scripts/` | 代码扫描、远程索引、合并、校验 |
| `examples/` | 示例输入脚本 + 2,484 变量真实输出 CSV |
