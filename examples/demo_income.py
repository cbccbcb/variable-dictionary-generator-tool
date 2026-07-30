# -*- coding: utf-8 -*-
"""
演示：产出一个银行流水-收入能力模块的完整特征结果

直接调用 txn_income_v1_1.py 的 SingleApplicationIncomeFeatureEngineer，
用模拟数据生成全部 2,484 个变量，输出到 variable_lineage_dictionary.csv
供 Excel / Python 用户查看。
"""

import os, sys
import numpy as np
import pandas as pd

# == 演示目标模块（请确保 txn_tool 在 Python path 中） ============
try:
    from txn_tool.txn_income_v1_1 import (
        SingleApplicationIncomeFeatureEngineer,
        income_type_tp_pairs,
        income_type_category_pairs,
    )
except ModuleNotFoundError:
    print("请将 txn_tool 目录放到 PYTHONPATH 或本文件所在目录")
    raise

# == 模拟 182 天交易数据 ============================================
np.random.seed(2024)
SAMPLE_DT = "2025-01-01"
dates = pd.date_range("2024-07-01", "2025-01-01", freq="D")

records = []
for d in dates:
    # 工资 → 每月 15 号
    if d.day == 15:
        records.append({"transaction_date": d, "amount": 5500 + np.random.normal(0, 300),
                        "dr_cr": "credit", "category": "Wages",
                        "tag_level1": "INCOME", "tag_level2": "Wages",
                        "third_party": "Employer Pty Ltd"})
    # 政府福利 → 每两周一次
    if d.day in [1, 15]:
        records.append({"transaction_date": d, "amount": 900 + np.random.normal(0, 60),
                        "dr_cr": "credit", "category": "Centrelink",
                        "tag_level1": "INCOME", "tag_level2": "Centrelink",
                        "third_party": "Centrelink Pension"})
        records.append({"transaction_date": d, "amount": 400 + np.random.normal(0, 30),
                        "dr_cr": "credit", "category": "Family Benefits",
                        "tag_level1": "INCOME", "tag_level2": "Centrelink",
                        "third_party": "Family Benefits"})
        records.append({"transaction_date": d, "amount": 350 + np.random.normal(0, 40),
                        "dr_cr": "credit", "category": "JobSeeker",
                        "tag_level1": "INCOME", "tag_level2": "Centrelink",
                        "third_party": "JobSeeker"})
    # 其他收入 → 偶尔发生
    if np.random.random() < 0.08:
        cats = ["All Other Credits", "External Transfers", "Gambling", "Insurance", "Rent", "Travel"]
        cat = np.random.choice(cats)
        records.append({"transaction_date": d, "amount": np.random.uniform(50, 2000),
                        "dr_cr": "credit", "category": cat,
                        "tag_level1": "INCOME", "tag_level2": "Other Income",
                        "third_party": f"Counterparty {cat}"})
    # 支出（EXPENSE）→ 每天随机消费
    if np.random.random() < 0.7:
        ecat = np.random.choice(["Groceries", "Dining Out", "Utilities", "Transport", "Retail"])
        records.append({"transaction_date": d, "amount": np.random.uniform(10, 300),
                        "dr_cr": "debit", "category": ecat,
                        "tag_level1": "EXPENSE", "tag_level2": ecat,
                        "third_party": f"Shop {ecat}"})

df = pd.DataFrame(records)
df["sample_datetime"] = pd.to_datetime(SAMPLE_DT)
df["transaction_date"] = pd.to_datetime(df["transaction_date"])
df["amount"] = df["amount"].abs()
df["user_id"] = "demo_user"
df["account_type"] = "transaction"
df["bank_account_id"] = "demo_account"
df["text"] = np.nan

print(f"模拟数据: {len(df)} 条交易")

# == 调用实际的特征工程类 ==========================================
engine = SingleApplicationIncomeFeatureEngineer(
    df=df,
    time_windows=[7, 14, 28, 56, 84, 168, 182],
    income_type_tp_pairs=income_type_tp_pairs,
    income_type_category_pairs=income_type_category_pairs,
    already_mapped=True,  # 模拟数据已含 tag_level1/tag_level2
)

out = engine.generate_all_features()
print(f"生成特征: {out.shape[1] - 2} 个变量")  # 减去 user_id/sample_datetime

# == 转置输出，方便阅读 ============================================
feature_cols = [c for c in out.columns if c not in ("user_id", "sample_datetime")]
long = out[feature_cols].T.reset_index()
long.columns = ["变量", "值"]

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "variable_lineage_dictionary.csv")
long.to_csv(OUT_PATH, index=False, encoding="utf-8-sig")
print(f"已保存到 {OUT_PATH}")
print(f"\n前 10 个变量预览：")
print(long.head(10).to_string(index=False))
