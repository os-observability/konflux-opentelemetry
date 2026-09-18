package checker

import (
	"debug/elf"
	"fmt"
	"sort"
	"strings"
)

func CheckSymbols(binaryPath string, classification map[string]PackageInfo) ([]Finding, error) {
	symbols, err := readSymbols(binaryPath)
	if err != nil {
		return nil, err
	}

	matched := make(map[string][]string)
	for _, sym := range symbols {
		for pkg, info := range classification {
			if info.Category != CategoryNonDelegating {
				continue
			}
			if matchesPackage(sym, pkg) {
				matched[pkg] = append(matched[pkg], sym)
			}
		}
	}

	var findings []Finding

	var pkgs []string
	for pkg := range matched {
		pkgs = append(pkgs, pkg)
	}
	sort.Strings(pkgs)

	for _, pkg := range pkgs {
		syms := matched[pkg]
		sort.Strings(syms)
		if len(syms) > 10 {
			syms = append(syms[:10], fmt.Sprintf("... and %d more", len(syms)-10))
		}
		info := classification[pkg]
		findings = append(findings, Finding{
			Checker:  "symbol",
			Severity: SeverityError,
			Package:  pkg,
			Message:  fmt.Sprintf("non-delegating symbols linked in binary: %s", info.Reason),
			Symbols:  syms,
			Category: string(info.Category),
		})
	}

	nonDelegating := NonDelegatingPackages(classification)
	sort.Strings(nonDelegating)
	for _, pkg := range nonDelegating {
		if _, found := matched[pkg]; !found {
			findings = append(findings, Finding{
				Checker:  "symbol",
				Severity: SeverityOK,
				Package:  pkg,
				Message:  "no symbols found in binary (dead-code-eliminated or not imported)",
			})
		}
	}

	return findings, nil
}

func readSymbols(binaryPath string) ([]string, error) {
	f, err := elf.Open(binaryPath)
	if err != nil {
		return nil, fmt.Errorf("opening ELF binary %s: %w", binaryPath, err)
	}
	defer f.Close()

	syms, err := f.Symbols()
	if err != nil {
		return nil, fmt.Errorf("reading symbols from %s: %w", binaryPath, err)
	}

	var names []string
	for _, s := range syms {
		if s.Name != "" {
			names = append(names, s.Name)
		}
	}

	return names, nil
}

func matchesPackage(symbolName, packagePath string) bool {
	idx := strings.Index(symbolName, packagePath)
	if idx == -1 {
		return false
	}
	after := idx + len(packagePath)
	if after >= len(symbolName) {
		return true
	}
	next := symbolName[after]
	return next == '.' || next == '/'
}
