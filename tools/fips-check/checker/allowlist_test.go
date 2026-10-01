package checker

import (
	"testing"
)

func TestApplyAllowlistByChain(t *testing.T) {
	findings := []Finding{
		{
			Checker:  "dependency",
			Severity: SeverityWarning,
			Package:  "golang.org/x/crypto/chacha20poly1305",
			Message:  "standalone AEAD implementation",
			Importers: []ImportChain{
				{Importer: "github.com/quic-go/quic-go/internal/handshake", Chain: []string{"myapp", "gin", "quic-go/internal/handshake"}},
				{Importer: "github.com/other/pkg", Chain: []string{"myapp", "other/pkg"}},
			},
		},
	}

	allowlist := &AllowlistConfig{
		Allow: []AllowEntry{
			{Package: "golang.org/x/crypto/chacha20poly1305", Chain: []string{"myapp", "gin", "quic-go/internal/handshake"}},
		},
	}

	result := ApplyAllowlist(findings, allowlist)
	if len(result) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(result))
	}
	if len(result[0].Importers) != 1 {
		t.Fatalf("expected 1 remaining importer, got %d", len(result[0].Importers))
	}
	if result[0].Importers[0].Importer != "github.com/other/pkg" {
		t.Errorf("expected other/pkg, got %s", result[0].Importers[0].Importer)
	}
	if result[0].Severity != SeverityWarning {
		t.Errorf("expected WARNING, got %s", result[0].Severity)
	}
}

func TestApplyAllowlistDifferentChainNotAllowed(t *testing.T) {
	findings := []Finding{
		{
			Checker:  "dependency",
			Severity: SeverityWarning,
			Package:  "golang.org/x/crypto/chacha20poly1305",
			Message:  "standalone AEAD implementation",
			Importers: []ImportChain{
				{Importer: "github.com/quic-go/quic-go/internal/handshake", Chain: []string{"myapp", "new-feature", "quic-go/internal/handshake"}},
			},
		},
	}

	allowlist := &AllowlistConfig{
		Allow: []AllowEntry{
			// Only allows the chain through gin, not through new-feature
			{Package: "golang.org/x/crypto/chacha20poly1305", Chain: []string{"myapp", "gin", "quic-go/internal/handshake"}},
		},
	}

	result := ApplyAllowlist(findings, allowlist)
	if result[0].Severity != SeverityWarning {
		t.Errorf("different chain should not be allowed, got %s", result[0].Severity)
	}
	if len(result[0].Importers) != 1 {
		t.Errorf("importer should remain, got %d importers", len(result[0].Importers))
	}
}

func TestApplyAllowlistAllChainsAllowed(t *testing.T) {
	findings := []Finding{
		{
			Checker:  "dependency",
			Severity: SeverityWarning,
			Package:  "golang.org/x/crypto/chacha20poly1305",
			Message:  "standalone AEAD implementation",
			Importers: []ImportChain{
				{Importer: "github.com/quic-go/quic-go/internal/handshake", Chain: []string{"myapp", "gin", "quic-go/internal/handshake"}},
			},
		},
	}

	allowlist := &AllowlistConfig{
		Allow: []AllowEntry{
			{Package: "golang.org/x/crypto/chacha20poly1305", Chain: []string{"myapp", "gin", "quic-go/internal/handshake"}},
		},
	}

	result := ApplyAllowlist(findings, allowlist)
	if len(result) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(result))
	}
	if result[0].Severity != SeverityOK {
		t.Errorf("expected OK when all chains allowed, got %s", result[0].Severity)
	}
}

func TestApplyAllowlistExcludeRoots(t *testing.T) {
	findings := []Finding{
		{
			Checker:  "dependency",
			Severity: SeverityWarning,
			Package:  "github.com/go-jose/go-jose/v4",
			Message:  "JOSE/JWE implementation",
			Importers: []ImportChain{
				{
					Importer: "github.com/coreos/go-oidc/v3/oidc",
					Chain:    []string{"myapp", "github.com/open-telemetry/opentelemetry-collector-contrib/extension/oidcauthextension", "github.com/coreos/go-oidc/v3/oidc"},
				},
				{
					Importer: "github.com/other/pkg",
					Chain:    []string{"myapp", "github.com/other/pkg"},
				},
			},
		},
	}

	allowlist := &AllowlistConfig{
		ExcludeRoots: []string{"github.com/open-telemetry/opentelemetry-collector-contrib/extension/oidcauthextension"},
	}

	result := ApplyAllowlist(findings, allowlist)
	if len(result) != 1 {
		t.Fatalf("expected 1 finding, got %d", len(result))
	}
	if len(result[0].Importers) != 1 {
		t.Fatalf("expected 1 remaining importer, got %d", len(result[0].Importers))
	}
	if result[0].Importers[0].Importer != "github.com/other/pkg" {
		t.Errorf("expected other/pkg, got %s", result[0].Importers[0].Importer)
	}
}

