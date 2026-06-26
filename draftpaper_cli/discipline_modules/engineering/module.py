# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

from ..base import DataConnectorSpec, DisciplineModule, DisciplineModuleSpec, MethodTemplateSpec


class EngineeringModule(DisciplineModule):
    spec = DisciplineModuleSpec(
        module_id="engineering",
        display_name="Engineering experiment, simulation, and reliability workflow",
        maturity="runnable",
        keywords=["engineering", "sensor", "signal", "finite element", "cfd", "simulation", "control", "reliability", "fatigue"],
        data_roles=["sample_or_component_id", "timestamp_or_step", "measurement", "unit", "boundary_condition", "operating_condition"],
        method_families=["signal_processing_pipeline", "simulation_postprocessing", "reliability_analysis", "control_validation", "uncertainty_quantification"],
        validation_checks=["unit_consistency_check", "boundary_condition_check", "sensitivity_analysis", "mesh_or_sampling_convergence"],
        figure_families=["signal_spectrum", "response_curve", "convergence_plot", "uncertainty_interval"],
        formula_families=["frequency_response", "stress_strain", "reliability_function", "uncertainty_propagation"],
        reviewer_risks=["unit_mismatch", "unstated_boundary_conditions", "no_sensitivity_analysis", "no_convergence_test", "weak_physical_plausibility"],
        data_connectors=[
            DataConnectorSpec("sensor_log_manifest", "Sensor or experimental log manifest", ["local_files", "remote_server"], [], [], ["CSV/TDMS/HDF5 sensor logs or local experiment manifest"], ["csv", "hdf5", "tdms", "json"], genericity_rules=["Record units, calibration state, and sampling rate."]),
            DataConnectorSpec("simulation_output_manifest", "Simulation output manifest", ["local_files", "remote_server"], [], [], ["FEM/CFD/CAE postprocessing outputs"], ["csv", "vtk", "hdf5", "json"], genericity_rules=["Record solver, mesh, timestep, and boundary condition metadata."]),
            DataConnectorSpec("materials_property_database", "Materials or component property database", ["api_access", "public_web_download", "local_files"], [], [], ["Materials Project, NIST, local materials table"], ["json", "csv"], genericity_rules=["Expose material system and property units as parameters."]),
        ],
        method_templates=[
            MethodTemplateSpec("signal_processing_pipeline", "Signal filtering, feature extraction, and spectral analysis", "engineering", "signal_processing_pipeline", ["timestamp_or_step", "measurement", "sampling_rate"], ["operating_condition"], ["numpy", "scipy"], ["numpy", "scipy"], ["signal_feature_table", "spectrum_figure"], ["signal_spectrum", "time_response"], ["frequency_response"], ["sampling_rate_check", "filter_parameter_check"], template_path="method_templates/signal_processing_pipeline/template.py", fixture_paths=["method_templates/signal_processing_pipeline/fixture_signal.csv"], aliases=["FFT", "time series signal"], maturity="runnable"),
            MethodTemplateSpec("simulation_postprocessing", "Simulation postprocessing and convergence diagnostics", "engineering", "simulation_postprocessing", ["simulation_output", "boundary_condition"], ["mesh_size", "time_step"], ["numpy", "pandas"], ["numpy", "pandas"], ["response_table", "convergence_figure"], ["response_curve", "convergence_plot"], ["stress_strain"], ["boundary_condition_check", "convergence_check"], aliases=["FEM", "CFD"]),
            MethodTemplateSpec("reliability_uncertainty_analysis", "Reliability and uncertainty analysis", "engineering", "reliability_analysis", ["measurement", "failure_or_threshold"], ["operating_condition"], ["numpy", "scipy"], ["numpy", "scipy"], ["reliability_table", "uncertainty_figure"], ["uncertainty_interval", "failure_probability"], ["reliability_function", "uncertainty_propagation"], ["sensitivity_analysis", "physical_plausibility_check"], aliases=["fatigue", "UQ"]),
        ],
        review_rule_groups=[
            {"rule_group_id": "unit_boundary_condition_gate", "checks": ["units and boundary/operating conditions must be explicit and consistent"]},
            {"rule_group_id": "convergence_sensitivity_gate", "checks": ["simulation or signal-processing claims require convergence or sensitivity evidence when applicable"]},
            {"rule_group_id": "physical_plausibility_gate", "checks": ["results must be checked against physical constraints or engineering expectations"]},
        ],
    )


MODULE = EngineeringModule()
