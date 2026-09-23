# fips-check

A Go CLI tool that validates FIPS 140-3 compliance of Go binaries and modules.

It performs three layers of checks:

1. **Build Info** (`--binary`): Verifies the binary was built with `GOFIPS140` and reports the module version.
2. **Dependency Analysis** (`--module`): Checks for non-FIPS-compliant crypto dependencies using `go mod why` and reports the full import chain showing which feature pulls in each package.
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

```
=== FIPS Compliance Report ===

Module: ./_build

--- Dependencies ---

[WARNING] ? golang.org/x/crypto/bcrypt
  standalone Blowfish-based implementation, not FIPS approved
  Chain:
    github.com/example/myapp
    -> github.com/prometheus/exporter-toolkit/web
    -> golang.org/x/crypto/bcrypt

[INFO] - golang.org/x/crypto/pbkdf2
  wrapper around crypto/pbkdf2 since Go 1.24 (delegates to crypto/pbkdf2 → FIPS module)
  Chain:
    github.com/example/myapp
    -> github.com/twmb/franz-go/pkg/kadm
    -> golang.org/x/crypto/pbkdf2

--- Summary ---
Errors: 0  Warnings: 1  Info: 1
```
