#!/usr/bin/env python
"""
Analyze rpms.lock.yaml for known CVEs by checking production images
and querying the Red Hat Security Data API.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import requests
import yaml

IMAGES = {
    "operator": "registry.redhat.io/rhosdt/opentelemetry-rhel9-operator",
    "collector": "registry.redhat.io/rhosdt/opentelemetry-collector-rhel9",
    "target-allocator": "registry.redhat.io/rhosdt/opentelemetry-target-allocator-rhel9",
}

RH_CVE_API = "https://access.redhat.com/hydra/rest/securitydata/cve.json"
RH_CVE_DETAIL_API = "https://access.redhat.com/hydra/rest/securitydata/cve"
RH_CVE_URL = "https://access.redhat.com/security/cve"


def extract_source_name(sourcerpm):
    """Extract source package name from sourcerpm field.

    Format: name-version-release.src.rpm
    The name can contain hyphens, so we need to identify where version starts.
    We use a heuristic: split on the pattern where a hyphen is followed by
    a digit and then find the version-release boundary.

    The version-release format is typically: version-release
    We need to strip both version and release from the end.
    """
    stem = sourcerpm.removesuffix(".src.rpm")
    # Split on all hyphens and work backwards
    # The format is name-version-release
    # We need to find where name ends and version begins
    # Version typically starts with a digit
    parts = stem.split("-")

    # Find the first part that starts with a digit (version starts there)
    for i in range(len(parts)):
        if parts[i] and parts[i][0].isdigit():
            # Everything before this is the name
            return "-".join(parts[:i])

    # Fallback: return the whole stem if no digit-starting part found
    return stem


def parse_lockfile(path, arch):
    """Parse rpms.lock.yaml and return packages for the given architecture."""
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

    # Also include noarch packages — they appear under any arch's section
    # in the lock file. The lock file puts noarch packages under the first
    # arch section with a repoid containing the requested arch.
    # In practice, noarch packages show up in every arch section, so the
    # loop above already captured them.

    return packages


def dedupe_by_source(packages):
    """Group packages by source RPM name."""
    grouped = {}
    for pkg in packages:
        src = extract_source_name(pkg["sourcerpm"])
        grouped.setdefault(src, []).append(pkg)
    return grouped