func TestApplyAllowlistNonDependencyFindingsUnchanged(t *testing.T) {
	findings := []Finding{
		{
			Checker:  "buildinfo",
			Severity: SeverityOK,
			Message:  "GOFIPS140=v1.0.0",
		},
		{
			Checker:  "symbol",
			Severity: SeverityError,
			Package:  "golang.org/x/crypto/chacha20",
			Message:  "non-delegating symbols linked in binary",
		},
	}

	allowlist := &AllowlistConfig{
		Allow: []AllowEntry{
			{Package: "golang.org/x/crypto/chacha20", Chain: []string{"anything"}},
		},
	}

	result := ApplyAllowlist(findings, allowlist)
	if len(result) != 2 {
		t.Fatalf("expected 2 findings unchanged, got %d", len(result))
	}
	if result[1].Severity != SeverityError {
		t.Errorf("symbol finding should remain ERROR, got %s", result[1].Severity)
	}
}

func TestApplyAllowlistSymbolDowngradedWhenDependencyAllowed(t *testing.T) {
	findings := []Finding{
		{
			Checker:  "dependency",
			Severity: SeverityWarning,
			Package:  "golang.org/x/crypto/chacha20",
			Message:  "standalone ChaCha20 implementation",
			Importers: []ImportChain{
				{Importer: "quic-go/internal/handshake", Chain: []string{"myapp", "gin", "quic-go/internal/handshake"}},
			},
		},
		{
			Checker:  "symbol",
			Severity: SeverityError,
			Package:  "golang.org/x/crypto/chacha20",
			Message:  "non-delegating symbols linked in binary",
			Symbols:  []string{"chacha20.XORKeyStream"},
		},
	}

	allowlist := &AllowlistConfig{
		Allow: []AllowEntry{
			{Package: "golang.org/x/crypto/chacha20", Chain: []string{"myapp", "gin", "quic-go/internal/handshake"}},
		},
	}

	result := ApplyAllowlist(findings, allowlist)
	if len(result) != 2 {
		t.Fatalf("expected 2 findings, got %d", len(result))
	}
	if result[0].Severity != SeverityOK {
		t.Errorf("dependency finding should be OK, got %s", result[0].Severity)
	}
	if result[1].Severity != SeverityOK {
		t.Errorf("symbol finding should be downgraded to OK, got %s", result[1].Severity)
	}
	if len(result[1].Symbols) != 0 {
		t.Errorf("symbol list should be cleared, got %v", result[1].Symbols)
	}
}

func TestApplyAllowlistSymbolNotDowngradedWhenPartiallyAllowed(t *testing.T) {
	findings := []Finding{
		{
			Checker:  "dependency",
			Severity: SeverityWarning,
			Package:  "golang.org/x/crypto/chacha20",
			Message:  "standalone ChaCha20 implementation",
			Importers: []ImportChain{
				{Importer: "quic-go/internal/handshake", Chain: []string{"myapp", "gin", "quic-go/internal/handshake"}},
				{Importer: "github.com/other/pkg", Chain: []string{"myapp", "other/pkg"}},
			},
		},
		{
			Checker:  "symbol",
			Severity: SeverityError,
			Package:  "golang.org/x/crypto/chacha20",
			Message:  "non-delegating symbols linked in binary",
			Symbols:  []string{"chacha20.XORKeyStream"},
		},
	}

	allowlist := &AllowlistConfig{
		Allow: []AllowEntry{
			{Package: "golang.org/x/crypto/chacha20", Chain: []string{"myapp", "gin", "quic-go/internal/handshake"}},
		},
	}

	result := ApplyAllowlist(findings, allowlist)
	if result[1].Severity != SeverityError {
		t.Errorf("symbol finding should remain ERROR when dependency only partially allowed, got %s", result[1].Severity)
	}
}

func TestApplyAllowlistNil(t *testing.T) {
	findings := []Finding{
		{Checker: "dependency", Severity: SeverityWarning, Package: "x"},
	}
	result := ApplyAllowlist(findings, nil)
	if len(result) != 1 {
		t.Fatalf("expected findings unchanged with nil allowlist")
	}
}
