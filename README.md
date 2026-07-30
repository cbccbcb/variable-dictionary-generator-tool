# 变量字典生成工具

## 项目背景

在信贷风控建模过程中，特征工程代码通常由多个团队、多轮迭代协作完成，变量命名风格不一致、衍生逻辑分散在 Python/SQL 等多类文件中、业务分类依赖人工经验。当模型需要审计、交接或跨团队复用时，缺乏一份统一的、可追溯的变量字典。

本工具解决的核心问题：**从特征工程源码中自动发现变量，追踪衍生链路，生成带业务分类和血缘说明的中文变量字典**。

## 项目目标

1. **自动化变量发现**：扫描 Python/SQL 源码，识别所有输出变量及其赋值逻辑，无需依赖人工维护的变量清单。
2. **血缘链路追溯**：追踪每个变量从原始字段到最终输出的完整加工过程，包括筛选条件、分组维度、聚合方式、时间窗口。
3. **业务化分类**：根据业务场景和数据源，将变量归入合理的一级/二级/三级分类，输出业务人员可读的中文说明。
4. **标准化输出**：生成固定格式的 CSV 字典文件，可作为特征治理、模型审计、数据资产管理的标准输入。

## 核心能力

### 支持多种代码来源

| 来源 | 说明 |
|---|---|
| **本地文件夹** | 通过 `scripts/scan_codebase.py` 扫描，支持 `.py`、`.sql`、`.yaml`、`.json` 文件 |
| **远程 GitHub 仓库** | 通过 `scripts/index_remote_repo.py` 索引，**无需 clone 到本地** |
| **远程 GitLab 仓库** | 同样支持，需指定 `--provider gitlab` |

### 支持多种代码语言

| 语言 | 识别模式 | 输出列差异 |
|---|---|---|
| **Python** | `features["var"] = ...`、`out[f"var_{w}d"] = ...`、字典返回值、config 驱动的循环/模板变量 | 最终 CSV 含 `来源函数`、`输入字段` 列 |
| **SQL** | `CREATE TABLE AS SELECT ... AS variable_name`、CTE 层级识别、`nvl(...) AS var` | 最终 CSV 含 `筛选逻辑`、`聚合逻辑` 列 |

SQL 场景下工具会自动区分多阶段 CTAS：跳过中间表、只提取输出变量层（`_middle_allpro`/`_middle_sampro`），避免最终合并表的 `nvl()` 包装导致变量重复。

### 三种工作流模式，由浅入深

| 模式 | 适用场景 | 典型变量数 | 产出物 |
|---|---|---|---|
| **quick** | 单文件、直接赋值、简单 SQL | < 100 | `code_chunks.jsonl` + `lineage_facts.jsonl` + 字典 CSV + 校验报告 |
| **standard**（默认） | 多文件、特征生成模块可识别 | 100 ~ 2000 | 同 quick |
| **deep** | 大型项目、嵌套模块、动态变量名、需审计 | > 1000 | standard 全部 + `code_map.json` + `data_preparation_facts.jsonl` + `feature_discovery.jsonl` + 可选审查报告 |

模式选择建议：

- 一个 `.sql` 文件 → **quick**
- 一个文件夹 3~5 个 `.py` 模块 → **standard**
- 整个特征工程仓库、12,000+ 变量 → **deep**

### 业务分类体系

工具**不预设固定的分类**，而是从代码中提取信号（模块名、变量前缀、数据源类型、聚合方向），由 LLM 推导候选分类后**与用户协商确认**。

已支持的业务场景参考：

- **银行流水**（数据源：银行流水数据）：收入能力、支出结构、余额流出、负债与盈余、多头借贷、交易类别、资产资质、基础信息
- **信贷还款**（数据源：借还款行为数据）：还款行为、逾期行为、额度使用、多头借贷、代扣还款、账龄、基础信息
- **信贷发标**（数据源：借还款行为数据）：账户活跃度、额度使用、授信状态、待还状态、还款质量、营销触达、App行为
- **信贷戳额**（数据源：借还款行为数据）：新老客标识、戳额策略、额度管理、风控标记、客群分层、准入规则
- **反欺诈**（数据源：applist/设备数据）：设备指纹、行为异常、关联网络、身份核验
- **短信风控**（数据源：短信数据）：待补充
- **征信**（数据源：征信报告数据）：待补充

## 示例

`examples/` 目录包含：

| 文件 | 说明 |
|---|---|
| `demo_income.py` | 简化版收入特征工程脚本，35 个变量，无需外部依赖即可运行 |
| `variable_lineage_dictionary.csv` | skill 对真实项目 `txn_income_v1_1.py` 生成的完整变量字典，2,484 个变量 |

完整字典 CSV 可下载 `examples/variable_lineage_dictionary.csv` 查看，字段说明见上方"最终输出"。

## 项目架构

```text
用户输入（代码路径 / 远程仓库 URL + 可选变量清单）
       │
       ▼
┌─────────────────────────┐
│  scan_codebase.py       │  本地源码扫描 → code_chunks.jsonl
│  index_remote_repo.py   │  远程仓库索引（无需 clone）
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│  LLM 工作流             │
│  quick / standard / deep │
│                         │
│  Step 0: 分类体系协商    │  LLM 推导场景 → 用户确认一级分类
│  Step 1: 代码扫描切块    │  py/sql → code_chunks.jsonl
│  Step 2: 选择工作模式    │  按规模选 quick/standard/deep
│  Step 3: 变量发现        │  解析输出变量（不依赖注释）
│  Step 4: 血缘追溯        │  追踪加工链路 → lineage_facts.jsonl
│  Step 5: 语义标注        │  LLM 生成中文名 + 一/二/三级分类
│  Step 6: 模板替换        │  窗口占位符 → 实际时间窗
│  Step 7: 生成 CSV        │  合并代码事实 + 语义标注
│  Step 8: 校验            │  字段完整性、去重、证据覆盖率
└──────────┬──────────────┘
           ▼
     variable_lineage_dictionary.csv（12列标准输出）
```

