package checker

import (
	"fmt"
	"os"
	"strings"

	"gopkg.in/yaml.v3"
)

type AllowEntry struct {
	Package string   `yaml:"package"`
	Chain   []string `yaml:"chain"`
	Reason  string   `yaml:"reason"`
}

type AllowlistConfig struct {
	Allow        []AllowEntry `yaml:"allow"`
	ExcludePackages []string     `yaml:"excludePackages"`
}

func LoadAllowlist(path string) (*AllowlistConfig, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("reading allowlist: %w", err)
	}
	var config AllowlistConfig
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("parsing allowlist: %w", err)
	}
	return &config, nil
}

func (a *AllowlistConfig) isChainAllowed(pkg string, chain []string) bool {
	for _, entry := range a.Allow {
		if entry.Package == pkg && chainsEqual(entry.Chain, chain) {
			return true
		}
	}
	return false
}

func chainsEqual(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

func (a *AllowlistConfig) isChainExcluded(chain []string) bool {
	for _, root := range a.ExcludePackages {
		for _, step := range chain {
			if step == root || strings.HasPrefix(step, root+"/") {
				return true
			}
		}
	}
	return false
}

func ApplyAllowlist(findings []Finding, allowlist *AllowlistConfig) []Finding {
	if allowlist == nil {
		return findings
	}

	fullyAllowed := make(map[string]bool)

	var result []Finding
	for _, f := range findings {
		if f.Checker != "dependency" || len(f.Importers) == 0 {
			result = append(result, f)
			continue
		}

		var remaining []ImportChain
		for _, ic := range f.Importers {
			if allowlist.isChainAllowed(f.Package, ic.Chain) {
				continue
			}
			if allowlist.isChainExcluded(ic.Chain) {
				continue
			}
			remaining = append(remaining, ic)
		}

		if len(remaining) == 0 {
			fullyAllowed[f.Package] = true
			f.Importers = nil
			f.Severity = SeverityOK
			f.Message = fmt.Sprintf("all import paths allowed: %s", f.Message)
			result = append(result, f)
		} else {
			f.Importers = remaining
			result = append(result, f)
		}
	}

	for i, f := range result {
		if f.Checker == "symbol" && f.Severity == SeverityError && fullyAllowed[f.Package] {
			result[i].Severity = SeverityOK
			result[i].Message = fmt.Sprintf("allowed by dependency allowlist: %s", f.Message)
			result[i].Symbols = nil
		}
	}

	return result
}
