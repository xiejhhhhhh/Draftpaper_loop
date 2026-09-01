# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

"""Astronomy/time-domain data-role and Chinese terminology extensions."""

from __future__ import annotations


DATA_ROLE_ALIASES = {
    "formal_event_manifest": "formal_event_manifest",
    "section25_formal_event_manifest": "formal_event_manifest",
    "acceptance_report": "data_acceptance_report",
    "section25_acceptance_report": "data_acceptance_report",
    "data_acceptance_report": "data_acceptance_report",
    "spectrum_file_inventory": "spectrum_file_inventory",
    "spectral_fit_features": "spectral_or_remote_sensing_features",
    "physical_spectral_values": "spectral_or_remote_sensing_features",
    "processing_level": "processing_level",
    "lv_version": "processing_level",
    "lv_priority": "processing_level",
}


FILENAME_ROLE_MARKERS = {
    "formal_event_manifest": "formal_event_manifest",
    "acceptance_report": "data_acceptance_report",
    "spectrum_file_inventory": "spectrum_file_inventory",
    "current_tokens": "current_observation_tokens",
    "history_tokens": "history_sequence_tokens",
    "spectral_fit_features": "spectral_or_remote_sensing_features",
}


TERMINOLOGY_ZH_CN = {
    "section25_formal_event_manifest": "Section 25正式事件清单",
    "section25_acceptance_report": "Section 25数据验收报告",
    "current_feature_masks_v3": "v3当前观测特征掩码",
    "current_tokens_v3": "v3当前观测序列",
    "history_feature_masks_v3": "v3历史光变特征掩码",
    "history_tokens_v3": "v3历史光变序列",
    "event_level_samples_v3": "v3事件级样本表",
    "spectral_fit_features_v3": "v3物理能谱拟合特征",
    "spectrum_file_inventory_v3": "v3能谱文件清单",
    "all_post_split": "边界后全事件划分",
    "later_only_split": "仅在边界后出现的源划分",
    "all_post_predictions": "边界后全事件预测",
    "later_only_predictions": "仅在边界后出现源的预测",
    "spectral_context": "物理能谱上下文",
    "physical_spectral_values": "物理能谱参数值",
    "spectral_availability": "能谱可用性",
    "history_availability": "历史光变可用性",
    "processing_level": "产品处理级别",
    "cat_net_counts": "源表净计数",
    "current_observation_transformer": "当前观测 Transformer 编码器",
    "causal_history_transformer": "因果历史光变 Transformer 编码器",
    "physical_spectrum_branch": "物理能谱分支",
    "frozen_time_forward_evaluation": "冻结时间前推评估",
    "later_only_source_evaluation": "边界后新源迁移评估",
    "spectral_availability_only_control": "仅使用能谱可用性的对照",
    "complete_case_physical_value_control": "完整能谱样本的物理参数对照",
    "astronomy time-domain X-ray source classification and machine learning": "天文学中的时域 X 射线源分类与机器学习",
    "Frozen all-post and later-only AGN/XRB performance": "冻结的边界后全事件与边界后新出现源 AGN/XRB 分类性能",
    "Multimodal, history, time-encoding, and spectral-opportunity ablations": "多模态、历史光变、时间编码与能谱可用性消融实验",
    "Calibration and selective AGN/XRB recommendation": "概率校准与选择性 AGN/XRB 分类建议",
    "冻结 all-post 与 later-only AGN/XRB 性能": "冻结边界后全事件与边界后新出现源的 AGN/XRB 分类性能",
    "多模态、历史、时间编码与谱机会消融": "多模态、历史光变、时间编码与能谱可用性消融实验",
    "time-domain": "时域",
    "time-encoding": "时间编码",
    "spectral-opportunity": "能谱可用性",
    "all-post": "全部边界后事件",
    "later-only source subset": "边界后新出现源子集",
    "later-only": "边界后新出现源",
    "current-only": "仅当前观测模型",
    "history-only": "仅历史光变模型",
    "current+history": "当前观测与历史光变融合模型",
    "current+spectrum": "当前观测与能谱融合模型",
    "spectrum": "能谱",
    "spectral availability": "能谱可用性",
    "censored upper-limit": "删失上限",
    "upper-limit": "上限",
    "all-masked": "全掩码",
    "current/history/spectrum": "当前观测、历史光变和能谱",
}


INLINE_TERMINOLOGY_ZH_CN = {
    "current/history/spectrum": "当前观测、历史光变和能谱",
    "current observation Transformer": "当前观测 Transformer 编码器",
    "causal history Transformer": "因果历史光变 Transformer 编码器",
    "later-only source subset": "边界后新出现源子集",
    "current-only": "仅当前观测模型",
    "history-only": "仅历史光变模型",
    "current+history": "当前观测与历史光变融合模型",
    "current+spectrum": "当前观测与能谱融合模型",
    "cadence gap": "采样间隔",
    "upper limit": "上限",
    "later-only": "边界后新出现源",
    "all-post": "全部边界后事件",
    "current": "当前观测",
    "history": "历史光变",
    "spectrum": "能谱",
    "删失上限 事件": "删失上限事件",
    "upper limit 不得伪造": "上限不得伪造",
    "边界后新出现源 子集": "边界后新出现源子集",
    "谱机会": "能谱可用性",
}


PROTECTED_TERMINOLOGY_TOKENS = [
    "EP/WXT",
    "AGN/XRB",
    "AGN",
    "XRB",
    "MJD",
    "Sherpa",
    "nH",
    "PHA",
    "ARF",
    "RMF",
]
