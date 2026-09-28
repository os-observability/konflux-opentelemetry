# fips-check

A Go CLI tool that validates FIPS 140-3 compliance of Go binaries and modules.

It performs three layers of checks:

1. **Build Info** (`--binary`): Verifies the binary was built with `GOFIPS140` and reports the module version.
2. **Dependency Analysis** (`--module`): Checks for non-FIPS-compliant crypto dependencies by building the full import graph (via `go list -deps`) and reports all import chains showing which features pull in each package.
3. **Symbol Analysis** (`--binary`): Scans the binary's symbol table for linked symbols from non-FIPS crypto packages, distinguishing packages that are dead-code-eliminated from those actually compiled in.

## Installation

```bash
go install github.com/os-observability/konflux-opentelemetry/tools/fips-check@latest
```

## Usage

```bash
# Check a compiled Go binary (build info + symbol analysis)
fips-check --binary ./path/to/binary

# Check a Go module's dependencies
fips-check --module ./path/to/module

# Both checks together
fips-check --binary ./path/to/binary --module ./path/to/module

# YAML output
fips-check --module ./path/to/module --yaml

# Use custom classification config (replaces built-in defaults)
fips-check --module ./path/to/module --config ./custom-packages.yaml
```

## Configuration

The tool ships with a built-in classification of crypto packages (embedded via `go:embed` from `checker/classification.yaml`).
To use a custom classification instead, pass `--config` with a YAML file using the same format:

```yaml
packages:
  - package: github.com/example/custom-crypto
    category: non-delegating
    reason: custom crypto implementation
    moduleCheck: true
```

When `--config` is specified, it **replaces** the built-in defaults entirely.

## Package Classification

The tool maintains a classification of crypto packages:

- **Delegating (safe)**: `x/crypto/sha3`, `x/crypto/pbkdf2`, `x/crypto/hkdf` — wrappers around standard library FIPS module since Go 1.24
- **Non-delegating (concern)**: `x/crypto/bcrypt`, `x/crypto/chacha20poly1305`, `x/crypto/ssh`, etc. — standalone implementations outside the FIPS boundary
- **Third-party (concern)**: `go-jose/go-jose`, `jcmturner/gokrb5`, `jcmturner/aescts`, `xdg-go/pbkdf2` — crypto implementations not using the FIPS module
- **Utility (safe)**: `x/crypto/cryptobyte` — encoding helpers with no crypto operations

## Exit Codes

- `0`: No errors or warnings
- `1`: Errors or warnings found
- `2`: Tool execution failure

## Example Output

Running against the OpenTelemetry Collector build:

```
=== FIPS Compliance Report ===

Module: ./redhat-opentelemetry-collector/_build

--- Dependencies ---

[WARNING] ? github.com/go-jose/go-jose/v4
  JOSE/JWE implementation, uses x/crypto/pbkdf2 for key derivation in JWE
  Imported by:
    - github.com/coreos/go-oidc/v3/oidc
      github.com/os-observability/redhat-opentelemetry-collector
      -> github.com/open-telemetry/opentelemetry-collector-contrib/extension/oidcauthextension
      -> github.com/coreos/go-oidc/v3/oidc
    - github.com/open-telemetry/opentelemetry-collector-contrib/extension/oidcauthextension
      github.com/os-observability/redhat-opentelemetry-collector
      -> github.com/open-telemetry/opentelemetry-collector-contrib/extension/oidcauthextension

[WARNING] ? golang.org/x/crypto/bcrypt
  standalone Blowfish-based implementation, not FIPS approved
  Imported by:
    - github.com/prometheus/exporter-toolkit/web
      github.com/os-observability/redhat-opentelemetry-collector
      -> github.com/open-telemetry/opentelemetry-collector-contrib/receiver/prometheusreceiver
      -> github.com/open-telemetry/opentelemetry-collector-contrib/receiver/prometheusreceiver/internal/apiserver
      -> github.com/prometheus/exporter-toolkit/web

[WARNING] ? golang.org/x/crypto/chacha20poly1305
  standalone AEAD implementation, not FIPS approved
  Imported by:
    - github.com/foxboron/go-tpm-keyfiles
      github.com/os-observability/redhat-opentelemetry-collector
      -> github.com/open-telemetry/opentelemetry-collector-contrib/extension/oauth2clientauthextension
      -> go.opentelemetry.io/collector/config/configtls
      -> github.com/foxboron/go-tpm-keyfiles
    - github.com/google/s2a-go/internal/record/internal/aeadcrypter
      github.com/os-observability/redhat-opentelemetry-collector
      -> github.com/open-telemetry/opentelemetry-collector-contrib/exporter/googlecloudexporter
      -> github.com/GoogleCloudPlatform/opentelemetry-operations-go/exporter/collector
      -> google.golang.org/api/option
      -> google.golang.org/api/internal
      -> github.com/google/s2a-go
      -> github.com/google/s2a-go/internal/handshaker
      -> github.com/google/s2a-go/internal/record
      -> github.com/google/s2a-go/internal/record/internal/halfconn
      -> github.com/google/s2a-go/internal/record/internal/aeadcrypter

[INFO] - golang.org/x/crypto/pbkdf2
  wrapper around crypto/pbkdf2 since Go 1.24 (delegates to crypto/pbkdf2 → FIPS module)
  Imported by:
    - github.com/jcmturner/gokrb5/v8/crypto/rfc8009
      github.com/os-observability/redhat-opentelemetry-collector
      -> github.com/open-telemetry/opentelemetry-collector-contrib/exporter/kafkaexporter
      -> github.com/open-telemetry/opentelemetry-collector-contrib/internal/kafka
      -> github.com/jcmturner/gokrb5/v8/keytab
      -> github.com/jcmturner/gokrb5/v8/crypto
      -> github.com/jcmturner/gokrb5/v8/crypto/rfc8009
    - github.com/twmb/franz-go/pkg/kadm
      github.com/os-observability/redhat-opentelemetry-collector
      -> github.com/open-telemetry/opentelemetry-collector-contrib/exporter/kafkaexporter
      -> github.com/open-telemetry/opentelemetry-collector-contrib/internal/kafka
      -> github.com/twmb/franz-go/pkg/kadm

--- Summary ---
Errors: 0  Warnings: 9  Info: 3
```
