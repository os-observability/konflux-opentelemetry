package main

import (
	"flag"
	"fmt"
	"os"

	"github.com/os-observability/konflux-opentelemetry/tools/fips-check/checker"
	"github.com/os-observability/konflux-opentelemetry/tools/fips-check/reporter"
)

func main() {
	binaryPath := flag.String("binary", "", "Path to compiled Go binary (enables build-info + symbol checks)")
	modulePath := flag.String("module", "", "Path to Go module directory (enables dependency check)")
	configPath := flag.String("config", "", "Path to classification YAML (replaces built-in defaults)")
	yamlOutput := flag.Bool("yaml", false, "Output as YAML instead of text")
	flag.Parse()

	if *binaryPath == "" && *modulePath == "" {
		fmt.Fprintln(os.Stderr, "at least one of --binary or --module is required")
		flag.Usage()
		os.Exit(2)
	}

	var classification map[string]checker.PackageInfo
	if *configPath != "" {
		data, err := os.ReadFile(*configPath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "reading config file: %v\n", err)
			os.Exit(2)
		}
		classification, err = checker.LoadClassificationFromFile(data)
		if err != nil {
			fmt.Fprintf(os.Stderr, "parsing config file: %v\n", err)
			os.Exit(2)
		}
	} else {
		var err error
		classification, err = checker.LoadDefaultClassification()
		if err != nil {
			fmt.Fprintf(os.Stderr, "loading default classification: %v\n", err)
			os.Exit(2)
		}
	}

	var findings []checker.Finding

	if *binaryPath != "" {
		bi, err := checker.CheckBuildInfo(*binaryPath)
		if err != nil {
			fmt.Fprintf(os.Stderr, "build info check failed: %v\n", err)
			os.Exit(2)
		}
		findings = append(findings, bi...)

		sym, err := checker.CheckSymbols(*binaryPath, classification)
		if err != nil {
			fmt.Fprintf(os.Stderr, "symbol check failed: %v\n", err)
			os.Exit(2)
		}
		findings = append(findings, sym...)
	}

	if *modulePath != "" {
		dep, err := checker.CheckDependencies(*modulePath, classification)
		if err != nil {
			fmt.Fprintf(os.Stderr, "dependency check failed: %v\n", err)
			os.Exit(2)
		}
		findings = append(findings, dep...)
	}

	report := reporter.Report{
		BinaryPath: *binaryPath,
		ModulePath: *modulePath,
		Findings:   findings,
	}

	if *yamlOutput {
		if err := reporter.WriteYAML(os.Stdout, report); err != nil {
			fmt.Fprintf(os.Stderr, "failed to write YAML: %v\n", err)
			os.Exit(2)
		}
	} else {
		reporter.WriteText(os.Stdout, report)
	}

	for _, f := range findings {
		if f.Severity == checker.SeverityError || f.Severity == checker.SeverityWarning {
			os.Exit(1)
		}
	}
}
