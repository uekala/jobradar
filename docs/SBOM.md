# Jobradar SBOM inventory

The `Python SBOM` workflow resolves dependencies in clean CI virtual environments and emits CycloneDX JSON files plus the exact `pip freeze` input used to create each file.

## Included scopes

- **runtime**: Python 3.12 packages installed from `jobradar/requirements.txt`.
- **standalone-tests**: Python 3.12 packages installed from the runtime and development requirement files.
- **ha-integration-tests**: Python 3.14 packages installed from the root `requirements_test.txt`. The Home Assistant test plugin is pinned to the matching reviewed release in that file.

The workflow runs for relevant pull requests and can also be started manually with `workflow_dispatch`. Its outputs are retained as GitHub Actions artifacts for 90 days.

## Scope limitations

These are Python package SBOMs, not a complete SBOM for the Home Assistant add-on image. They do not yet inventory:

- Debian packages and other operating-system contents in `python:3.12-slim-bookworm`.
- The exact base-image digest used for a particular ARM64 add-on build.
- Home Assistant host-provided components or services.
- External APIs, feeds, remote fonts, or their data/service terms.

The SBOM generator is installed in the runner environment, outside the isolated target virtual environment, so it is not mixed into the application package inventory. The resolved package list is uploaded alongside each SBOM to make the input auditable.

## Reproducibility and review

Dependency constraints in the runtime and standalone development manifests are ranges, not locks. The generated files therefore represent the versions resolved at that workflow run, not a guarantee that a future run will resolve identical versions. Preserve the artifact with the corresponding workflow run/commit when retaining an audit record.

The Home Assistant integration test plugin is pinned separately because its releases track specific Home Assistant versions and may require a newer Python runtime. Update that pin together with the Python version after checking the plugin's published metadata and rerunning the integration tests.

Do not treat a successful SBOM generation as proof that all licenses or external-service terms have been legally approved. Review missing/ambiguous license metadata and separately assess the Docker base image and external data sources.
