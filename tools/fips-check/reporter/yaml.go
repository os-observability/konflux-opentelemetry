package reporter

import (
	"fmt"
	"io"

	"gopkg.in/yaml.v3"
)

func WriteYAML(w io.Writer, report Report) error {
	report.Summary = report.computeSummary()

	data, err := yaml.Marshal(report)
	if err != nil {
		return fmt.Errorf("marshaling YAML: %w", err)
	}
	_, err = w.Write(data)
	return err
}
