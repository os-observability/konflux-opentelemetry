#!/usr/bin/env python
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import yaml


class TestExtractSourceName(unittest.TestCase):
    def test_simple_name(self):
        from rpm_cve_check import extract_source_name
        self.assertEqual(extract_source_name("glibc-2.34-274.el9_8.src.rpm"), "glibc")

    def test_name_with_hyphens(self):
        from rpm_cve_check import extract_source_name
        self.assertEqual(extract_source_name("util-linux-2.37.4-25.el9.src.rpm"), "util-linux")

    def test_name_with_plus(self):
        from rpm_cve_check import extract_source_name
        # gcc source produces libstdc++
        self.assertEqual(extract_source_name("gcc-11.5.0-14.el9.src.rpm"), "gcc")

    def test_epoch_in_evr(self):
        from rpm_cve_check import extract_source_name
        self.assertEqual(extract_source_name("openssl-3.5.5-6.el9_8.src.rpm"), "openssl")


class TestParseLockfile(unittest.TestCase):
    def test_parses_arch_packages(self):
        from rpm_cve_check import parse_lockfile
        lockdata = {
            "arches": [
                {
                    "arch": "x86_64",
                    "packages": [
                        {"name": "openssl", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
                        {"name": "glibc", "evr": "2.34-274.el9_8", "sourcerpm": "glibc-2.34-274.el9_8.src.rpm"},
                    ],
                },
                {
                    "arch": "aarch64",
                    "packages": [
                        {"name": "openssl", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
                    ],
                },
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(lockdata, f)
            f.flush()
            packages = parse_lockfile(f.name, "x86_64")
        os.unlink(f.name)
        self.assertEqual(len(packages), 2)
        self.assertEqual(packages[0]["name"], "openssl")
        self.assertEqual(packages[1]["name"], "glibc")

    def test_unknown_arch_returns_empty(self):
        from rpm_cve_check import parse_lockfile
        lockdata = {"arches": [{"arch": "x86_64", "packages": [{"name": "a", "evr": "1", "sourcerpm": "a-1.src.rpm"}]}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(lockdata, f)
            f.flush()
            packages = parse_lockfile(f.name, "s390x")
        os.unlink(f.name)
        self.assertEqual(packages, [])

    def test_includes_noarch_packages(self):
        from rpm_cve_check import parse_lockfile
        lockdata = {
            "arches": [
                {
                    "arch": "x86_64",
                    "packages": [
                        {"name": "openssl", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
                    ],
                },
            ]
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(lockdata, f)
            f.flush()
            packages = parse_lockfile(f.name, "x86_64")
        os.unlink(f.name)
        self.assertEqual(len(packages), 1)


class TestDedupeBySource(unittest.TestCase):
    def test_groups_by_source(self):
        from rpm_cve_check import dedupe_by_source
        packages = [
            {"name": "glibc", "evr": "2.34-274.el9_8", "sourcerpm": "glibc-2.34-274.el9_8.src.rpm"},
            {"name": "glibc-common", "evr": "2.34-274.el9_8", "sourcerpm": "glibc-2.34-274.el9_8.src.rpm"},
            {"name": "openssl", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
        ]
        grouped = dedupe_by_source(packages)
        self.assertEqual(len(grouped), 2)
        self.assertIn("glibc", grouped)
        self.assertIn("openssl", grouped)
        self.assertEqual(len(grouped["glibc"]), 2)
        self.assertEqual(len(grouped["openssl"]), 1)


class TestClassifyPackages(unittest.TestCase):
    def test_runtime_package(self):
        from rpm_cve_check import classify_packages
        packages = [
            {"name": "openssl-libs", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
        ]
        image_rpm_sets = {"operator": {"openssl-libs", "glibc"}, "collector": {"openssl-libs"}}
        runtime, buildonly = classify_packages(packages, image_rpm_sets)
        self.assertEqual(len(runtime), 1)
        self.assertEqual(len(buildonly), 0)
        self.assertEqual(set(runtime[0]["images"]), {"operator", "collector"})

    def test_buildonly_package(self):
        from rpm_cve_check import classify_packages
        packages = [
            {"name": "gcc", "evr": "11.5.0-14.el9", "sourcerpm": "gcc-11.5.0-14.el9.src.rpm"},
        ]
        image_rpm_sets = {"operator": {"openssl-libs"}}
        runtime, buildonly = classify_packages(packages, image_rpm_sets)
        self.assertEqual(len(runtime), 0)
        self.assertEqual(len(buildonly), 1)

    def test_mixed_packages(self):
        from rpm_cve_check import classify_packages
        packages = [
            {"name": "openssl-libs", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
            {"name": "gcc", "evr": "11.5.0-14.el9", "sourcerpm": "gcc-11.5.0-14.el9.src.rpm"},
        ]
        image_rpm_sets = {"operator": {"openssl-libs"}}
        runtime, buildonly = classify_packages(packages, image_rpm_sets)
        self.assertEqual(len(runtime), 1)
        self.assertEqual(len(buildonly), 1)
        self.assertEqual(runtime[0]["name"], "openssl-libs")
        self.assertEqual(buildonly[0]["name"], "gcc")


class TestFetchCvesForSource(unittest.TestCase):
    @patch("rpm_cve_check.requests.get")
    def test_parses_api_response(self, mock_get):
        from rpm_cve_check import fetch_cves_for_source
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = [
            {
                "CVE": "CVE-2026-42771",
                "severity": "low",
                "cvss3_score": "6.5",
                "public_date": "2026-07-10T00:00:00Z",
                "bugzilla_description": "openssl: Possible OOB Read",
                "resource_url": "https://access.redhat.com/hydra/rest/securitydata/cve/CVE-2026-42771.json",
            }
        ]
        mock_get.return_value = mock_response

        cves = fetch_cves_for_source("openssl")
        self.assertEqual(len(cves), 1)
        self.assertEqual(cves[0]["cve_id"], "CVE-2026-42771")
        self.assertEqual(cves[0]["severity"], "low")
        self.assertEqual(cves[0]["cvss3_score"], "6.5")
        self.assertEqual(cves[0]["link"], "https://access.redhat.com/security/cve/CVE-2026-42771")

    @patch("rpm_cve_check.requests.get")
    def test_handles_api_error(self, mock_get):
        from rpm_cve_check import fetch_cves_for_source
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        cves = fetch_cves_for_source("nonexistent")
        self.assertEqual(cves, [])

    @patch("rpm_cve_check.requests.get")
    def test_handles_empty_response(self, mock_get):
        from rpm_cve_check import fetch_cves_for_source
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        cves = fetch_cves_for_source("zlib")
        self.assertEqual(cves, [])


class TestFetchAllCves(unittest.TestCase):
    @patch("rpm_cve_check.fetch_cves_for_source")
    def test_deduplicates_api_calls(self, mock_fetch):
        from rpm_cve_check import fetch_all_cves
        mock_fetch.return_value = [{"cve_id": "CVE-2024-1234", "severity": "moderate", "cvss3_score": "5.0", "public_date": "2024-01-01", "summary": "test", "link": "https://example.com"}]

        source_packages = {
            "glibc": [{"name": "glibc", "evr": "2.34"}, {"name": "glibc-common", "evr": "2.34"}],
            "openssl": [{"name": "openssl-libs", "evr": "3.5.5"}],
        }
        result = fetch_all_cves(source_packages)
        self.assertEqual(mock_fetch.call_count, 2)
        self.assertIn("glibc", result)
        self.assertIn("openssl", result)


class TestFormatMarkdown(unittest.TestCase):
    def test_runtime_with_cves(self):
        from rpm_cve_check import format_markdown, extract_source_name
        runtime = [
            {"name": "openssl-libs", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm", "images": ["operator", "collector"]},
        ]
        buildonly = []
        cves_by_source = {
            "openssl": [
                {"cve_id": "CVE-2026-42771", "severity": "low", "cvss3_score": "6.5", "public_date": "2026-07-10T00:00:00Z", "summary": "openssl: Possible OOB Read", "link": "https://access.redhat.com/security/cve/CVE-2026-42771"},
            ],
        }
        report = format_markdown(runtime, buildonly, cves_by_source, "rpms.lock.yaml", "x86_64")
        self.assertIn("# RPM CVE Report", report)
        self.assertIn("## Runtime Packages", report)
        self.assertIn("openssl-libs", report)
        self.assertIn("CVE-2026-42771", report)
        self.assertIn("6.5", report)
        self.assertIn("operator", report)
        self.assertIn("collector", report)

    def test_buildonly_section(self):
        from rpm_cve_check import format_markdown
        runtime = []
        buildonly = [
            {"name": "gcc", "evr": "11.5.0-14.el9", "sourcerpm": "gcc-11.5.0-14.el9.src.rpm"},
        ]
        cves_by_source = {"gcc": []}
        report = format_markdown(runtime, buildonly, cves_by_source, "rpms.lock.yaml", "x86_64")
        self.assertIn("## Build-Only Packages", report)
        self.assertIn("gcc", report)
        self.assertIn("_No known CVEs_", report)

    def test_summary_table(self):
        from rpm_cve_check import format_markdown
        runtime = [
            {"name": "openssl-libs", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm", "images": ["operator"]},
        ]
        buildonly = [
            {"name": "gcc", "evr": "11.5.0-14.el9", "sourcerpm": "gcc-11.5.0-14.el9.src.rpm"},
        ]
        cves_by_source = {
            "openssl": [{"cve_id": "CVE-2026-42771", "severity": "important", "cvss3_score": "6.5", "public_date": "2026-07-10", "summary": "test", "link": "https://example.com"}],
            "gcc": [],
        }
        report = format_markdown(runtime, buildonly, cves_by_source, "rpms.lock.yaml", "x86_64")
        self.assertIn("## Summary", report)
        self.assertIn("Runtime", report)
        self.assertIn("Build-only", report)


class TestFormatJson(unittest.TestCase):
    def test_valid_json_output(self):
        from rpm_cve_check import format_json
        runtime = [
            {"name": "openssl-libs", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm", "images": ["operator"]},
        ]
        buildonly = []
        cves_by_source = {"openssl": []}
        output = format_json(runtime, buildonly, cves_by_source, "rpms.lock.yaml", "x86_64")
        data = json.loads(output)
        self.assertIn("runtime_packages", data)
        self.assertIn("buildonly_packages", data)
        self.assertIn("lockfile", data)
        self.assertEqual(data["arch"], "x86_64")


if __name__ == "__main__":
    unittest.main()
