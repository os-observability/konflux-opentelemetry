#!/usr/bin/env python
import re

import yaml


def extract_source_name(sourcerpm):
    stem = sourcerpm.removesuffix(".src.rpm")
    parts = stem.split("-")
    for i in range(len(parts)):
        if parts[i] and parts[i][0].isdigit():
            return "-".join(parts[:i])
    return stem


def parse_lockfile(path, arch):
    with open(path) as f:
        data = yaml.safe_load(f)
    packages = []
    for arch_entry in data.get("arches", []):
        if arch_entry.get("arch") == arch:
            for pkg in arch_entry.get("packages", []):
                packages.append({
                    "name": pkg["name"],
                    "evr": pkg["evr"],
                    "sourcerpm": pkg["sourcerpm"],
                })
            break
    return packages


def dedupe_by_source(packages):
    grouped = {}
    for pkg in packages:
        src = extract_source_name(pkg["sourcerpm"])
        grouped.setdefault(src, []).append(pkg)
    return grouped