### 目录结构

| 路径 | 说明 |
|---|---|
| `SKILL.md` | 核心工作流说明，Step 0-8 完整流程 |
| `references/prompts.md` | LLM 提示词：项目诊断、变量发现、血缘抽取、语义标注 |
| `references/schemas.md` | 中间产物的 JSONL schema 定义 |
| `references/csv_output_spec.md` | 最终 CSV 的字段顺序、定义、格式规范 |
| `scripts/scan_codebase.py` | 扫描本地源码，按函数/类切块输出 JSONL |
| `scripts/index_remote_repo.py` | 索引远程 GitHub/GitLab 仓库，识别变量衍生信号 |
| `scripts/merge_jsonl.py` | 合并分批输出的 JSONL 文件 |
| `scripts/validate_lineage.py` | 校验最终 CSV：字段完整性、重复变量、证据覆盖率 |
| `agents/openai.yaml` | Agent 配置文件 |
| `examples/` | 示例：demo 脚本 + 真实项目的 2,484 变量字典 CSV |

### 最终输出

CSV 字典共有 11 个字段，其中 9 个为两语言通用，2 个根据代码语言不同而不同。

**通用字段（Python 和 SQL 均包含）：**

> 变量 | 变量名称 | 一级类别 | 二级类别 | 三级类别 | 来源模块 | 代码语言 | 时间窗口 | 缺失值取值 | 衍生过程

**Python 特有字段：**

> 来源函数 | 输入字段

**SQL 特有字段：**

> 筛选逻辑 | 聚合逻辑

---

#### Python 变量示例

以 `bank_txn_income_Wages_sum_7d`（近 7 天工资收入总额）为例：

| 字段 | 值 |
|---|---|
| 变量 | `bank_txn_income_Wages_sum_7d` |
| 变量名称 | 近 7 天工资收入总额 |
| 一级类别 | 收入能力 |
| 二级类别 | 基础统计-求和 |
| 三级类别 | 收入能力-基础统计-求和 |
| 来源模块 | txn_income_v1_1 |
| 代码语言 | Python |
| 时间窗口 | 近 7 天 |
| **来源函数** | `amount_by_type`（在 `wdf[tag_level2=='Wages']` 子集上调用 `.sum()`） |
| **输入字段** | `amount`（交易金额）、`trac_days`（距今窗口天数）、`tag_level2`（收入类型标签） |
| 缺失值取值 | `-1000000` |
| 衍生过程 | 流水原始数据 → finv 映射表 → SingleApplicationIncomeFeatureEngineer → amount_by_type(近 7 天) → 变量 |

#### SQL 变量示例

以一个假设的信贷还款 SQL 变量 `paydebt_owing_principal_total_l30d`（近 30 天待还本金总额）为例：

| 字段 | 值 |
|---|---|
| 变量 | `paydebt_owing_principal_total_l30d` |
| 变量名称 | 近 30 天待还本金总额 |
| 一级类别 | 待还状态 |
| 二级类别 | 待还金额 |
| 三级类别 | 待还状态-待还金额 |
| 来源模块 | sql/paydebt_owing.sql |
| 代码语言 | SQL |
| 时间窗口 | 近 30 天 |
| **筛选逻辑** | `loan_time >= sample_datetime - 30d AND owing_principal > 0` |
| **聚合逻辑** | `nvl(sum(owing_principal), 0)` |
| 缺失值取值 | `0` |
| 衍生过程 | dwd_loan_owing 表 → WHERE 近30天 + 待还>0 → sum(本金) → 变量 |

> **差异说明**：Python 变量通过 `来源函数` 和 `输入字段` 描述加工逻辑（代码调用链路）；SQL 变量通过 `筛选逻辑` 和 `聚合逻辑` 描述加工逻辑（WHERE + 聚合函数）。两种表示方式都是直接从代码中提取的原始表达式，不做翻译，保持可追溯性。

## 快速开始

**本地源码扫描：**

```bash
python scripts/scan_codebase.py <源码路径> --out output/code_chunks.jsonl
```

**远程仓库索引（无需 clone）：**

```bash
# GitHub
python scripts/index_remote_repo.py https://github.com/org/repo \
  --out output/derivation_index.json \
  --chunks-out output/remote_code_chunks.jsonl

# GitLab
python scripts/index_remote_repo.py https://gitlab.com/group/project \
  --provider gitlab \
  --out output/derivation_index.json \
  --chunks-out output/remote_code_chunks.jsonl
```

私有仓库需设置 token：`export GITHUB_TOKEN=<token>` 或 `export GITLAB_TOKEN=<token>`

**合并分批输出：**

```bash
python scripts/merge_jsonl.py output/batches --out output/lineage_facts.jsonl
```

**校验最终字典：**

```bash
python scripts/validate_lineage.py output/variable_lineage_dictionary.csv \
  --facts output/lineage_facts.jsonl \
  --report output/validation_report.json
```
