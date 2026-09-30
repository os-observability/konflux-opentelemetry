package checker

type Severity string

const (
	SeverityError   Severity = "ERROR"
	SeverityWarning Severity = "WARNING"
	SeverityInfo    Severity = "INFO"
	SeverityOK      Severity = "OK"
)

type ImportChain struct {
	Importer string   `yaml:"importer"`
	Chain    []string `yaml:"chain"`
}

type Finding struct {
	Checker   string        `yaml:"checker"`
	Severity  Severity      `yaml:"severity"`
	Package   string        `yaml:"package,omitempty"`
	Message   string        `yaml:"message"`
	Importers []ImportChain `yaml:"importers,omitempty"`
	Symbols   []string      `yaml:"symbols,omitempty"`
	Category  string        `yaml:"category,omitempty"`
}
