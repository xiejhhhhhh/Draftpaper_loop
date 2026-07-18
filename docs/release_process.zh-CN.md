# 发布验证流程

Draftpaper-loop 会把 Git tag、包版本、workflow skill、workflow contract、release manifest、README 版本和构建后的 wheel 作为同一发布身份进行核验。

## 本地验证

```powershell
python tools/verify_release_tag.py --tag v<version>
python -m pytest --cov=draftpaper_cli --cov-config=.coveragerc --cov-fail-under=65
python -m build --wheel
python tools/verify_install_matrix.py --wheel-dir dist
python tools/verify_wheel_install.py --wheel-dir dist
python tools/scan_secrets.py
```

`tests.yml` 在 Windows 和 Linux 运行完整测试，分别验证四种安装档位，并在 macOS 运行控制面 smoke。`tag-build-verify.yml` 会针对 `v*` tag 再次检查源码身份、合同、安全、构建和隔离 wheel。

当前许可证为 `LicenseRef-Draftpaper-NonCommercial`。Tag workflow 只验证可分发 wheel，不执行公开 PyPI 发布。任何经过授权的分发仍是独立、显式的流程，并继续受项目许可证和第三方 notices 约束。
