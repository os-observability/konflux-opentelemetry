package checker

import (
	"bufio"
	"bytes"
	"context"
	"fmt"
	"os/exec"
	"sort"
	"strings"
)

func CheckDependencies(ctx context.Context, modulePath string, classification map[string]PackageInfo) ([]Finding, error) {
	graph, err := buildImportGraph(ctx, modulePath)
	if err != nil {
		return nil, fmt.Errorf("building import graph: %w", err)
	}

	reverseGraph := buildReverseGraph(graph)
	roots := findRoots(ctx, graph, modulePath)

	var findings []Finding

	for pkg, info := range classification {
		importers := findImporters(graph, pkg)
		if len(importers) == 0 {
			continue
		}

		sort.Strings(importers)

		severity := SeverityInfo
		message := info.Reason
		if info.Category == CategoryNonDelegating {
			severity = SeverityWarning
		} else if info.Category == CategoryDelegating {
			message = fmt.Sprintf("%s (delegates to %s → FIPS module)", info.Reason, info.DelegatesTo)
		} else {
			continue
		}

		var chains []ImportChain
		for _, imp := range importers {
			chain := traceToRoot(reverseGraph, roots, imp)
			chains = append(chains, ImportChain{
				Importer: imp,
				Chain:    chain,
			})
		}

		findings = append(findings, Finding{
			Checker:   "dependency",
			Severity:  severity,
			Package:   pkg,
			Message:   message,
			Importers: chains,
			Category:  string(info.Category),
		})
	}

	sort.Slice(findings, func(i, j int) bool {
		if findings[i].Severity != findings[j].Severity {
			return findings[i].Severity < findings[j].Severity
		}
		return findings[i].Package < findings[j].Package
	})

	return findings, nil
}

type importEdge struct {
	ImportPath string
	Imports    []string
}

func buildImportGraph(ctx context.Context, modulePath string) ([]importEdge, error) {
	cmd := exec.CommandContext(ctx, "go", "list", "-deps", "-f", "{{.ImportPath}} {{join .Imports \" \"}}", "./...")
	cmd.Dir = modulePath

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		return nil, fmt.Errorf("go list: %s: %s", err, stderr.String())
	}

	var edges []importEdge
	scanner := bufio.NewScanner(&stdout)
	for scanner.Scan() {
		fields := strings.Fields(scanner.Text())
		if len(fields) == 0 {
			continue
		}
		edges = append(edges, importEdge{
			ImportPath: fields[0],
			Imports:    fields[1:],
		})
	}

	return edges, nil
}

func buildReverseGraph(graph []importEdge) map[string][]string {
	reverse := make(map[string][]string)
	for _, edge := range graph {
		for _, imp := range edge.Imports {
			reverse[imp] = append(reverse[imp], edge.ImportPath)
		}
	}
	return reverse
}

// findRoots returns the main module's own packages (the ./... packages).
func findRoots(ctx context.Context, graph []importEdge, modulePath string) map[string]bool {
	cmd := exec.CommandContext(ctx, "go", "list", "./...")
	cmd.Dir = modulePath

	var stdout bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Run()

	roots := make(map[string]bool)
	scanner := bufio.NewScanner(&stdout)
	for scanner.Scan() {
		roots[strings.TrimSpace(scanner.Text())] = true
	}
	return roots
}

func findImporters(graph []importEdge, target string) []string {
	var importers []string
	for _, edge := range graph {
		if edge.ImportPath == target {
			continue
		}
		for _, imp := range edge.Imports {
			if imp == target || strings.HasPrefix(imp, target+"/") {
				importers = append(importers, edge.ImportPath)
				break
			}
		}
	}
	return importers
}

// traceToRoot finds the shortest path from any root package to the given
// importer using BFS on the reverse graph.
func traceToRoot(reverseGraph map[string][]string, roots map[string]bool, target string) []string {
	if roots[target] {
		return []string{target}
	}

	type node struct {
		pkg  string
		path []string
	}

	visited := make(map[string]bool)
	queue := []node{{pkg: target, path: []string{target}}}
	visited[target] = true

	for len(queue) > 0 {
		current := queue[0]
		queue = queue[1:]

		for _, parent := range reverseGraph[current.pkg] {
			if visited[parent] {
				continue
			}
			visited[parent] = true

			newPath := make([]string, len(current.path)+1)
			copy(newPath, current.path)
			newPath[len(current.path)] = parent

			if roots[parent] {
				// Reverse so it reads root → ... → importer
				for i, j := 0, len(newPath)-1; i < j; i, j = i+1, j-1 {
					newPath[i], newPath[j] = newPath[j], newPath[i]
				}
				return newPath
			}

			queue = append(queue, node{pkg: parent, path: newPath})
		}
	}

	return []string{target}
}
