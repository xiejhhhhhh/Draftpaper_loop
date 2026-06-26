# Copyright (c) 2026 xiejhhhhhh
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ResearchCodeMiningTests(unittest.TestCase):
    def test_discover_score_extract_writes_candidate_reports_without_copying_source(self) -> None:
        from draftpaper_cli.research_code_mining import (
            discover_research_repos,
            extract_plugin_candidates,
            score_research_repos,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "seed_repos.json"
            seed.write_text(
                json.dumps(
                    [
                        {
                            "full_name": "open-science/geo-raster-workflow",
                            "html_url": "https://github.com/open-science/geo-raster-workflow",
                            "description": "Remote sensing raster processing, zonal statistics, and reproducible figures.",
                            "topics": ["remote-sensing", "geography", "raster", "reproducible-research"],
                            "language": "Python",
                            "stargazers_count": 128,
                            "forks_count": 24,
                            "license": {"spdx_id": "MIT"},
                            "has_readme": True,
                            "has_tests": True,
                            "has_ci": True,
                            "has_requirements": True,
                            "paper": {"doi": "10.0000/example", "venue": "Methods in Ecology and Evolution", "year": 2024},
                            "workflow_signals": ["data", "method", "figure", "notebook"],
                        },
                        {
                            "full_name": "unclear/no-license-script",
                            "html_url": "https://github.com/unclear/no-license-script",
                            "description": "One-off script for a private dataset.",
                            "topics": ["script"],
                            "language": "Python",
                            "stargazers_count": 2,
                            "forks_count": 0,
                            "license": None,
                            "has_readme": False,
                            "has_tests": False,
                            "has_ci": False,
                            "has_requirements": False,
                            "workflow_signals": ["script"],
                        },
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            discovered = discover_research_repos(
                output_root=root,
                discipline="geography",
                query="remote sensing raster workflow",
                from_json=seed,
            )
            discovered_path = Path(discovered["output_file"])
            self.assertTrue(discovered_path.exists())
            self.assertEqual(discovered["repo_count"], 2)

            scored = score_research_repos(input_file=discovered_path, output_root=root)
            scored_path = Path(scored["output_file"])
            ranked = json.loads(scored_path.read_text(encoding="utf-8"))
            self.assertGreater(ranked["repositories"][0]["score"], ranked["repositories"][1]["score"])
            self.assertEqual(ranked["repositories"][0]["license_policy"], "permissive_reusable")
            self.assertEqual(ranked["repositories"][1]["license_policy"], "metadata_only_no_code_reuse")

            extracted = extract_plugin_candidates(input_file=scored_path, output_root=root, top_n=1)
            candidate_root = Path(extracted["candidate_dirs"][0])
            self.assertTrue((candidate_root / "candidate_manifest.json").exists())
            self.assertTrue((candidate_root / "candidate_report.html").exists())
            self.assertFalse((candidate_root / "source").exists())

            manifest = json.loads((candidate_root / "candidate_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_policy"], "candidate_report_only_no_source_copy")
            self.assertEqual(manifest["discipline"], "geography")
            self.assertIn("raster", manifest["candidate_capabilities"])

    def test_cli_commands_chain_research_code_mining_reports(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "repos.json"
            seed.write_text(
                json.dumps(
                    [
                        {
                            "full_name": "open-ml/baseline-ablation",
                            "html_url": "https://github.com/open-ml/baseline-ablation",
                            "description": "Machine learning baseline, ablation study, model evaluation, and figures.",
                            "topics": ["machine-learning", "ablation", "baseline", "scientific-figures"],
                            "language": "Python",
                            "stargazers_count": 75,
                            "forks_count": 10,
                            "license": {"spdx_id": "Apache-2.0"},
                            "has_readme": True,
                            "has_tests": True,
                            "has_ci": False,
                            "has_requirements": True,
                            "workflow_signals": ["data", "model", "metric", "figure"],
                        }
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            discover_cmd = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "discover-research-repos",
                "--output-root",
                str(root),
                "--discipline",
                "machine_learning",
                "--query",
                "baseline ablation",
                "--from-json",
                str(seed),
            ]
            discovered = subprocess.run(discover_cmd, cwd=Path.cwd(), text=True, capture_output=True, check=True)
            discovered_payload = json.loads(discovered.stdout)

            score_cmd = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "score-research-repos",
                "--input",
                discovered_payload["output_file"],
                "--output-root",
                str(root),
            ]
            scored = subprocess.run(score_cmd, cwd=Path.cwd(), text=True, capture_output=True, check=True)
            scored_payload = json.loads(scored.stdout)

            extract_cmd = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "extract-plugin-candidates",
                "--input",
                scored_payload["output_file"],
                "--output-root",
                str(root),
                "--top-n",
                "1",
            ]
            extracted = subprocess.run(extract_cmd, cwd=Path.cwd(), text=True, capture_output=True, check=True)
            extracted_payload = json.loads(extracted.stdout)
            self.assertEqual(extracted_payload["candidate_count"], 1)
            self.assertTrue(Path(extracted_payload["index_html"]).exists())

    def test_cli_inspect_map_bootstrap_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "repo"
            (repo / "src" / "data").mkdir(parents=True)
            (repo / "src" / "models").mkdir(parents=True)
            (repo / "README.md").write_text("# Medicine workflow\n\nCohort survival analysis.", encoding="utf-8")
            (repo / "requirements.txt").write_text("lifelines\npandas\n", encoding="utf-8")
            (repo / "src" / "data" / "load_ehr.py").write_text("PRIVATE_TOKEN = 'not exported'\n", encoding="utf-8")
            (repo / "src" / "models" / "survival_model.py").write_text("def run():\n    pass\n", encoding="utf-8")
            candidate = root / "candidate"
            candidate.mkdir()
            (candidate / "candidate_manifest.json").write_text(
                json.dumps({
                    "candidate_id": "medicine_survival_candidate",
                    "discipline": "medicine",
                    "source_repository": {"full_name": "open/medicine-survival", "license_policy": "permissive_reusable"},
                }),
                encoding="utf-8",
            )

            inspect_cmd = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "inspect-research-repo",
                "--candidate",
                str(candidate),
                "--local-repo",
                str(repo),
                "--output-root",
                str(root),
                "--mode",
                "tree_docs",
            ]
            inspected = subprocess.run(inspect_cmd, cwd=Path.cwd(), text=True, capture_output=True, check=True)
            inspected_payload = json.loads(inspected.stdout)

            map_cmd = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "map-repository-workflow",
                "--inspection",
                inspected_payload["repository_structure"],
                "--output-root",
                str(root),
            ]
            mapped = subprocess.run(map_cmd, cwd=Path.cwd(), text=True, capture_output=True, check=True)
            mapped_payload = json.loads(mapped.stdout)

            bootstrap_cmd = [
                sys.executable,
                "-m",
                "draftpaper_cli.cli",
                "bootstrap-discipline-foundation",
                "--workflow-map",
                mapped_payload["workflow_map"],
                "--output-root",
                str(root),
            ]
            bootstrapped = subprocess.run(bootstrap_cmd, cwd=Path.cwd(), text=True, capture_output=True, check=True)
            bootstrapped_payload = json.loads(bootstrapped.stdout)
            self.assertTrue(Path(bootstrapped_payload["foundation_candidate"]).exists())

    def test_inspect_map_and_bootstrap_foundation_are_metadata_only(self) -> None:
        from draftpaper_cli.research_code_mining import (
            bootstrap_discipline_foundation,
            inspect_research_repo,
            map_repository_workflow,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "fake_finance_repo"
            (repo / "src" / "data").mkdir(parents=True)
            (repo / "src" / "models").mkdir(parents=True)
            (repo / "src" / "figures").mkdir(parents=True)
            (repo / "tests").mkdir()
            (repo / ".github" / "workflows").mkdir(parents=True)
            (repo / "README.md").write_text("# Finance workflow\n\nEvent study and portfolio backtesting.", encoding="utf-8")
            (repo / "requirements.txt").write_text("pandas\nstatsmodels\nmatplotlib\n", encoding="utf-8")
            (repo / "src" / "data" / "download_prices.py").write_text("SECRET_SHOULD_NOT_BE_COPIED = 'private'\n", encoding="utf-8")
            (repo / "src" / "models" / "event_study.py").write_text("def run():\n    pass\n", encoding="utf-8")
            (repo / "src" / "figures" / "plot_abnormal_returns.py").write_text("def plot():\n    pass\n", encoding="utf-8")
            (repo / "tests" / "test_event_study.py").write_text("def test_placeholder():\n    assert True\n", encoding="utf-8")
            (repo / ".github" / "workflows" / "tests.yml").write_text("name: tests\n", encoding="utf-8")

            candidate_dir = root / "candidate"
            candidate_dir.mkdir()
            manifest = {
                "candidate_id": "finance_open_science_event_study",
                "discipline": "finance",
                "source_repository": {
                    "full_name": "open-science/event-study",
                    "html_url": "https://github.com/open-science/event-study",
                    "license_spdx": "MIT",
                    "license_policy": "permissive_reusable",
                },
                "candidate_capabilities": ["data_connector", "baseline_model", "scientific_figure"],
            }
            (candidate_dir / "candidate_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            inspection = inspect_research_repo(candidate=candidate_dir, local_repo=repo, output_root=root)
            inspection_path = Path(inspection["repository_structure"])
            payload = json.loads(inspection_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["source_policy"], "structure_and_docs_only_no_source_copy")
            self.assertGreaterEqual(payload["file_count"], 6)
            self.assertFalse((Path(inspection["inspection_dir"]) / "source").exists())
            inventory_text = Path(inspection["file_inventory"]).read_text(encoding="utf-8")
            self.assertIn("data_connector", inventory_text)
            self.assertIn("method", inventory_text)
            self.assertNotIn("SECRET_SHOULD_NOT_BE_COPIED", inventory_text)

            workflow = map_repository_workflow(inspection_file=inspection_path, output_root=root)
            workflow_payload = json.loads(Path(workflow["workflow_map"]).read_text(encoding="utf-8"))
            self.assertIn("data_connector", workflow_payload["workflow_roles"])
            self.assertIn("method", workflow_payload["workflow_roles"])
            self.assertIn("scientific_figure", workflow_payload["workflow_roles"])
            self.assertIn("validation", workflow_payload["workflow_roles"])

            foundation = bootstrap_discipline_foundation(workflow_map=workflow["workflow_map"], output_root=root)
            foundation_payload = json.loads(Path(foundation["foundation_candidate"]).read_text(encoding="utf-8"))
            self.assertEqual(foundation_payload["status"], "foundation_candidate_written")
            self.assertEqual(foundation_payload["discipline"], "finance")
            self.assertGreaterEqual(len(foundation_payload["data_connector_candidates"]), 1)
            self.assertGreaterEqual(len(foundation_payload["method_template_candidates"]), 1)
            self.assertGreaterEqual(len(foundation_payload["review_rule_candidates"]), 1)
            self.assertEqual(foundation_payload["merge_policy"], "candidate_only_do_not_modify_formal_module")


if __name__ == "__main__":
    unittest.main()
