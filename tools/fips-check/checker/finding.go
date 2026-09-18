package checker

type Severity string

const (
	SeverityError   Severity = "ERROR"
	SeverityWarning Severity = "WARNING"
	SeverityInfo    Severity = "INFO"
	SeverityOK      Severity = "OK"
)

type Finding struct {
	Checker  string   `yaml:"checker"`
	Severity Severity `yaml:"severity"`
	Package  string   `yaml:"package,omitempty"`
	Message  string   `yaml:"message"`
	Chain    []string `yaml:"chain,omitempty"`
	Symbols  []string `yaml:"symbols,omitempty"`
	Category string   `yaml:"category,omitempty"`
}
