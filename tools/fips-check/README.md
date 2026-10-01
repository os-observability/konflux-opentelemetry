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

# Use allowlist for verified import paths (CI gate)
fips-check --binary ./binary --module ./path/to/module --allowlist ./allowlist.yaml
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

## Allowlist

The `--allowlist` flag accepts a YAML file with verified import chains. This is designed for CI gating — you verify each import chain once, add it to the allowlist, and the tool only fails on new, unverified chains.

The allowlist matches on the **shortest reported import chain** from the root module package to the direct importer (one chain per importer, found via BFS). If the same crypto package is imported through a different chain (e.g., a new feature adds a dependency that also uses `chacha20poly1305`), it won't be allowed until you verify and add that chain. Note: if a dependency upgrade changes the shortest path to an already-allowed importer, the allowlist entry may need updating.

```yaml
allow:
  - package: golang.org/x/crypto/chacha20poly1305
    chain:
      - github.com/my-org/my-app/cmd/server
      - github.com/gin-gonic/gin
      - github.com/quic-go/quic-go/http3
      - github.com/quic-go/quic-go
      - github.com/quic-go/quic-go/internal/handshake
    reason: QUIC HTTP/3 transport via gin, not exposed in FIPS mode

  - package: golang.org/x/crypto/pkcs12
    chain:
      - github.com/my-org/my-app/cmd/config
      - github.com/prometheus/prometheus/config
      - github.com/prometheus/prometheus/storage/remote/azuread
      - github.com/Azure/azure-sdk-for-go/sdk/azidentity
    reason: Azure cert auth, not used in our deployment

# Exclude entire features that are disabled in FIPS mode
excludePackages:
  - github.com/open-telemetry/opentelemetry-collector-contrib/extension/oidcauthextension
```

When all import chains of a package are allowed (or excluded), both the dependency and symbol findings are downgraded to OK. When only some chains are allowed, the finding remains a warning showing only the unverified chains. Symbol findings are only downgraded when all dependency chains for the same package are allowed.

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
      severity: OK
      message: GOFIPS140=v1.0.0-c2097c7c
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
        - go:itab.*vendor/golang.org/x/crypto/chacha20poly1305.chacha20poly1305,crypto/cipher.AEAD
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).NonceSize
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).Open
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).Overhead
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).Seal
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).open
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).openGeneric
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).seal
        - vendor/golang.org/x/crypto/chacha20poly1305.(*chacha20poly1305).sealGeneric
        - vendor/golang.org/x/crypto/chacha20poly1305..inittask
        - '... and 17 more'
      category: non-delegating
    - checker: symbol
      severity: OK
      package: github.com/go-jose/go-jose/v4
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: github.com/jcmturner/aescts/v2
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: github.com/jcmturner/gofork
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: github.com/jcmturner/gokrb5/v8
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: github.com/xdg-go/pbkdf2
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/argon2
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/bcrypt
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/blake2b
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/blake2s
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/blowfish
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/bn256
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/cast5
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/curve25519
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/nacl
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/openpgp
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/pkcs12
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/salsa20
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/scrypt
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/ssh
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/tea
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/twofish
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: symbol
      severity: OK
      package: golang.org/x/crypto/xtea
      message: no symbols found in binary (dead-code-eliminated or not imported)
    - checker: dependency
      severity: INFO
      package: golang.org/x/crypto/hkdf
      message: wrapper around crypto/hkdf since Go 1.24 (delegates to crypto/hkdf → FIPS module)
      importers:
        - importer: github.com/google/s2a-go/internal/record/internal/halfconn
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
        - importer: github.com/quic-go/quic-go/internal/handshake
          chain:
            - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/server
            - github.com/gin-gonic/gin
            - github.com/quic-go/quic-go/http3
            - github.com/quic-go/quic-go
            - github.com/quic-go/quic-go/internal/handshake
      category: delegating
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
    - checker: dependency
      severity: WARNING
      package: golang.org/x/crypto/chacha20
      message: standalone ChaCha20 implementation, not FIPS approved
      importers:
        - importer: github.com/quic-go/quic-go/internal/handshake
          chain:
            - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/server
            - github.com/gin-gonic/gin
            - github.com/quic-go/quic-go/http3
            - github.com/quic-go/quic-go
            - github.com/quic-go/quic-go/internal/handshake
        - importer: golang.org/x/crypto/chacha20poly1305
          chain:
            - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/server
            - github.com/gin-gonic/gin
            - github.com/quic-go/quic-go/http3
            - github.com/quic-go/quic-go
            - github.com/quic-go/quic-go/internal/handshake
            - golang.org/x/crypto/chacha20poly1305
      category: non-delegating
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
      severity: WARNING
      package: golang.org/x/crypto/pkcs12
      message: uses RC2 internally, not FIPS approved
      importers:
        - importer: github.com/Azure/azure-sdk-for-go/sdk/azidentity
          chain:
            - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/config
            - github.com/prometheus/prometheus/config
            - github.com/prometheus/prometheus/storage/remote/azuread
            - github.com/Azure/azure-sdk-for-go/sdk/azidentity
      category: non-delegating
