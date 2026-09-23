package reporter

import (
	"fmt"
	"io"
	"strings"

	"github.com/os-observability/konflux-opentelemetry/tools/fips-check/checker"
)

func WriteText(w io.Writer, report Report) {
	fmt.Fprintln(w, "=== FIPS Compliance Report ===")
	fmt.Fprintln(w)

	if report.BinaryPath != "" {
		fmt.Fprintf(w, "Binary: %s\n", report.BinaryPath)
	}
	if report.ModulePath != "" {
		fmt.Fprintf(w, "Module: %s\n", report.ModulePath)
	}
	fmt.Fprintln(w)

	writeSection(w, "Build Info", report.Findings, "buildinfo")
	writeSection(w, "Dependencies", report.Findings, "dependency")
	writeSection(w, "Symbols in Binary", report.Findings, "symbol")

	summary := report.computeSummary()
	fmt.Fprintln(w, "--- Summary ---")
	fmt.Fprintf(w, "Errors: %d  Warnings: %d  Info: %d\n", summary.Errors, summary.Warnings, summary.Info)
}

func writeSection(w io.Writer, title string, findings []checker.Finding, checkerName string) {
	var sectionFindings []checker.Finding
	for _, f := range findings {
		if f.Checker == checkerName {
			sectionFindings = append(sectionFindings, f)
		}
	}

	if len(sectionFindings) == 0 {
		return
	}

	fmt.Fprintf(w, "--- %s ---\n\n", title)

	for _, f := range sectionFindings {
		icon := severityIcon(f.Severity)
		if f.Package != "" {
			fmt.Fprintf(w, "[%s] %s %s\n", f.Severity, icon, f.Package)
			fmt.Fprintf(w, "  %s\n", f.Message)
		} else {
			fmt.Fprintf(w, "[%s] %s %s\n", f.Severity, icon, f.Message)
		}

		if len(f.Chain) > 0 {
			fmt.Fprintln(w, "  Chain:")
			for i, step := range f.Chain {
				if i == 0 {
					fmt.Fprintf(w, "    %s\n", step)
				} else {
					fmt.Fprintf(w, "    -> %s\n", step)
				}
			}
		}

		if len(f.Symbols) > 0 {
			fmt.Fprintln(w, "  Symbols:")
			for _, s := range f.Symbols {
				fmt.Fprintf(w, "    %s\n", s)
			}
		}

		fmt.Fprintln(w)
	}
}

func severityIcon(s checker.Severity) string {
	switch s {
	case checker.SeverityError:
		return strings.Repeat("!", 1)
	case checker.SeverityWarning:
		return "?"
	case checker.SeverityOK:
		return "ok"
	default:
		return "-"
	}
}
