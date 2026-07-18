# Release Verification Process

Draftpaper-loop release verification binds the Git tag, package version, workflow skill, workflow contract, release manifest, README versions and built wheel.

## Local Verification

```powershell
python tools/verify_release_tag.py --tag v<version>
python -m pytest --cov=draftpaper_cli --cov-config=.coveragerc --cov-fail-under=65
python -m build --wheel
python tools/verify_install_matrix.py --wheel-dir dist
python tools/verify_wheel_install.py --wheel-dir dist
python tools/scan_secrets.py
```

`tests.yml` runs the full suite on Windows and Linux, four independent install-profile smokes, and a focused macOS control-plane smoke. `tag-build-verify.yml` repeats source identity, contracts, security, build and isolated-wheel verification for a `v*` tag.

The current license is `LicenseRef-Draftpaper-NonCommercial`. The tag workflow verifies a distributable wheel but does not perform a public PyPI release. Any authorized distribution remains a separate, explicit process governed by the project license and third-party notices.
