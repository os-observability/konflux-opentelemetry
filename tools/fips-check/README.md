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

Running against the OpenTelemetry Operator binary and module with YAML output:

```bash
fips-check --binary opentelemetry-operator --module . --yaml
```

```yaml
binaryPath: opentelemetry-operator
modulePath: .
findings:
    - checker: buildinfo
      severity: ERROR
      message: binary was not built with GOFIPS140 — no FIPS 140 module embedded
    - checker: buildinfo
      severity: WARNING
      message: CGO_ENABLED=1 — binary uses cgo, verify no non-FIPS C crypto is linked
    - checker: symbol
      severity: ERROR
      package: golang.org/x/crypto/chacha20
      message: 'non-delegating symbols linked in binary: standalone ChaCha20 implementation, not FIPS approved'
      symbols:
        - vendor/golang.org/x/crypto/chacha20.(*Cipher).XORKeyStream
        - vendor/golang.org/x/crypto/chacha20.(*Cipher).xorKeyStreamBlocksGeneric
        - vendor/golang.org/x/crypto/chacha20.hChaCha20
        - vendor/golang.org/x/crypto/chacha20.newUnauthenticatedCipher
      category: non-delegating
    - checker: symbol
      severity: ERROR
      package: golang.org/x/crypto/chacha20poly1305
      message: 'non-delegating symbols linked in binary: standalone AEAD implementation, not FIPS approved'
      symbols:
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).Open
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).Seal
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).seal
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).sealGeneric
        - '... and 17 more'
      category: non-delegating
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/bcrypt
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: dependency
      severity: WARNING
      package: golang.org/x/crypto/chacha20poly1305
      message: standalone AEAD implementation, not FIPS approved
      importers:
        - importer: github.com/google/s2a-go/internal/record/internal/aeadcrypter
          chain:
            - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/config
            - github.com/prometheus/prometheus/config
            - github.com/prometheus/prometheus/storage/remote/googleiam
            - google.golang.org/api/option
            - google.golang.org/api/internal
            - github.com/google/s2a-go
            - github.com/google/s2a-go/internal/handshaker
            - github.com/google/s2a-go/internal/record
            - github.com/google/s2a-go/internal/record/internal/halfconn
            - github.com/google/s2a-go/internal/record/internal/aeadcrypter
        - importer: github.com/quic-go/quic-go/internal/handshake
          chain:
            - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/server
            - github.com/gin-gonic/gin
            - github.com/quic-go/quic-go/http3
            - github.com/quic-go/quic-go
            - github.com/quic-go/quic-go/internal/handshake
      category: non-delegating
    - checker: dependency
      severity: INFO
      package: golang.org/x/crypto/sha3
      message: wrapper around crypto/sha3 since Go 1.24 (delegates to crypto/sha3 → FIPS module)
      importers:
        - importer: github.com/go-playground/validator/v10
          chain:
            - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/server
            - github.com/gin-gonic/gin
            - github.com/gin-gonic/gin/binding
            - github.com/go-playground/validator/v10
      category: delegating
summary:
    errors: 3
    warnings: 4
    info: 2
```
