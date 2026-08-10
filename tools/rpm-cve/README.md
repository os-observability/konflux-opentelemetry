# RPM CVE Check

CLI tool that extracts RPM packages from a container image and queries the
[Red Hat Security Data API](https://access.redhat.com/documentation/en-us/red_hat_security_data_api/)
for known CVEs affecting the installed versions.

When an optional [rpms.lock.yaml](https://hermetoproject.github.io/hermeto/latest/rpm/#rpm-lockfile) lock file is provided, the report classifies CVEs as
**fixed by the update** or **remaining** — useful for reviewing lock file PRs.

## Usage

```bash
# Scan an image for CVEs
podman run --rm \
  -v $XDG_RUNTIME_DIR/containers/auth.json:/auth.json:Z \
  -e REGISTRY_AUTH_FILE=/auth.json \
  ghcr.io/os-observability/konflux-opentelemetry/rpm-cve-check:latest \
  --image registry.redhat.io/rhosdt/opentelemetry-rhel9-operator:rhosdt-3.10.0

# Scan and compare against a lock file update
podman run --rm \
  -v $XDG_RUNTIME_DIR/containers/auth.json:/auth.json:Z \
  -e REGISTRY_AUTH_FILE=/auth.json \
  -v $(pwd):/workspace:Z \
  ghcr.io/os-observability/konflux-opentelemetry/rpm-cve-check:latest \
  --image registry.redhat.io/rhosdt/opentelemetry-rhel9-operator:rhosdt-3.10.0 \
  --lockfile /workspace/rpms.lock.yaml
```

For `docker` instead of `podman`, the auth file is typically at `~/.docker/config.json`:

### Options

| Flag | Description |
|------|-------------|
| `--image` | Full container image reference (required) |
| `--lockfile` | Path to `rpms.lock.yaml` — shows which CVEs the update fixes |
| `--output` | `markdown` (default) or `yaml` |
| `--arch` | Architecture for lock file parsing (default: `x86_64`) |

## How it works

1. Downloads the container image layers using `skopeo`
2. Extracts the RPM database (`/var/lib/rpm`) from the image layers
3. Queries `rpm -qa` against the extracted database to list installed packages
4. For each source package, queries the Red Hat Security Data API for known CVEs
5. Fetches per-CVE details and filters to only CVEs affecting the installed version
   (auto-detects the RHEL version from package `.elN` suffixes and matches against the corresponding CPE entries)
6. If a lock file is provided, compares CVEs against the updated versions to classify
   them as fixed or remaining
