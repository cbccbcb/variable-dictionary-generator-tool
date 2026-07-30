# 变量字典生成工具

## 项目背景

在信贷风控建模过程中，特征工程代码通常由多个团队、多轮迭代协作完成，变量命名风格不一致、衍生逻辑分散在 Python/SQL 等多类文件中、业务分类依赖人工经验。当模型需要审计、交接或跨团队复用时，缺乏一份统一的、可追溯的变量字典。

本工具解决的核心问题：**从特征工程源码中自动发现变量，追踪衍生链路，生成带业务分类和血缘说明的中文变量字典**。

## 项目目标

1. **自动化变量发现**：扫描 Python/SQL 源码，识别所有输出变量及其赋值逻辑，无需依赖人工维护的变量清单。
2. **血缘链路追溯**：追踪每个变量从原始字段到最终输出的完整加工过程，包括筛选条件、分组维度、聚合方式、时间窗口。
3. **业务化分类**：根据业务场景和数据源，将变量归入合理的一级/二级分类（如收入能力、多头借贷、还款行为），输出业务人员可读的中文说明。
4. **标准化输出**：生成固定格式的 CSV 字典文件，可作为特征治理、模型审计、数据资产管理的标准输入。

## 应用价值

- **模型审计**：每个变量均有代码证据（来源文件、函数、行号），满足合规审计的"可解释、可追溯"要求。
- **特征治理**：统一变量命名和分类标准，消除同名不同义、同义不同名的混乱。
- **团队协作**：新成员可通过字典快速理解现有特征体系，降低知识传递成本。
- **跨场景复用**：支持银行流水、信贷还款、信贷发标、反欺诈、征信等多种业务场景。

## 支持的业务场景

工具不预设固定的分类体系，而是根据项目代码特征和用户协商确定。以下为已支持的场景参考：

- **银行流水**（数据源：银行流水数据）：收入能力、支出结构、余额流出、负债与盈余、多头借贷、交易类别、资产资质、基础信息
- **信贷还款**（数据源：借还款行为数据）：还款行为、逾期行为、额度使用、多头借贷、代扣还款、账龄、基础信息
- **信贷发标**（数据源：借还款行为数据）：账户活跃度、额度使用、授信状态、待还状态、还款质量、营销触达、App行为
- **信贷戳额**（数据源：借还款行为数据）：新老客标识、戳额策略、额度管理、风控标记、客群分层、准入规则
- **反欺诈**（数据源：applist/设备数据）：设备指纹、行为异常、关联网络、身份核验
- **短信风控**（数据源：短信数据）：待补充
- **征信**（数据源：征信报告数据）：待补充

## 项目架构

```text
用户输入（代码路径 + 可选变量清单）
       │
       ▼
┌─────────────────────────┐
│  scan_codebase.py       │  源码扫描 → code_chunks.jsonl
│  index_remote_repo.py   │  远程仓库索引（无需本地 clone）
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│  LLM 工作流             │
│  quick / standard / deep │  三种模式，按项目规模选择
│                         │
│  Step 0: 分类体系协商    │  LLM 根据代码信号推导场景，与用户确认
│  Step 3: 变量发现        │  从代码中解析输出变量（不依赖注释）
│  Step 4: 血缘追溯        │  追踪加工链路 → lineage_facts.jsonl
│  Step 5: 语义标注        │  LLM 生成变量中文名、一二级分类
│  Step 6: 模板替换        │  脚本将窗口占位符替换为实际值
│  Step 7: 生成 CSV        │  合并代码事实与语义标注
└──────────┬──────────────┘
           ▼
┌─────────────────────────┐
│  validate_lineage.py    │  校验字段完整性、去重、证据覆盖率
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

### 工作流模式

| 模式 | 适用场景 | 产出物 |
|---|---|---|
| `quick` | 单文件、直接赋值、简单 SQL | chunks + facts + CSV + 校验报告 |
| `standard` | 多文件、模块可识别（**默认**） | 同 quick |
| `deep` | 大型项目、嵌套模块、>1000变量、需审计 | standard + code_map + 数据准备事实 + 特征发现 + 可选审查 |

### 最终输出

CSV 字典包含 12 列（Python 变量）或 11 列（SQL 变量），核心字段：

变量 | 变量名称 | 一级类别 | 二级类别 | 三级类别 | 来源模块 | 代码语言 | 时间窗口 | 来源函数(Python) / 筛选逻辑(SQL) | 输入字段(Python) / 聚合逻辑(SQL) | 缺失值取值 | 衍生过程

## 示例

`examples/` 目录包含一个端到端的最小示例：

- `demo_income.py` — 简化版收入特征工程脚本（~120行），包含 5 个特征函数，生成 43 个变量
- `demo_lineage_facts.jsonl` — LLM 从代码中提取的血缘事实（13条样本）
- `variable_lineage_dictionary.csv` — 最终输出的变量字典 CSV

字典 CSV 效果如下（前 5 行）：

变量 | 变量名称 | 一级类别 | 二级类别 | 来源函数 | 时间窗口 | 衍生过程
---|---|---|---|---|---|---
bank_txn_income_global_sum_7d | 近7天总收入总额 | 收入能力 | 基础统计-求和 | amount_global | 近7天 | 模拟交易数据 -> SimpleIncomeFeatureEngineer -> amount_global(近7天) -> ...
bank_txn_income_global_count_7d | 近7天总收入笔数 | 收入能力 | 基础统计-次数 | amount_global | 近7天 | 模拟交易数据 -> SimpleIncomeFeatureEngineer -> amount_global(近7天) -> ...
bank_txn_income_Wages_sum_7d | 近7天工资收入总额 | 收入能力 | 基础统计-求和 | amount_by_type | 近7天 | 模拟交易数据 -> ... -> amount_by_type(近7天, tag_level2=Wages) -> ...
bank_txn_income_Wages_trend_slope_30d | 近30天工资收入趋势斜率 | 收入能力 | 趋势分析 | trend_slope | 近30天 | 模拟交易数据 -> ... -> trend_slope(近30天) -> ...
bank_txn_income_Wages_latest_vs_3m | 工资收入最新值与近3月均值之比 | 收入能力 | 窗口对比分析 | amount_comparison | 近90天 | 模拟交易数据 -> ... -> amount_comparison -> ...

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
