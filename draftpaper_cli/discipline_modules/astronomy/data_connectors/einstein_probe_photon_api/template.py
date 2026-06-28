# Copyright (c) 2026 Jinray Xie
# Contact: xiejinhui22@mails.ucas.ac.cn
# Source-available for non-commercial use only; commercial use requires written authorization.

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import parse, request


@dataclass(frozen=True)
class PhotonApiConfig:
    base_url: str
    email: str
    password: str


def load_photon_api_config(env: dict[str, str] | None = None) -> PhotonApiConfig:
    """Load API configuration from environment variables only.

    The reusable connector never reads project-local files for credentials.
    Project code may provide a credential loader outside this template.
    """
    values = env or os.environ
    missing = [name for name in ["EP_BASE_URL", "EP_EMAIL", "EP_PASSWORD"] if not values.get(name)]
    if missing:
        raise RuntimeError("Missing Einstein Probe API environment variables: " + ", ".join(missing))
    return PhotonApiConfig(
        base_url=str(values["EP_BASE_URL"]).rstrip("/"),
        email=str(values["EP_EMAIL"]),
        password=str(values["EP_PASSWORD"]),
    )


def build_photon_query(
    *,
    ra: float,
    dec: float,
    start_time: str,
    end_time: str,
    bin_size: int,
    mode: str = "precise",
    arm_flag: str = "true",
) -> dict[str, str]:
    return {
        "ra": f"{float(ra):.8f}",
        "dec": f"{float(dec):.8f}",
        "start_time": start_time,
        "end_time": end_time,
        "bin_size": str(int(bin_size)),
        "mode": mode,
        "arm_flag": arm_flag,
    }


def parse_photon_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize common photon payload shapes into light-curve rows."""
    candidate = payload.get("data", payload)
    if isinstance(candidate, dict):
        for key in ["lc", "light_curve", "lightcurve", "bins", "rows"]:
            if isinstance(candidate.get(key), list):
                candidate = candidate[key]
                break
    if not isinstance(candidate, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in candidate:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "time": item.get("time", item.get("mjd", item.get("t"))),
                "flux": item.get("flux", item.get("rate", item.get("counts"))),
                "flux_error": item.get("flux_error", item.get("rate_error", item.get("err"))),
                "exposure": item.get("exposure", item.get("exp")),
            }
        )
    return rows


def fetch_photon_payload(config: PhotonApiConfig, query: dict[str, str], *, token: str, timeout: int = 60) -> dict[str, Any]:
    url = f"{config.base_url}/photons/api/?{parse.urlencode(query)}"
    req = request.Request(url, headers={"tdic-token": token})
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def write_payload_rows(payload: dict[str, Any], output_json: Path, output_csv: Path) -> dict[str, int]:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = parse_photon_payload(payload)
    header = ["time", "flux", "flux_error", "exposure"]
    with output_csv.open("w", encoding="utf-8", newline="") as handle:
        handle.write(",".join(header) + "\n")
        for row in rows:
            handle.write(",".join("" if row.get(col) is None else str(row.get(col)) for col in header) + "\n")
    return {"row_count": len(rows)}
