#!/usr/bin/env python
import argparse
import re
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
import yaml


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


RH_CVE_API = "https://access.redhat.com/hydra/rest/securitydata/cve.json"
RH_CVE_DETAIL_API = "https://access.redhat.com/hydra/rest/securitydata/cve"
RH_CVE_URL = "https://access.redhat.com/security/cve"


def extract_source_name(sourcerpm):
    stem = sourcerpm.removesuffix(".src.rpm")
    parts = stem.split("-")
    for i in range(len(parts)):
        if parts[i] and parts[i][0].isdigit():
            return "-".join(parts[:i])
    return stem


def extract_source_evr(sourcerpm, pkg_evr=None):
    stem = sourcerpm.removesuffix(".src.rpm")
    name = extract_source_name(sourcerpm)
    evr_from_filename = stem[len(name) + 1:]
    if pkg_evr and ":" in pkg_evr:
        epoch = pkg_evr.split(":")[0]
        return f"{epoch}:{evr_from_filename}"
    return evr_from_filename


def _parse_evr(evr_string):
    if ":" in evr_string:
        epoch_str, vr = evr_string.split(":", 1)
        epoch = int(epoch_str)
    else:
        epoch = 0
        vr = evr_string
    if "-" in vr:
        version, release = vr.rsplit("-", 1)
    else:
        version = vr
        release = ""
    return epoch, version, release


def _rpm_vercmp(a, b):
    if a == b:
        return 0
    sa = re.findall(r"[a-zA-Z]+|[0-9]+", a)
    sb = re.findall(r"[a-zA-Z]+|[0-9]+", b)
    for i in range(max(len(sa), len(sb))):
        if i >= len(sa):
            return -1
        if i >= len(sb):
            return 1
        x, y = sa[i], sb[i]
        x_num = x[0].isdigit()
        y_num = y[0].isdigit()
        if x_num != y_num:
            return 1 if x_num else -1
        if x_num:
            xi, yi = int(x), int(y)
            if xi != yi:
                return 1 if xi > yi else -1
        else:
            if x != y:
                return 1 if x > y else -1
    return 0


def compare_evr(evr1, evr2):
    e1, v1, r1 = _parse_evr(evr1)
    e2, v2, r2 = _parse_evr(evr2)
    if e1 != e2:
        return 1 if e1 > e2 else -1
    vc = _rpm_vercmp(v1, v2)
    if vc != 0:
        return vc
    return _rpm_vercmp(r1, r2)


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
    tmpdir = tempfile.mkdtemp(prefix="rpm-cve-check-")
    try:
        image_dir = Path(tmpdir) / "image"
        rootfs = Path(tmpdir) / "rootfs"
        rootfs.mkdir()

        subprocess.run(
            ["skopeo", "copy", "--override-arch", "amd64",
             f"docker://{image_ref}", f"dir:{image_dir}"],
            check=True, capture_output=True,
        )

        import json as _json
        manifest = _json.loads((image_dir / "manifest.json").read_text())
        for layer in manifest["layers"]:
            blob = image_dir / layer["digest"].split(":")[1]
            subprocess.run(
                ["tar", "xf", str(blob), "-C", str(rootfs), "var/lib/rpm"],
                capture_output=True,
            )

        rpm_db_path = rootfs / "var" / "lib" / "rpm"
        if not rpm_db_path.exists():
            return []

        output = subprocess.check_output(
            ["rpm", "-qa", "--dbpath", str(rpm_db_path),
             "--queryformat", "%{NAME}\\t%{EPOCH}\\t%{VERSION}\\t%{RELEASE}\\t%{SOURCERPM}\\n"],
            text=True,
        )
        packages = []
        for line in output.strip().splitlines():
            parts = line.split("\t")
            if len(parts) != 5:
                continue
            name, epoch, version, release, sourcerpm = parts
            if epoch in ("(none)", "0"):
                evr = f"{version}-{release}"
            else:
                evr = f"{epoch}:{version}-{release}"
            packages.append({"name": name, "evr": evr, "sourcerpm": sourcerpm})
        return packages
    finally:
        subprocess.run(["rm", "-rf", tmpdir], capture_output=True)


def tag_image_packages(pkgs, image_label):
    return [{**pkg, "images": [image_label]} for pkg in pkgs]


def fetch_cves_for_source(source_name):
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


def fetch_cve_detail(cve_id):
    try:
        resp = requests.get(f"{RH_CVE_DETAIL_API}/{cve_id}.json", timeout=30)
        if not resp.ok:
            return None
        return resp.json()
    except requests.RequestException:
        return None


