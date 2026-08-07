#!/usr/bin/env python
import re
import subprocess
import tempfile
from pathlib import Path

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