summary:
    errors: 2
    warnings: 3
    info: 2
```

Example allowlist for the operator (`--allowlist`). With this allowlist, `fips-check` exits with status `0` for the findings above:

```yaml
# Verified FIPS allowlist for the OpenTelemetry Operator.
# Each entry documents a non-FIPS crypto import chain that has been reviewed
# and determined acceptable for our FIPS deployment.
# The chain is the exact import path from the root module package to the direct importer.
# If a new code path imports the same crypto package, it must be verified and added here.

allow:
  # quic-go uses chacha20 for QUIC/HTTP3 transport.
  # Pulled in by gin (target allocator HTTP server). Not exposed in FIPS mode.
  - package: golang.org/x/crypto/chacha20
    chain:
      - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/server
      - github.com/gin-gonic/gin
      - github.com/quic-go/quic-go/http3
      - github.com/quic-go/quic-go
      - github.com/quic-go/quic-go/internal/handshake
    reason: QUIC HTTP/3 transport via gin, not exposed in FIPS mode

  # chacha20poly1305 internally imports chacha20, same quic-go path.
  - package: golang.org/x/crypto/chacha20
    chain:
      - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/server
      - github.com/gin-gonic/gin
      - github.com/quic-go/quic-go/http3
      - github.com/quic-go/quic-go
      - github.com/quic-go/quic-go/internal/handshake
      - golang.org/x/crypto/chacha20poly1305
    reason: internal dependency of chacha20poly1305 in quic-go

  # quic-go uses chacha20poly1305 for QUIC transport.
  - package: golang.org/x/crypto/chacha20poly1305
    chain:
      - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/server
      - github.com/gin-gonic/gin
      - github.com/quic-go/quic-go/http3
      - github.com/quic-go/quic-go
      - github.com/quic-go/quic-go/internal/handshake
    reason: QUIC HTTP/3 transport via gin, not exposed in FIPS mode

  # Google S2A uses chacha20poly1305 as fallback AEAD.
  # When FIPS is enabled, S2A negotiates AES-GCM instead.
  - package: golang.org/x/crypto/chacha20poly1305
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
    reason: Google S2A fallback cipher, AES-GCM is used when FIPS is enabled

  # Azure SDK uses pkcs12 for certificate-based authentication.
  # This auth method is not used in our FIPS deployment.
  - package: golang.org/x/crypto/pkcs12
    chain:
      - github.com/open-telemetry/opentelemetry-operator/cmd/otel-allocator/internal/config
      - github.com/prometheus/prometheus/config
      - github.com/prometheus/prometheus/storage/remote/azuread
      - github.com/Azure/azure-sdk-for-go/sdk/azidentity
    reason: Azure certificate auth, not used in our FIPS deployment
```