def detect_rhel_version(packages):
    counts = {}
    for pkg in packages:
        match = re.search(r"\.el(\d+)", pkg.get("evr", ""))
        if match:
            ver = match.group(1)
            counts[ver] = counts.get(ver, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def _is_rhel(rhel_version, cpe, product_name=""):
    return (f"enterprise_linux:{rhel_version}" in cpe
            or f"rhel_eus:{rhel_version}" in cpe
            or f"rhel_aus:{rhel_version}" in cpe
            or f"Enterprise Linux {rhel_version}" in product_name)


def is_cve_affecting_version(detail, source_name, source_evr, rhel_version):
    if not detail:
        return True
    has_rhel_entry = False
    for state in detail.get("package_state", []):
        if state.get("package_name", "") != source_name:
            continue
        if not _is_rhel(rhel_version, state.get("cpe", "")):
            continue
        has_rhel_entry = True
        fix_state = state.get("fix_state", "")
        if fix_state in ("Not affected", "Out of support scope"):
            return False
    for release in detail.get("affected_release", []):
        cpe = release.get("cpe", "")
        product = release.get("product_name", "")
        if not _is_rhel(rhel_version, cpe, product):
            continue
        pkg = release.get("package", "")
        pkg_name = extract_source_name(pkg)
        if pkg_name != source_name:
            continue
        has_rhel_entry = True
        fix_evr = pkg[len(pkg_name) + 1:]
        if fix_evr and compare_evr(source_evr, fix_evr) >= 0:
            return False
        return True
    if not has_rhel_entry:
        return False
    return True


def fetch_and_filter_cves(source_packages):
    initial = {}
    for source_name in source_packages:
        initial[source_name] = fetch_cves_for_source(source_name)

    all_cve_ids = set()
    for cves in initial.values():
        for cve in cves:
            all_cve_ids.add(cve["cve_id"])

    if not all_cve_ids:
        return initial, {}

    print(f"Fetching details for {len(all_cve_ids)} CVEs...", file=sys.stderr)
    details = {}
    done = 0
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_id = {
            executor.submit(fetch_cve_detail, cve_id): cve_id
            for cve_id in all_cve_ids
        }
        for future in as_completed(future_to_id):
            cve_id = future_to_id[future]
            details[cve_id] = future.result()
            done += 1
            if done % 100 == 0:
                print(f"  {done}/{len(all_cve_ids)}...", file=sys.stderr)

    return initial, details


def filter_cves_for_packages(source_packages, initial_cves, details, rhel_version):
    results = {}
    for source_name, pkgs in source_packages.items():
        source_evr = extract_source_evr(pkgs[0]["sourcerpm"], pkgs[0]["evr"])
        filtered = []
        for cve in initial_cves.get(source_name, []):
            detail = details.get(cve["cve_id"])
            if is_cve_affecting_version(detail, source_name, source_evr, rhel_version):
                filtered.append(cve)
        results[source_name] = filtered
    return results


def classify_cves_with_lockfile(image_source_pkgs, lockfile_pkgs, image_cves, details, rhel_version):
    lock_by_source = {}
    for pkg in lockfile_pkgs:
        src = extract_source_name(pkg["sourcerpm"])
        if src not in lock_by_source:
            lock_by_source[src] = pkg

    fixed = {}
    remaining = {}
    for source_name, cves in image_cves.items():
        if not cves:
            continue
        lock_pkg = lock_by_source.get(source_name)
        if not lock_pkg:
            remaining[source_name] = cves
            continue
        lock_evr = extract_source_evr(lock_pkg["sourcerpm"], lock_pkg["evr"])
        for cve in cves:
            detail = details.get(cve["cve_id"])
            if is_cve_affecting_version(detail, source_name, lock_evr, rhel_version):
                remaining.setdefault(source_name, []).append(cve)
            else:
                fixed.setdefault(source_name, []).append(cve)
    return fixed, remaining


def _source_to_binaries(image_pkgs):
    mapping = {}
    for pkg in image_pkgs:
        src = extract_source_name(pkg["sourcerpm"])
        mapping.setdefault(src, []).append(pkg["name"])
    return {src: sorted(set(names)) for src, names in mapping.items()}


def _format_cve_table(cves):
    lines = ["| CVE | CVSS | Severity | Date | Summary | Link |",
             "|-----|------|----------|------|---------|------|"]
    for cve in sorted(cves, key=lambda c: float(c.get("cvss3_score") or 0), reverse=True):
        date_str = cve["public_date"][:10] if cve["public_date"] else "N/A"
        score = cve.get("cvss3_score") or "N/A"
        severity = (cve["severity"] or "unknown").capitalize()
        lines.append(
            f"| {cve['cve_id']} | {score} | {severity} "
            f"| {date_str} | {cve['summary']} | [Details]({cve['link']}) |"
        )
    return "\n".join(lines)


def _count_source_cves(cves_by_source):
    total = sum(len(v) for v in cves_by_source.values())
    crit = sum(
        1 for cves in cves_by_source.values() for c in cves
        if (c.get("severity") or "").lower() in ("critical", "important")
    )
    return len(cves_by_source), total, crit


def format_markdown_image_only(image_pkgs, cves_by_source, image_ref):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# RPM CVE Report",
        "",
        f"- **Image:** {image_ref}",
        f"- **Date:** {today}",
        "",
        "## Open CVEs",
        "",
    ]
    src_to_bins = _source_to_binaries(image_pkgs)
    pkg_by_source = {}
    for pkg in image_pkgs:
        src = extract_source_name(pkg["sourcerpm"])
        if src not in pkg_by_source:
            pkg_by_source[src] = pkg

    sources_shown = set()
    for source_name in sorted(cves_by_source):
        cves = cves_by_source[source_name]
        if not cves:
            continue
        sources_shown.add(source_name)
        pkg = pkg_by_source.get(source_name)
        images_str = ", ".join(sorted(pkg.get("images", []))) if pkg else ""
        bins = src_to_bins.get(source_name, [])
        bins_str = f" (rpms: {', '.join(bins)})" if bins and bins != [source_name] else ""
        evr = pkg["evr"] if pkg else ""
        lines.append(f"### {source_name} {evr}{bins_str} ({images_str})")
        lines.append("")
        lines.append(_format_cve_table(cves))
        lines.append("")

    if not sources_shown:
        lines.append("_No known CVEs affecting the installed package versions._")
        lines.append("")

    srcs, total, crit = _count_source_cves(cves_by_source)
    lines.extend([
        "## Summary",
        "",
        f"- **Packages with CVEs:** {srcs}",
        f"- **Total CVEs:** {total}",
        f"- **Critical/Important:** {crit}",
        "",
    ])
    return "\n".join(lines)


