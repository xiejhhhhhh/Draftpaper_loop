# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from ..base import DataConnectorSpec, DisciplineModule, DisciplineModuleSpec, MethodTemplateSpec


class FinanceModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="finance",
        display_name="Finance and empirical asset-pricing workflow",
        maturity="runnable",
        keywords=["finance", "asset pricing", "portfolio", "return", "volatility", "event study", "factor model"],
        data_roles=["asset_identifier", "timestamp", "price_or_return", "benchmark_return", "event_date", "firm_or_security_metadata"],
        method_families=["event_study", "factor_model", "portfolio_backtest", "volatility_model", "risk_metric"],
        validation_checks=["time_ordered_split", "lookahead_bias_check", "transaction_cost_sensitivity", "out_of_sample_validation"],
        figure_families=["cumulative_abnormal_return", "factor_exposure", "drawdown_curve", "risk_return_frontier"],
        formula_families=["abnormal_return", "factor_regression", "sharpe_ratio", "value_at_risk"],
        reviewer_risks=["lookahead_bias", "survivorship_bias", "data_snooping", "transaction_cost_omission", "weak_out_of_sample_evidence"],
        data_connectors=[
            DataConnectorSpec("market_price_api", "Market price API or downloadable quote table", ["api_access", "public_web_download", "local_files"], ["yfinance"], ["yfinance"], ["Yahoo Finance, Stooq, exchange API, or local OHLCV table"], ["csv", "parquet", "json"], genericity_rules=["Do not hard-code tickers or date windows."]),
            DataConnectorSpec("macro_economic_series", "Macroeconomic time-series data", ["api_access", "public_web_download"], ["pandas_datareader"], ["pandas_datareader"], ["FRED, World Bank, OECD, or local macro table"], ["csv", "json"], genericity_rules=["Expose frequency and country/region as parameters."]),
            DataConnectorSpec("sec_filing_metadata", "Company filing and fundamentals metadata", ["api_access", "public_web_download"], [], [], ["SEC EDGAR or local company fundamentals table"], ["json", "csv", "xbrl"], genericity_rules=["Do not store API credentials or company-specific secrets."]),
        ],
        method_templates=[
            MethodTemplateSpec("event_study", "Event study with abnormal-return windowing", "finance", "event_study", ["price_or_return", "benchmark_return", "event_date"], ["firm_metadata"], ["pandas", "statsmodels"], ["pandas", "statsmodels"], ["event_window_table", "cumulative_abnormal_return_figure"], ["event_window", "cumulative_abnormal_return"], ["abnormal_return", "cumulative_abnormal_return"], ["pre_event_window_check", "benchmark_alignment_check"], template_path="method_templates/event_study/template.py", fixture_paths=["method_templates/event_study/fixture_returns.csv"], aliases=["abnormal return", "CAR"], maturity="runnable"),
            MethodTemplateSpec("factor_model", "Linear factor exposure model", "finance", "factor_model", ["asset_return", "factor_returns"], ["risk_free_rate"], ["pandas", "statsmodels"], ["pandas", "statsmodels"], ["factor_loading_table", "residual_diagnostics"], ["factor_exposure", "residual_diagnostics"], ["factor_regression"], ["time_ordering_check", "heteroskedasticity_check"], aliases=["CAPM", "Fama French"]),
            MethodTemplateSpec("portfolio_backtest", "Portfolio backtest and risk-return diagnostics", "finance", "portfolio_backtest", ["asset_returns", "portfolio_weights"], ["transaction_costs"], ["pandas", "numpy"], ["pandas", "numpy"], ["performance_table", "drawdown_figure"], ["risk_return_frontier", "drawdown_curve"], ["sharpe_ratio", "maximum_drawdown"], ["lookahead_bias_check", "transaction_cost_sensitivity"], aliases=["backtesting", "asset allocation"]),
        ],
        review_rule_groups=[
            {"rule_group_id": "lookahead_bias_gate", "checks": ["features and portfolio weights must be computed using only past information"]},
            {"rule_group_id": "survivorship_bias_gate", "checks": ["universe construction and delisting handling must be stated"]},
            {"rule_group_id": "out_of_sample_finance_gate", "checks": ["claims require time-ordered validation and transaction-cost sensitivity"]},
        ],
    )


MODULE = FinanceModule()
