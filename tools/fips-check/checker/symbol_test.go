package checker

import (
	"testing"
)

func TestMatchesPackage(t *testing.T) {
	tests := []struct {
		symbol  string
		pkg     string
		matches bool
	}{
		{
			symbol:  "golang.org/x/crypto/bcrypt.GenerateFromPassword",
			pkg:     "golang.org/x/crypto/bcrypt",
			matches: true,
		},
		{
			symbol:  "golang.org/x/crypto/sha3.New256",
			pkg:     "golang.org/x/crypto/sha3",
			matches: true,
		},
		{
			symbol:  "crypto/sha256.New",
			pkg:     "golang.org/x/crypto/sha3",
			matches: false,
		},
		{
			symbol:  "golang.org/x/crypto/chacha20poly1305.New",
			pkg:     "golang.org/x/crypto/chacha20",
			matches: false,
		},
		{
			symbol:  "golang.org/x/crypto/chacha20.NewUnauthenticatedCipher",
			pkg:     "golang.org/x/crypto/chacha20",
			matches: true,
		},
		{
			symbol:  "golang.org/x/crypto/chacha20poly1305.New",
			pkg:     "golang.org/x/crypto/chacha20poly1305",
			matches: true,
		},
		{
			symbol:  "github.com/jcmturner/gokrb5/v8/crypto.GetEtype",
			pkg:     "github.com/jcmturner/gokrb5/v8",
			matches: true,
		},
		{
			symbol:  "main.main",
			pkg:     "golang.org/x/crypto/bcrypt",
			matches: false,
		},
	}

	for _, tt := range tests {
		got := matchesPackage(tt.symbol, tt.pkg)
		if got != tt.matches {
			t.Errorf("matchesPackage(%q, %q) = %v, want %v", tt.symbol, tt.pkg, got, tt.matches)
		}
	}
}