def format_markdown_with_lockfile(image_pkgs, fixed, remaining, lockfile_path,
                                  image_ref, lock_by_source):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [
        "# RPM CVE Report",
        "",
        f"- **Image:** {image_ref}",
        f"- **Lock file:** {lockfile_path}",
        f"- **Date:** {today}",
        "",
    ]

    src_to_bins = _source_to_binaries(image_pkgs)
    pkg_by_source = {}
    for pkg in image_pkgs:
        src = extract_source_name(pkg["sourcerpm"])
        if src not in pkg_by_source:
            pkg_by_source[src] = pkg

    def _pkg_header(source_name):
        bins = src_to_bins.get(source_name, [])
        if bins and bins != [source_name]:
            return f" (rpms: {', '.join(bins)})"
        return ""

    lines.append("## CVEs Fixed by Lock File Update")
    lines.append("")
    if not fixed:
        lines.append("_No CVEs fixed by this update._")
        lines.append("")
    else:
        for source_name, cves in sorted(fixed.items()):
            img_pkg = pkg_by_source.get(source_name)
            lock_pkg = lock_by_source.get(source_name)
            images_str = ", ".join(sorted(img_pkg.get("images", []))) if img_pkg else ""
            img_evr = img_pkg["evr"] if img_pkg else "?"
            lock_evr = lock_pkg["evr"] if lock_pkg else "?"
            lines.append(f"### {source_name}{_pkg_header(source_name)} ({images_str})")
            lines.append(f"**{img_evr}** → **{lock_evr}**")
            lines.append("")
            lines.append(_format_cve_table(cves))
            lines.append("")

    lines.append("## Remaining CVEs")
    lines.append("")
    if not remaining:
        lines.append("_No remaining CVEs after this update._")
        lines.append("")
    else:
        for source_name, cves in sorted(remaining.items()):
            img_pkg = pkg_by_source.get(source_name)
            lock_pkg = lock_by_source.get(source_name)
            images_str = ", ".join(sorted(img_pkg.get("images", []))) if img_pkg else ""
            img_evr = img_pkg["evr"] if img_pkg else "?"
            if lock_pkg:
                lock_evr = lock_pkg["evr"]
                lines.append(f"### {source_name}{_pkg_header(source_name)} ({images_str})")
                lines.append(f"**{img_evr}** → **{lock_evr}**")
            else:
                lines.append(f"### {source_name}{_pkg_header(source_name)} ({images_str})")
                lines.append(f"**{img_evr}** (not in lock file)")
            lines.append("")
            lines.append(_format_cve_table(cves))
            lines.append("")

    f_srcs, f_total, f_crit = _count_source_cves(fixed)
    r_srcs, r_total, r_crit = _count_source_cves(remaining)
    lines.extend([
        "## Summary",
        "",
        "| Category | Packages | CVEs | Critical/Important |",
        "|----------|----------|------|--------------------|",
        f"| Fixed by update | {f_srcs} | {f_total} | {f_crit} |",
        f"| Remaining | {r_srcs} | {r_total} | {r_crit} |",
        "",
    ])
    return "\n".join(lines)


