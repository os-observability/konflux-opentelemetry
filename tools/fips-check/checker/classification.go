package checker

import (
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
	if err := yaml.Unmarshal(data, &config); err != nil {
		return nil, fmt.Errorf("parsing classification config: %w", err)
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
