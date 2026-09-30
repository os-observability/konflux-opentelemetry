package checker

import (
	"bytes"
	_ "embed"
	"fmt"

	"gopkg.in/yaml.v3"
)

type PackageCategory string

const (
	CategoryDelegating    PackageCategory = "delegating"
	CategoryNonDelegating PackageCategory = "non-delegating"
	CategoryUtility       PackageCategory = "utility"
)

type PackageInfo struct {
	Package     string          `yaml:"package"`
	Category    PackageCategory `yaml:"category"`
	Reason      string          `yaml:"reason"`
	DelegatesTo string          `yaml:"delegatesTo,omitempty"`
	ModuleCheck bool            `yaml:"moduleCheck,omitempty"`
}

type ClassificationConfig struct {
	Packages []PackageInfo `yaml:"packages"`
}

//go:embed classification.yaml
var defaultClassificationData []byte

func LoadDefaultClassification() (map[string]PackageInfo, error) {
	return parseClassification(defaultClassificationData)
}

func LoadClassificationFromFile(data []byte) (map[string]PackageInfo, error) {
	return parseClassification(data)
}

func MergeClassifications(base, override map[string]PackageInfo) map[string]PackageInfo {
	merged := make(map[string]PackageInfo, len(base)+len(override))
	for k, v := range base {
		merged[k] = v
	}
	for k, v := range override {
		merged[k] = v
	}
	return merged
}

func parseClassification(data []byte) (map[string]PackageInfo, error) {
	var config ClassificationConfig
	decoder := yaml.NewDecoder(bytes.NewReader(data))
	decoder.KnownFields(true)
	if err := decoder.Decode(&config); err != nil {
		return nil, fmt.Errorf("parsing classification config: %w", err)
	}
	if len(config.Packages) == 0 {
		return nil, fmt.Errorf("classification config must contain at least one package")
	}
	for _, pkg := range config.Packages {
		if pkg.Package == "" {
			return nil, fmt.Errorf("classification package name must not be empty")
		}
		switch pkg.Category {
		case CategoryDelegating, CategoryNonDelegating, CategoryUtility:
		default:
			return nil, fmt.Errorf("unsupported package category %q for %s", pkg.Category, pkg.Package)
		}
	}

	result := make(map[string]PackageInfo, len(config.Packages))
	for _, pkg := range config.Packages {
		result[pkg.Package] = pkg
	}
	return result, nil
}

func NonDelegatingPackages(classification map[string]PackageInfo) []string {
	var pkgs []string
	for pkg, info := range classification {
		if info.Category == CategoryNonDelegating {
			pkgs = append(pkgs, pkg)
		}
	}
	return pkgs
}
