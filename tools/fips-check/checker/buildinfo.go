package checker

import (
	"debug/buildinfo"
	"fmt"
	"regexp"
)

func CheckBuildInfo(binaryPath string) ([]Finding, error) {
	info, err := buildinfo.ReadFile(binaryPath)
	if err != nil {
		return nil, fmt.Errorf("reading build info from %s: %w", binaryPath, err)
	}

	var findings []Finding

	gofips140 := ""
	for _, s := range info.Settings {
		if s.Key == "GOFIPS140" {
			gofips140 = s.Value
			break
		}
	}

	switch {
	case gofips140 == "" || gofips140 == "off":
		findings = append(findings, Finding{
			Checker:  "buildinfo",
			Severity: SeverityError,
			Message:  "binary was not built with GOFIPS140 — no FIPS 140 module embedded",
		})
	case isValidGOFIPS140(gofips140):
		findings = append(findings, Finding{
			Checker:  "buildinfo",
			Severity: SeverityOK,
			Message:  fmt.Sprintf("GOFIPS140=%s", gofips140),
		})
	default:
		findings = append(findings, Finding{
			Checker:  "buildinfo",
			Severity: SeverityError,
			Message:  fmt.Sprintf("GOFIPS140=%s — unrecognized value, expected certified, latest, inprocess, or vX.Y.Z", gofips140),
		})
	}

	cgoEnabled := ""
	for _, s := range info.Settings {
		if s.Key == "CGO_ENABLED" {
			cgoEnabled = s.Value
			break
		}
	}
	if cgoEnabled == "1" {
		findings = append(findings, Finding{
			Checker:  "buildinfo",
			Severity: SeverityWarning,
			Message:  "CGO_ENABLED=1 — binary uses cgo, verify no non-FIPS C crypto is linked",
		})
	}

	return findings, nil
}

var validGOFIPS140 = regexp.MustCompile(`^v\d+\.\d+\.\d+(-[a-zA-Z0-9]+)?$`)

func isValidGOFIPS140(value string) bool {
	switch value {
	case "certified", "latest", "inprocess":
		return true
	}
	return validGOFIPS140.MatchString(value)
}
