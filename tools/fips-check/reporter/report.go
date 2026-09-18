package reporter

import "github.com/os-observability/konflux-opentelemetry/tools/fips-check/checker"

type Report struct {
	BinaryPath string            `yaml:"binaryPath,omitempty"`
	ModulePath string            `yaml:"modulePath,omitempty"`
	Findings   []checker.Finding `yaml:"findings"`
	Summary    Summary           `yaml:"summary"`
}

type Summary struct {
	Errors   int `yaml:"errors"`
	Warnings int `yaml:"warnings"`
	Info     int `yaml:"info"`
}

func (r *Report) computeSummary() Summary {
	var s Summary
	for _, f := range r.Findings {
		switch f.Severity {
		case checker.SeverityError:
			s.Errors++
		case checker.SeverityWarning:
			s.Warnings++
		case checker.SeverityInfo:
			s.Info++
		}
	}
	return s
}