def format_yaml_image_only(image_pkgs, cves_by_source, image_ref):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def enrich(pkg):
        source = extract_source_name(pkg["sourcerpm"])
        return {"name": pkg["name"], "evr": pkg["evr"], "cves": cves_by_source.get(source, [])}

    return yaml.dump({
        "image": image_ref,
        "date": today,
        "packages": [enrich(p) for p in image_pkgs],
    }, Dumper=_NoAliasDumper, default_flow_style=False, sort_keys=False)


def format_yaml_with_lockfile(image_pkgs, fixed, remaining, lockfile_path,
                              image_ref, lock_by_source):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return yaml.dump({
        "image": image_ref,
        "lockfile": lockfile_path,
        "date": today,
        "fixed_cves": fixed,
        "remaining_cves": remaining,
    }, Dumper=_NoAliasDumper, default_flow_style=False, sort_keys=False)


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Extract RPM packages from a container image via skopeo, "
            "query the Red Hat Security Data API for known CVEs affecting "
            "the installed package versions, and produce a report. "
            "When a lock file is provided, the report also shows which "
            "CVEs would be fixed by updating to the lock file versions."
        ),
    )
    parser.add_argument("--image", required=True,
                        help="Full image reference, e.g. registry.redhat.io/rhosdt/opentelemetry-rhel9-operator:rhosdt-3.10.0")
    parser.add_argument("--lockfile",
                        help="Path to rpms.lock.yaml — when provided, shows which image CVEs are fixed by the update")
    parser.add_argument("--output", choices=["markdown", "yaml"], default="markdown",
                        help="Output format (default: markdown)")
    parser.add_argument("--arch", default="x86_64",
                        help="Architecture for lock file parsing (default: x86_64)")
    args = parser.parse_args()

    image_label = args.image.split("/")[-1].split(":")[0]

    # Step 1: Extract RPMs from image
    print(f"Extracting RPMs from {args.image}...", file=sys.stderr)
    raw_pkgs = get_image_rpms(args.image)
    image_pkgs = tag_image_packages(raw_pkgs, image_label)
    print(f"Found {len(image_pkgs)} packages", file=sys.stderr)

    rhel_version = detect_rhel_version(raw_pkgs)
    if not rhel_version:
        print("Error: could not detect RHEL version from image packages", file=sys.stderr)
        sys.exit(1)
    print(f"Detected RHEL {rhel_version}", file=sys.stderr)

    # Step 2: Fetch CVEs and details
    source_packages = dedupe_by_source(image_pkgs)
    print(f"Querying Red Hat CVE API for {len(source_packages)} source packages...", file=sys.stderr)
    initial_cves, details = fetch_and_filter_cves(source_packages)

    # Step 3: Filter to CVEs affecting image versions
    print("Filtering CVEs against image package versions...", file=sys.stderr)
    image_cves = filter_cves_for_packages(source_packages, initial_cves, details, rhel_version)
    total = sum(len(v) for v in image_cves.values())
    print(f"Found {total} CVEs affecting installed versions", file=sys.stderr)

    # Step 4: Optionally classify with lock file
    if args.lockfile:
        if not Path(args.lockfile).exists():
            print(f"Error: lock file not found: {args.lockfile}", file=sys.stderr)
            sys.exit(1)
        lockfile_pkgs = parse_lockfile(args.lockfile, args.arch)
        print(f"Lock file: {len(lockfile_pkgs)} packages for {args.arch}", file=sys.stderr)
        fixed, remaining = classify_cves_with_lockfile(
            source_packages, lockfile_pkgs, image_cves, details, rhel_version,
        )
        f_total = sum(len(v) for v in fixed.values())
        r_total = sum(len(v) for v in remaining.values())
        print(f"CVEs fixed by update: {f_total}, remaining: {r_total}", file=sys.stderr)

        lock_by_source = {}
        for pkg in lockfile_pkgs:
            src = extract_source_name(pkg["sourcerpm"])
            if src not in lock_by_source:
                lock_by_source[src] = pkg

        if args.output == "markdown":
            print(format_markdown_with_lockfile(
                image_pkgs, fixed, remaining, args.lockfile, args.image, lock_by_source))
        else:
            print(format_yaml_with_lockfile(
                image_pkgs, fixed, remaining, args.lockfile, args.image, lock_by_source))
    else:
        if args.output == "markdown":
            print(format_markdown_image_only(image_pkgs, image_cves, args.image))
        else:
            print(format_yaml_image_only(image_pkgs, image_cves, args.image))


if __name__ == "__main__":
    main()
