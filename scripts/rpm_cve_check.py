#!/usr/bin/env python
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


RH_CVE_API = "https://access.redhat.com/hydra/rest/securitydata/cve.json"
RH_CVE_URL = "https://access.redhat.com/security/cve"

IMAGES = {
    "operator": "registry.redhat.io/rhosdt/opentelemetry-rhel9-operator",
    "collector": "registry.redhat.io/rhosdt/opentelemetry-collector-rhel9",
    "target-allocator": "registry.redhat.io/rhosdt/opentelemetry-target-allocator-rhel9",
}


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


def _format_pkg_section(pkg, cves_by_source, include_images=False):
    """Format a single package's section with CVE table."""
    source = extract_source_name(pkg["sourcerpm"])
    header = f"### {pkg['name']} {pkg['evr']}"
    if include_images and "images" in pkg:
        header += f" ({', '.join(sorted(pkg['images']))})"
    lines = [header, ""]

    cves = cves_by_source.get(source, [])
    if not cves:
        lines.append("_No known CVEs_")
    else:
        lines.append("| CVE | CVSS | Severity | Date | Summary | Link |")
        lines.append("|-----|------|----------|------|---------|------|")
        for cve in sorted(cves, key=lambda c: float(c.get("cvss3_score") or 0), reverse=True):
            date_str = cve["public_date"][:10] if cve["public_date"] else "N/A"
            score = cve.get("cvss3_score") or "N/A"
            lines.append(
                f"| {cve['cve_id']} | {score} | {cve['severity'].capitalize()} "
                f"| {date_str} | {cve['summary']} | [Details]({cve['link']}) |"
            )
    lines.append("")
    return "\n".join(lines)


def _count_cves(packages, cves_by_source):
    """Count CVE stats for a set of packages."""
    sources_seen = set()
    total_cves = 0
    pkgs_with_cves = 0
    critical_important = 0
    for pkg in packages:
        source = extract_source_name(pkg["sourcerpm"])
        if source in sources_seen:
            continue
        sources_seen.add(source)
        cves = cves_by_source.get(source, [])
        if cves:
            pkgs_with_cves += 1
            total_cves += len(cves)
            critical_important += sum(
                1 for c in cves if c.get("severity", "").lower() in ("critical", "important")
            )
    return len(packages), pkgs_with_cves, total_cves, critical_important


def format_markdown(runtime, buildonly, cves_by_source, lockfile_path, arch):
    """Generate the full markdown report."""
    today = datetime.utcnow().strftime("%Y-%m-%d")
    lines = [
        "# RPM CVE Report",
        "",
        f"**Lock file:** {lockfile_path}",
        f"**Architecture:** {arch}",
        f"**Date:** {today}",
        "",
    ]

    lines.append("## Runtime Packages")
    lines.append("")
    if not runtime:
        lines.append("_No runtime packages found in lock file._")
        lines.append("")
    else:
        for pkg in runtime:
            lines.append(_format_pkg_section(pkg, cves_by_source, include_images=True))

    lines.append("## Build-Only Packages")
    lines.append("")
    if not buildonly:
        lines.append("_No build-only packages found in lock file._")
        lines.append("")
    else:
        for pkg in buildonly:
            lines.append(_format_pkg_section(pkg, cves_by_source, include_images=False))

    rt_pkgs, rt_with, rt_total, rt_crit = _count_cves(runtime, cves_by_source)
    bo_pkgs, bo_with, bo_total, bo_crit = _count_cves(buildonly, cves_by_source)

    lines.append("## Summary")
    lines.append("")
    lines.append("| Category | Packages | With CVEs | Total CVEs | Critical/Important |")
    lines.append("|----------|----------|-----------|------------|--------------------|")
    lines.append(f"| Runtime | {rt_pkgs} | {rt_with} | {rt_total} | {rt_crit} |")
    lines.append(f"| Build-only | {bo_pkgs} | {bo_with} | {bo_total} | {bo_crit} |")
    lines.append("")

    return "\n".join(lines)


def format_json(runtime, buildonly, cves_by_source, lockfile_path, arch):
    """Generate the JSON report."""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    def enrich(pkg):
        source = extract_source_name(pkg["sourcerpm"])
        return {**pkg, "cves": cves_by_source.get(source, [])}

    data = {
        "lockfile": lockfile_path,
        "arch": arch,
        "date": today,
        "runtime_packages": [enrich(p) for p in runtime],
        "buildonly_packages": [enrich(p) for p in buildonly],
    }
    return json.dumps(data, indent=2)


def resolve_image_names(image_arg):
    """Return list of image keys based on --image flag."""
    if image_arg == "all":
        return list(IMAGES.keys())
    if image_arg in IMAGES:
        return [image_arg]
    print(f"Error: unknown image '{image_arg}'. Choose from: {', '.join(IMAGES.keys())}, all", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Analyze rpms.lock.yaml for known CVEs against production images."
    )
    parser.add_argument("lockfile", help="Path to rpms.lock.yaml")
    parser.add_argument("--image", default="all",
                        help="Image to check: operator, collector, target-allocator, or all (default: all)")
    parser.add_argument("--tag", default="latest",
                        help="Production image tag, e.g. rhosdt-3.10.0 (default: latest)")
    parser.add_argument("--output", choices=["markdown", "json"], default="markdown",
                        help="Output format (default: markdown)")
    parser.add_argument("--arch", default="x86_64",
                        help="Architecture to analyze (default: x86_64)")
    args = parser.parse_args()

    if not Path(args.lockfile).exists():
        print(f"Error: lock file not found: {args.lockfile}", file=sys.stderr)
        sys.exit(1)

    image_keys = resolve_image_names(args.image)

    # Step 1: Parse lock file
    print(f"Parsing {args.lockfile} for arch {args.arch}...", file=sys.stderr)
    packages = parse_lockfile(args.lockfile, args.arch)
    if not packages:
        print(f"No packages found for arch {args.arch}", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(packages)} packages", file=sys.stderr)

    # Step 2: Classify packages
    print(f"Inspecting production images (tag={args.tag})...", file=sys.stderr)
    image_rpm_sets = {}
    for key in image_keys:
        ref = f"{IMAGES[key]}:{args.tag}"
        print(f"  Pulling RPM list from {ref}...", file=sys.stderr)
        image_rpm_sets[key] = get_image_rpms(ref)
        print(f"  Found {len(image_rpm_sets[key])} RPMs in {key}", file=sys.stderr)

    runtime, buildonly = classify_packages(packages, image_rpm_sets)
    print(f"Classified: {len(runtime)} runtime, {len(buildonly)} build-only", file=sys.stderr)

    # Step 3: Fetch CVEs
    source_packages = dedupe_by_source(packages)
    print(f"Querying Red Hat CVE API for {len(source_packages)} source packages...", file=sys.stderr)
    cves_by_source = fetch_all_cves(source_packages)
    total_cves = sum(len(v) for v in cves_by_source.values())
    print(f"Found {total_cves} CVEs across all packages", file=sys.stderr)

    # Step 4: Format output
    if args.output == "markdown":
        print(format_markdown(runtime, buildonly, cves_by_source, args.lockfile, args.arch))
    else:
        print(format_json(runtime, buildonly, cves_by_source, args.lockfile, args.arch))


if __name__ == "__main__":
    main()
