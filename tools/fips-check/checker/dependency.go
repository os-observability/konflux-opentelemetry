package checker

import (
	"bufio"
	"bytes"
	"fmt"
	"os/exec"
	"sort"
	"strings"
)

func CheckDependencies(modulePath string, classification map[string]PackageInfo) ([]Finding, error) {
	var findings []Finding

	nonDelegating := NonDelegatingPackages(classification)
	sort.Strings(nonDelegating)

	for _, pkg := range nonDelegating {
		info := classification[pkg]
		chain, err := resolveChain(modulePath, pkg, info.ModuleCheck)
		if err != nil {
			return nil, fmt.Errorf("checking %s: %w", pkg, err)
		}
		if chain == nil {
			continue
		}

		findings = append(findings, Finding{
			Checker:  "dependency",
			Severity: SeverityWarning,
			Package:  pkg,
			Message:  info.Reason,
			Chain:    chain,
			Category: string(info.Category),
		})
	}

	var delegating []string
	for pkg, info := range classification {
		if info.Category == CategoryDelegating {
			delegating = append(delegating, pkg)
		}
	}
	sort.Strings(delegating)

	for _, pkg := range delegating {
		info := classification[pkg]
		chain, err := resolveChain(modulePath, pkg, info.ModuleCheck)
		if err != nil {
			return nil, fmt.Errorf("checking %s: %w", pkg, err)
		}
		if chain == nil {
			continue
		}
		findings = append(findings, Finding{
			Checker:  "dependency",
			Severity: SeverityInfo,
			Package:  pkg,
			Message:  fmt.Sprintf("%s (delegates to %s → FIPS module)", info.Reason, info.DelegatesTo),
			Chain:    chain,
			Category: string(info.Category),
		})
	}

	return findings, nil
}

func resolveChain(modulePath, pkg string, moduleLevel bool) ([]string, error) {
	if moduleLevel {
		return goModWhyModule(modulePath, pkg)
	}
	return goModWhy(modulePath, pkg)
}

func goModWhy(modulePath, pkg string) ([]string, error) {
	cmd := exec.Command("go", "mod", "why", pkg)
	cmd.Dir = modulePath
	return parseModWhy(cmd)
}

func goModWhyModule(modulePath, module string) ([]string, error) {
	cmd := exec.Command("go", "mod", "why", "-m", module)
	cmd.Dir = modulePath
	return parseModWhy(cmd)
}

func parseModWhy(cmd *exec.Cmd) ([]string, error) {
	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		output := stdout.String()
		if strings.Contains(output, "does not need") {
			return nil, nil
		}
		return nil, fmt.Errorf("%s: %s", err, stderr.String())
	}

	output := stdout.String()
	if strings.Contains(output, "does not need") {
		return nil, nil
	}

	var chain []string
	scanner := bufio.NewScanner(strings.NewReader(output))
	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		chain = append(chain, line)
	}

	if len(chain) == 0 {
		return nil, nil
	}

	return chain, nil
}
