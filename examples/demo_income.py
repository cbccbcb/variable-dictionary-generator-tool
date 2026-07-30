# -*- coding: utf-8 -*-
"""
演示用简化版收入特征工程脚本。
从交易明细中计算近7/30/90天的工资收入和政府福利收入的基础统计量。

这是 txn_income_v1_1.py 的极简版本，仅保留核心结构用于演示 skill 的变量发现和血缘追溯能力。
"""

import numpy as np
import pandas as pd


class SimpleIncomeFeatureEngineer:
    def __init__(self, df: pd.DataFrame, time_windows=None):
        self.time_windows = sorted(time_windows) if time_windows else [7, 30, 90]
        self.features = {}
        self.df = df.copy()
        self._prepare_data()

    def _prepare_data(self):
        df = self.df.copy()
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce").abs()
        df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce")
        df["sample_datetime"] = pd.to_datetime(df["sample_datetime"], errors="coerce")
        df["trac_days"] = (df["sample_datetime"].dt.floor("D") - df["transaction_date"].dt.floor("D")).dt.days
        df = df[df["trac_days"] >= 0].copy()

        # 按 tag_level2 标出不同收入类型
        self.wages_df = df[df["tag_level2"] == "Wages"].copy()
        self.centrelink_df = df[df["tag_level2"] == "Centrelink"].copy()
        self.other_income_df = df[df["tag_level2"] == "Other Income"].copy()
        self.df = df

    # ===== 1) 全局收入统计 =====
    def amount_global(self):
        features = {}
        for window in self.time_windows:
            wdf = self.df[self.df["trac_days"] <= window]
            if len(wdf) > 0:
                features[f"bank_txn_income_global_sum_{window}d"] = float(wdf["amount"].sum())
                features[f"bank_txn_income_global_count_{window}d"] = float(wdf["amount"].count())
                features[f"bank_txn_income_global_mean_{window}d"] = float(wdf["amount"].mean())
                features[f"bank_txn_income_global_max_{window}d"] = float(wdf["amount"].max())
                features[f"bank_txn_income_global_cv_{window}d"] = float(wdf["amount"].std() / wdf["amount"].mean()) if wdf["amount"].mean() > 0 else np.nan
            else:
                for stat in ["sum", "count"]:
                    features[f"bank_txn_income_global_{stat}_{window}d"] = 0.0
                for stat in ["mean", "max", "cv"]:
                    features[f"bank_txn_income_global_{stat}_{window}d"] = np.nan
        self.features.update(features)
        return features

    # ===== 2) 按收入类型统计 =====
    def amount_by_type(self):
        features = {}
        income_types = {"Wages": self.wages_df, "Centrelink": self.centrelink_df}
        for window in self.time_windows:
            for itype, idf in income_types.items():
                wdf = idf[idf["trac_days"] <= window]
                if len(wdf) > 0:
                    features[f"bank_txn_income_{itype}_sum_{window}d"] = float(wdf["amount"].sum())
                    features[f"bank_txn_income_{itype}_count_{window}d"] = float(wdf["amount"].count())
                    features[f"bank_txn_income_{itype}_mean_{window}d"] = float(wdf["amount"].mean())
                else:
                    features[f"bank_txn_income_{itype}_sum_{window}d"] = 0.0
                    features[f"bank_txn_income_{itype}_count_{window}d"] = 0.0
                    features[f"bank_txn_income_{itype}_mean_{window}d"] = np.nan
        self.features.update(features)
        return features

    # ===== 3) 工资收入趋势 =====
    def trend_slope(self):
        features = {}
        for window in self.time_windows:
            for itype, idf in [("Wages", self.wages_df)]:
                wdf = idf[idf["trac_days"] <= window]
                if len(wdf) >= 2:
                    daily = wdf.groupby("transaction_date")["amount"].sum().sort_index().reset_index()
                    x = (daily["transaction_date"] - daily["transaction_date"].min()).dt.days.values.astype(float)
                    y = daily["amount"].values.astype(float)
                    slope = np.polyfit(x, y, 1)[0]
                    features[f"bank_txn_income_{itype}_trend_slope_{window}d"] = float(slope)
                else:
                    features[f"bank_txn_income_{itype}_trend_slope_{window}d"] = np.nan
        self.features.update(features)
        return features

    # ===== 4) 收入占比 =====
    def ratio(self):
        features = {}
        income_types = {"Wages": self.wages_df, "Centrelink": self.centrelink_df}
        for window in self.time_windows:
            wdf = self.df[self.df["trac_days"] <= window]
            total = float(wdf["amount"].sum()) if len(wdf) > 0 else 0.0
            for itype, idf in income_types.items():
                wdf_type = idf[idf["trac_days"] <= window]
                type_sum = float(wdf_type["amount"].sum()) if len(wdf_type) > 0 else 0.0
                if total > 0 and type_sum > 0:
                    features[f"bank_txn_income_{itype}_ratio_{window}d"] = type_sum / total
                elif total > 0:
                    features[f"bank_txn_income_{itype}_ratio_{window}d"] = 0.0
                else:
                    features[f"bank_txn_income_{itype}_ratio_{window}d"] = np.nan
        self.features.update(features)
        return features

    # ===== 5) 收入窗口对比（最新 vs 3个月均值） =====
    def amount_comparison(self):
        features = {}
        for itype, idf in [("Wages", self.wages_df)]:
            latest = idf["amount"].iloc[0] if len(idf) > 0 else 0.0
            wdf_90 = idf[idf["trac_days"] <= 90]
            avg_90 = float(wdf_90["amount"].mean()) if len(wdf_90) > 0 else 0.0
            if avg_90 > 0:
                features[f"bank_txn_income_{itype}_latest_vs_3m"] = latest / avg_90
            else:
                features[f"bank_txn_income_{itype}_latest_vs_3m"] = np.nan
        self.features.update(features)
        return features

    # ===== 输出 =====
    def generate_all_features(self):
        self.amount_global()
        self.amount_by_type()
        self.trend_slope()
        self.ratio()
        self.amount_comparison()
        return pd.DataFrame([self.features])


if __name__ == "__main__":
    # 模拟数据
    np.random.seed(42)
    dates = pd.date_range("2024-01-01", "2024-03-31", freq="D")
    sample_dt = "2024-04-01"

    rows = []
    for d in dates:
        # 工资：每月15号发 5000+噪声
        if d.day == 15:
            rows.append({"transaction_date": d, "amount": 5000 + np.random.normal(0, 200), "tag_level2": "Wages", "sample_datetime": sample_dt})
        # 政府福利：每两周 800+噪声
        if d.day in [5, 20]:
            rows.append({"transaction_date": d, "amount": 800 + np.random.normal(0, 50), "tag_level2": "Centrelink", "sample_datetime": sample_dt})
        # 日常消费：每天随机
        rows.append({"transaction_date": d, "amount": np.random.uniform(20, 200), "tag_level2": "Other Income", "sample_datetime": sample_dt})

    df = pd.DataFrame(rows)
    engine = SimpleIncomeFeatureEngineer(df, time_windows=[7, 30, 90])
    result = engine.generate_all_features()
    print(f"生成 {result.shape[1]} 个变量")
    print(result.T.head(10).to_string())
