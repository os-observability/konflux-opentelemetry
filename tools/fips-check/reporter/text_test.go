package reporter

import (
	"bytes"
	"strings"
	"testing"

	"github.com/os-observability/konflux-opentelemetry/tools/fips-check/checker"
)

func TestWriteText(t *testing.T) {
	report := Report{
		BinaryPath: "/usr/bin/test-binary",
		ModulePath: "/src/test-module",
		Findings: []checker.Finding{
			{
				Checker:  "buildinfo",
				Severity: checker.SeverityOK,
				Message:  "GOFIPS140=v1.0.0",
			},
			{
				Checker:  "dependency",
				Severity: checker.SeverityWarning,
				Package:  "golang.org/x/crypto/bcrypt",
				Message:  "standalone Blowfish-based implementation",
				Chain:    []string{"myapp", "exporter-toolkit/web", "x/crypto/bcrypt"},
				Category: "non-delegating",
			},
			{
				Checker:  "symbol",
				Severity: checker.SeverityError,
				Package:  "golang.org/x/crypto/bcrypt",
				Message:  "non-delegating symbols linked in binary",
				Symbols:  []string{"bcrypt.GenerateFromPassword"},
				Category: "non-delegating",
			},
		},
	}

	var buf bytes.Buffer
	WriteText(&buf, report)
	output := buf.String()

	if !strings.Contains(output, "FIPS Compliance Report") {
		t.Error("missing report header")
	}
	if !strings.Contains(output, "/usr/bin/test-binary") {
		t.Error("missing binary path")
	}
	if !strings.Contains(output, "golang.org/x/crypto/bcrypt") {
		t.Error("missing bcrypt finding")
	}
	if !strings.Contains(output, "exporter-toolkit/web") {
		t.Error("missing chain step")
	}
	if !strings.Contains(output, "Errors: 1") {
		t.Error("missing error count")
	}
}

func TestWriteTextEmptyReport(t *testing.T) {
	report := Report{
		ModulePath: "/src/test",
		Findings:   nil,
	}

	var buf bytes.Buffer
	WriteText(&buf, report)
	output := buf.String()

	if !strings.Contains(output, "Errors: 0") {
		t.Error("expected zero errors")
	}
}
