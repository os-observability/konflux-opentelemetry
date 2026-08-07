#!/usr/bin/env python
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
import yaml


RH_CVE_API = "https://access.redhat.com/hydra/rest/securitydata/cve.json"
RH_CVE_URL = "https://access.redhat.com/security/cve"


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


def get_image_rpms(image_ref):
    """Get set of RPM package names installed in a container image."""
    tmpdir = tempfile.mkdtemp(prefix="rpm-cve-check-")
    try:
        cid = subprocess.check_output(
            ["podman", "create", image_ref],
            text=True,
        ).strip()
        try:
            subprocess.run(
                ["podman", "cp", f"{cid}:/var/lib/rpm", tmpdir],
                check=True,
                capture_output=True,
            )
        finally:
            subprocess.run(["podman", "rm", cid], capture_output=True)

        rpm_db_path = Path(tmpdir) / "rpm"
        output = subprocess.check_output(
            ["rpm", "-qa", "--dbpath", str(rpm_db_path), "--queryformat", "%{NAME}\\n"],
            text=True,
        )
        return set(output.strip().splitlines())
    finally:
        subprocess.run(["rm", "-rf", tmpdir], capture_output=True)


def classify_packages(packages, image_rpm_sets):
    """Classify packages as runtime or build-only based on image contents."""
    runtime = []
    buildonly = []
    for pkg in packages:
        found_in = [name for name, rpms in image_rpm_sets.items() if pkg["name"] in rpms]
        if found_in:
            runtime.append({**pkg, "images": found_in})
        else:
            buildonly.append(pkg)
    return runtime, buildonly


def fetch_cves_for_source(source_name):
    """Query Red Hat Security Data API for CVEs affecting a source package."""
    try:
        resp = requests.get(RH_CVE_API, params={"package": source_name}, timeout=30)
        if not resp.ok:
            print(f"Warning: CVE API returned {resp.status_code} for {source_name}", file=sys.stderr)
            return []
        cves = []
        for entry in resp.json():
            cves.append({
                "cve_id": entry.get("CVE", ""),
                "severity": entry.get("severity", "unknown"),
                "cvss3_score": entry.get("cvss3_score"),
                "public_date": entry.get("public_date", ""),
                "summary": entry.get("bugzilla_description", ""),
                "link": f"{RH_CVE_URL}/{entry.get('CVE', '')}",
            })
        return cves
    except requests.RequestException as e:
        print(f"Warning: CVE API request failed for {source_name}: {e}", file=sys.stderr)
        return []


def fetch_all_cves(source_packages):
    """Fetch CVEs for all unique source packages."""
    results = {}
    for source_name in source_packages:
        results[source_name] = fetch_cves_for_source(source_name)
    return results
