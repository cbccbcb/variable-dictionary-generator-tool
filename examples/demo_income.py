# -*- coding: utf-8 -*-
"""
演示：从特征工程脚本生成变量字典

这个小脚本模拟了一个简化版收入特征工程模块，生成 35 个典型变量。
运行后会输出变量名列表，对应的分类和中文名见 variable_lineage_dictionary.csv。

无需任何外部依赖（pandas + numpy 即可运行）。
"""

import numpy as np
import pandas as pd

# ============================================================
# 简化的收入特征工程（模拟 txn_income_v1_1.py 的核心结构）
# ============================================================
class SimpleIncomeEngine:
    def __init__(self, df, time_windows=None):
        self.time_windows = time_windows or [7, 30, 90]
        self.features = {}
        self.df = df.copy()

    def _wdf(self, w):
        """窗内数据"""
        mask = self.df["trac_days"] <= w
        return self.df[mask]

    def amount_global(self):
        """全局收入统计 — sum/count/mean/max/cv × 3窗 = 15个变量"""
        for w in self.time_windows:
            wdf = self._wdf(w)
            amt = wdf["amount"]
            self.features[f"bank_txn_income_global_sum_{w}d"] = float(amt.sum())
            self.features[f"bank_txn_income_global_count_{w}d"] = float(amt.count())
            self.features[f"bank_txn_income_global_mean_{w}d"] = float(amt.mean())
            self.features[f"bank_txn_income_global_max_{w}d"] = float(amt.max())
            self.features[f"bank_txn_income_global_cv_{w}d"] = (
                float(amt.std() / amt.mean()) if amt.mean() > 0 else np.nan
            )

    def amount_by_type(self):
        """按收入类型统计 — Wages/Centrelink × sum/count/mean × 3窗 = 18个变量"""
        for w in self.time_windows:
            for itype in ["Wages", "Centrelink"]:
                typedf = self._wdf(w)
                typedf = typedf[typedf["tag_level2"] == itype]
                amt = typedf["amount"]
                self.features[f"bank_txn_income_{itype}_sum_{w}d"] = float(amt.sum()) if len(amt) > 0 else 0.0
                self.features[f"bank_txn_income_{itype}_count_{w}d"] = float(amt.count())
                self.features[f"bank_txn_income_{itype}_mean_{w}d"] = (
                    float(amt.mean()) if len(amt) > 0 else np.nan
                )

    def amount_comparison(self):
        """窗口对比 — latest_vs_3m/1m_vs_3m = 2个变量"""
        self.features["bank_txn_income_Wages_latest_vs_3m"] = self._compare("Wages", "latest", 90)
        self.features["bank_txn_income_Wages_1m_vs_3m"] = self._compare("Wages", 30, 90)

    def _compare(self, itype, short, long_w):
        typedf = self.df[self.df["tag_level2"] == itype]
        if short == "latest":
            num = typedf["amount"].iloc[0] if len(typedf) > 0 else 0
        else:
            num = float(typedf[typedf["trac_days"] <= short]["amount"].mean())
        den = float(typedf[typedf["trac_days"] <= long_w]["amount"].mean())
        return num / den if den > 0 else np.nan

    def generate_all_features(self):
        self.amount_global()
        self.amount_by_type()
        self.amount_comparison()
        return pd.DataFrame([self.features])


# ============================================================
# 模拟数据 + 运行
# ============================================================
np.random.seed(42)
dates = pd.date_range("2024-10-01", "2024-12-31", freq="D")

rows = []
for d in dates:
    # 每月15号工资
    if d.day == 15:
        rows.append({"amount": 5000 + np.random.normal(0, 200),
                     "tag_level2": "Wages",
                     "trac_days": (pd.Timestamp("2025-01-01") - d).days})
    # 每两周Centrelink
    if d.day in [1, 15]:
        rows.append({"amount": 850 + np.random.normal(0, 50),
                     "tag_level2": "Centrelink",
                     "trac_days": (pd.Timestamp("2025-01-01") - d).days})

df = pd.DataFrame(rows)
engine = SimpleIncomeEngine(df)
result = engine.generate_all_features()

print(f"生成 {result.shape[1]} 个变量\n")
for var in sorted(result.columns):
    print(var)
