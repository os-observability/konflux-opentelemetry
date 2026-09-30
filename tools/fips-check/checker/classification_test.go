package checker

import (
	"testing"
)

func TestLoadDefaultClassification(t *testing.T) {
	classification, err := LoadDefaultClassification()
	if err != nil {
		t.Fatalf("failed to load default classification: %v", err)
	}
	if len(classification) == 0 {
		t.Fatal("expected non-empty classification")
	}
}

func TestClassificationCompleteness(t *testing.T) {
	classification, err := LoadDefaultClassification()
	if err != nil {
		t.Fatalf("failed to load default classification: %v", err)
	}

	knownXCryptoPackages := []string{
		"golang.org/x/crypto/sha3",
		"golang.org/x/crypto/pbkdf2",
		"golang.org/x/crypto/hkdf",
		"golang.org/x/crypto/bcrypt",
		"golang.org/x/crypto/blowfish",
		"golang.org/x/crypto/chacha20",
		"golang.org/x/crypto/chacha20poly1305",
		"golang.org/x/crypto/ssh",
		"golang.org/x/crypto/pkcs12",
		"golang.org/x/crypto/curve25519",
		"golang.org/x/crypto/salsa20",
		"golang.org/x/crypto/nacl",
		"golang.org/x/crypto/argon2",
		"golang.org/x/crypto/scrypt",
		"golang.org/x/crypto/cryptobyte",
	}

	for _, pkg := range knownXCryptoPackages {
		if _, ok := classification[pkg]; !ok {
			t.Errorf("missing classification for %s", pkg)
		}
	}
}

func TestClassificationCategories(t *testing.T) {
	classification, err := LoadDefaultClassification()
	if err != nil {
		t.Fatalf("failed to load default classification: %v", err)
	}

	delegating := map[string]bool{
		"golang.org/x/crypto/sha3":   true,
		"golang.org/x/crypto/pbkdf2": true,
		"golang.org/x/crypto/hkdf":   true,
	}

	for pkg, info := range classification {
		if delegating[pkg] {
			if info.Category != CategoryDelegating {
				t.Errorf("%s should be delegating, got %s", pkg, info.Category)
			}
			if info.DelegatesTo == "" {
				t.Errorf("%s is delegating but has no DelegatesTo", pkg)
			}
		}
	}
}

func TestNonDelegatingPackages(t *testing.T) {
	classification, err := LoadDefaultClassification()
	if err != nil {
		t.Fatalf("failed to load default classification: %v", err)
	}

	pkgs := NonDelegatingPackages(classification)
	if len(pkgs) == 0 {
		t.Error("expected non-empty list of non-delegating packages")
	}

	for _, pkg := range pkgs {
		info, ok := classification[pkg]
		if !ok {
			t.Errorf("NonDelegatingPackages returned unknown package %s", pkg)
		}
		if info.Category != CategoryNonDelegating {
			t.Errorf("NonDelegatingPackages returned %s with category %s", pkg, info.Category)
		}
	}
}

func TestThirdPartyPackagesHaveModuleCheck(t *testing.T) {
	classification, err := LoadDefaultClassification()
	if err != nil {
		t.Fatalf("failed to load default classification: %v", err)
	}

	thirdParty := []string{
		"github.com/jcmturner/gokrb5/v8",
		"github.com/jcmturner/aescts/v2",
		"github.com/jcmturner/gofork",
		"github.com/xdg-go/pbkdf2",
		"github.com/go-jose/go-jose/v4",
	}

	for _, pkg := range thirdParty {
		info, ok := classification[pkg]
		if !ok {
			t.Errorf("missing classification for third-party package %s", pkg)
			continue
		}
		if !info.ModuleCheck {
			t.Errorf("%s should have ModuleCheck=true", pkg)
		}
	}
}

func TestMergeClassifications(t *testing.T) {
	base := map[string]PackageInfo{
		"pkg/a": {Package: "pkg/a", Category: CategoryNonDelegating, Reason: "original"},
		"pkg/b": {Package: "pkg/b", Category: CategoryUtility, Reason: "utility"},
	}
	override := map[string]PackageInfo{
		"pkg/a": {Package: "pkg/a", Category: CategoryDelegating, Reason: "now delegating"},
		"pkg/c": {Package: "pkg/c", Category: CategoryNonDelegating, Reason: "new package"},
	}

	merged := MergeClassifications(base, override)

	if merged["pkg/a"].Category != CategoryDelegating {
		t.Errorf("pkg/a should be overridden to delegating, got %s", merged["pkg/a"].Category)
	}
	if merged["pkg/b"].Category != CategoryUtility {
		t.Error("pkg/b should be preserved from base")
	}
	if _, ok := merged["pkg/c"]; !ok {
		t.Error("pkg/c should be added from override")
	}
}

func TestLoadClassificationFromFile(t *testing.T) {
	data := []byte(`
packages:
  - package: custom/crypto/pkg
    category: non-delegating
    reason: custom test package
    moduleCheck: true
`)
	classification, err := LoadClassificationFromFile(data)
	if err != nil {
		t.Fatalf("failed to parse: %v", err)
	}
	info, ok := classification["custom/crypto/pkg"]
	if !ok {
		t.Fatal("missing custom package")
	}
	if info.Category != CategoryNonDelegating {
		t.Errorf("expected non-delegating, got %s", info.Category)
	}
	if !info.ModuleCheck {
		t.Error("expected moduleCheck=true")
	}
}
