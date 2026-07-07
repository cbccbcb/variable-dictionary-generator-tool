# Schemas

Use JSONL for intermediate artifacts. Each line must be one valid JSON object.

## code_chunks.jsonl

```json
{
  "chunk_id": "relative/path.py::function::func_name::12-80",
  "file": "relative/path.py",
  "language": "python",
  "symbol_type": "function",
  "symbol_name": "func_name",
  "start_line": 12,
  "end_line": 80,
  "code": "..."
}
```

## feature_discovery.jsonl

```json
{
  "feature": "bank_txn_balance_anomaly_days_14d",
  "feature_template": "bank_txn_balance_anomaly_days_{w}d",
  "feature_is_template": false,
  "source_file": "input/txn_eod.py",
  "source_module": "txn_eod",
  "source_class": "代码中未明确体现",
  "source_function": "_build_balance_series_features",
  "discovery_method": "f-string loop expansion",
  "evidence_chunk_id": "input/txn_eod.py::function::_build_balance_series_features::120-230",
  "evidence_snippet": "out[f\"bank_txn_balance_anomaly_days_{w}d\"] = ..."
}
```

## lineage_facts.jsonl

```json
{
  "feature": "bank_txn_balance_anomaly_days_14d",
  "source_file": "input/txn_eod.py",
  "source_module": "txn_eod",
  "source_class": "代码中未明确体现",
  "source_function": "_build_balance_series_features",
  "input_fields": ["balance", "balance_date"],
  "filter_conditions": ["balance_date within window"],
  "groupby_keys": [],
  "aggregation_method": ["sum"],
  "calculation_expression": "sum(is_balance_anomaly)",
  "time_window": "14",
  "time_window_unit": "d",
  "upstream_features": [],
  "business_conditions": ["代码中未明确体现"],
  "evidence_chunk_id": "input/txn_eod.py::function::_build_balance_series_features::120-230",
  "evidence_snippet": "out[f\"bank_txn_balance_anomaly_days_{w}d\"] = int(slc['is_balance_anomaly'].sum())",
  "confidence_level": "high",
  "confidence_reason": "变量赋值和计算表达式在同一代码块中明确出现"
}
```

Required fields for `lineage_facts.jsonl`:

- `feature`
- `source_file`
- `source_module`
- `source_function`
- `input_fields`
- `filter_conditions`
- `aggregation_method`
- `calculation_expression`
- `time_window`
- `time_window_unit`
- `evidence_chunk_id`
- `evidence_snippet`
- `confidence_level`
- `confidence_reason`

Use `代码中未明确体现` or `根据变量名推测` instead of empty strings when information is uncertain.
