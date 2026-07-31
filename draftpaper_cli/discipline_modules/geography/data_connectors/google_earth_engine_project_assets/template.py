"""Generic Google Earth Engine project-asset registry connector."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def _write_outputs(output_dir: Path, *, project_id: str, asset_root: str, assets: list[dict[str, Any]]) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    registry_json = output_dir / "gee_asset_registry.json"
    registry_csv = output_dir / "gee_asset_registry.csv"
    payload = {
        "schema_version": "draftpaper.gee_asset_registry.v1",
        "project_id": project_id,
        "asset_root": asset_root,
        "asset_count": len(assets),
        "credential_policy": "credentials handled by the Earth Engine client and never serialized",
        "assets": assets,
    }
    registry_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    with registry_csv.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["asset_id", "asset_name", "asset_type", "update_time"])
        writer.writeheader()
        for asset in assets:
            asset_id = str(asset.get("id") or asset.get("name") or "")
            writer.writerow(
                {
                    "asset_id": asset_id,
                    "asset_name": asset_id.rsplit("/", 1)[-1],
                    "asset_type": asset.get("type"),
                    "update_time": asset.get("updateTime"),
                }
            )
    return {
        "status": "written",
        "asset_count": len(assets),
        "registry_json": str(registry_json),
        "registry_csv": str(registry_csv),
    }


def list_live_assets(*, project_id: str, asset_root: str, page_size: int = 1000) -> list[dict[str, Any]]:
    import ee

    ee.Initialize(project=project_id)
    assets: list[dict[str, Any]] = []
    next_page_id: str | None = None
    while True:
        request: dict[str, Any] = {"parent": asset_root, "pageSize": int(page_size)}
        if next_page_id:
            request["pageToken"] = next_page_id
        response = ee.data.listAssets(request)
        assets.extend(response.get("assets", []))
        next_page_id = response.get("nextPageToken")
        if not next_page_id:
            return assets


def prepare_data_connector(*, output_dir: Path, parameters: dict[str, Any] | None = None) -> dict[str, Any]:
    params = dict(parameters or {})
    project_id = str(params.get("project_id") or "")
    asset_root = str(params.get("asset_root") or (f"projects/{project_id}/assets" if project_id else ""))
    if not project_id or not asset_root:
        return {
            "connector_id": "google_earth_engine_project_assets",
            "status": "template_ready_for_project_binding",
            "required_parameters": ["project_id", "asset_root"],
            "output_dir": str(output_dir),
        }
    assets = list_live_assets(project_id=project_id, asset_root=asset_root, page_size=int(params.get("page_size") or 1000))
    return _write_outputs(output_dir, project_id=project_id, asset_root=asset_root, assets=assets)


def build_template_plan(context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "connector_id": "google_earth_engine_project_assets",
        "status": "plan_ready",
        "parameter_keys": sorted(str(key) for key in (context or {}).keys()),
        "credential_handling": "credential payloads are absent from context and outputs",
    }


def run_template(output_dir: str | Path, fixture_path: str | Path | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    output = Path(output_dir)
    if fixture_path:
        fixture = json.loads(Path(fixture_path).read_text(encoding="utf-8-sig"))
        return _write_outputs(
            output,
            project_id=str(fixture.get("project_id") or "FIXTURE_PROJECT"),
            asset_root=str(fixture.get("asset_root") or "projects/FIXTURE_PROJECT/assets"),
            assets=list(fixture.get("assets") or []),
        )
    return prepare_data_connector(output_dir=output, parameters=context)
