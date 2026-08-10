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
        self.assertEqual(extract_source_name("openssl-3.0.7-25.el9_3.src.rpm"), "openssl")

    def test_name_with_hyphens(self):
        from rpm_cve_check import extract_source_name
        self.assertEqual(extract_source_name("p11-kit-0.26.2-1.el9.src.rpm"), "p11-kit")

    def test_name_with_plus(self):
        from rpm_cve_check import extract_source_name
        self.assertEqual(extract_source_name("libstdc++-11.5.0-14.el9.src.rpm"), "libstdc++")

    def test_epoch_in_evr(self):
        from rpm_cve_check import extract_source_name
        self.assertEqual(extract_source_name("openssl-3.5.5-4.el9_8.src.rpm"), "openssl")


class TestExtractSourceEvr(unittest.TestCase):
    def test_simple(self):
        from rpm_cve_check import extract_source_evr
        self.assertEqual(extract_source_evr("openssl-3.0.7-25.el9_3.src.rpm"), "3.0.7-25.el9_3")

    def test_no_epoch(self):
        from rpm_cve_check import extract_source_evr
        self.assertEqual(extract_source_evr("glibc-2.34-274.el9_8.src.rpm"), "2.34-274.el9_8")

    def test_with_epoch_from_pkg(self):
        from rpm_cve_check import extract_source_evr
        result = extract_source_evr("openssl-3.5.5-4.el9_8.src.rpm", "1:3.5.5-4.el9_8")
        self.assertEqual(result, "1:3.5.5-4.el9_8")


class TestCompareEvr(unittest.TestCase):
    def test_equal(self):
        from rpm_cve_check import compare_evr
        self.assertEqual(compare_evr("3.0.7-25.el9_3", "3.0.7-25.el9_3"), 0)

    def test_newer_version(self):
        from rpm_cve_check import compare_evr
        self.assertGreater(compare_evr("3.5.5-4.el9_8", "3.0.7-25.el9_3"), 0)

    def test_older_version(self):
        from rpm_cve_check import compare_evr
        self.assertLess(compare_evr("3.0.7-25.el9_3", "3.5.5-4.el9_8"), 0)

    def test_epoch_wins(self):
        from rpm_cve_check import compare_evr
        self.assertGreater(compare_evr("1:1.0-1.el9", "0:99.0-1.el9"), 0)

    def test_release_comparison(self):
        from rpm_cve_check import compare_evr
        self.assertGreater(compare_evr("3.0.7-26.el9_3", "3.0.7-25.el9_3"), 0)


class TestParseLockfile(unittest.TestCase):
    def test_parses_arch_packages(self):
        from rpm_cve_check import parse_lockfile
        content = yaml.dump({
            "lockfileVersion": 1,
            "arches": [{
                "arch": "x86_64",
                "packages": [
                    {"name": "openssl-libs", "evr": "1:3.5.5-6.el9_8",
                     "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
                    {"name": "glibc", "evr": "2.34-274.el9_8",
                     "sourcerpm": "glibc-2.34-274.el9_8.src.rpm"},
                ],
            }],
        })
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            f.flush()
            packages = parse_lockfile(f.name, "x86_64")
        os.unlink(f.name)
        self.assertEqual(len(packages), 2)

    def test_unknown_arch_returns_empty(self):
        from rpm_cve_check import parse_lockfile
        content = yaml.dump({
            "lockfileVersion": 1,
            "arches": [{"arch": "x86_64", "packages": [
                {"name": "glibc", "evr": "2.34-274.el9_8",
                 "sourcerpm": "glibc-2.34-274.el9_8.src.rpm"},
            ]}],
        })
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            f.flush()
            packages = parse_lockfile(f.name, "s390x")
        os.unlink(f.name)
        self.assertEqual(len(packages), 0)


class TestDedupeBySource(unittest.TestCase):
    def test_groups_by_source(self):
        from rpm_cve_check import dedupe_by_source
        pkgs = [
            {"name": "openssl-libs", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
            {"name": "openssl", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
            {"name": "glibc", "evr": "2.34-274.el9_8", "sourcerpm": "glibc-2.34-274.el9_8.src.rpm"},
        ]
        grouped = dedupe_by_source(pkgs)
        self.assertEqual(len(grouped), 2)
        self.assertIn("openssl", grouped)
        self.assertEqual(len(grouped["openssl"]), 2)


class TestTagImagePackages(unittest.TestCase):
    def test_tags_packages(self):
        from rpm_cve_check import tag_image_packages
        pkgs = [
            {"name": "glibc", "evr": "2.34-274.el9_8", "sourcerpm": "glibc-2.34-274.el9_8.src.rpm"},
            {"name": "openssl-libs", "evr": "3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
        ]
        tagged = tag_image_packages(pkgs, "operator")
        self.assertEqual(len(tagged), 2)
        for p in tagged:
            self.assertEqual(p["images"], ["operator"])


class TestDetectRhelVersion(unittest.TestCase):
    def test_detects_rhel9(self):
        from rpm_cve_check import detect_rhel_version
        pkgs = [
            {"name": "glibc", "evr": "2.34-274.el9_8"},
            {"name": "openssl-libs", "evr": "1:3.5.5-4.el9_8"},
            {"name": "gpg-pubkey", "evr": "fd431d51-4ae0493b"},
        ]
        self.assertEqual(detect_rhel_version(pkgs), "9")

    def test_detects_rhel8(self):
        from rpm_cve_check import detect_rhel_version
        pkgs = [
            {"name": "glibc", "evr": "2.28-225.el8"},
            {"name": "openssl-libs", "evr": "1:1.1.1k-12.el8_9"},
        ]
        self.assertEqual(detect_rhel_version(pkgs), "8")

    def test_no_el_suffix_returns_none(self):
        from rpm_cve_check import detect_rhel_version
        pkgs = [{"name": "gpg-pubkey", "evr": "fd431d51-4ae0493b"}]
        self.assertIsNone(detect_rhel_version(pkgs))


class TestIsCveAffectingVersion(unittest.TestCase):
    def test_none_detail_assumes_affected(self):
        from rpm_cve_check import is_cve_affecting_version
        self.assertTrue(is_cve_affecting_version(None, "openssl", "3.0.7-25.el9_3", "9"))

    def test_not_affected_state(self):
        from rpm_cve_check import is_cve_affecting_version
        detail = {"package_state": [
            {"package_name": "openssl", "cpe": "cpe:/o:redhat:enterprise_linux:9", "fix_state": "Not affected"},
        ]}
        self.assertFalse(is_cve_affecting_version(detail, "openssl", "3.0.7-25.el9_3", "9"))

    def test_fixed_in_older_version(self):
        from rpm_cve_check import is_cve_affecting_version
        detail = {"affected_release": [
            {"cpe": "cpe:/o:redhat:enterprise_linux:9", "package": "openssl-3.0.7-20.el9_3"},
        ]}
        self.assertFalse(is_cve_affecting_version(detail, "openssl", "3.0.7-25.el9_3", "9"))

    def test_fix_version_newer_than_ours(self):
        from rpm_cve_check import is_cve_affecting_version
        detail = {"affected_release": [
            {"cpe": "cpe:/o:redhat:enterprise_linux:9", "package": "openssl-3.5.5-99.el9_8"},
        ]}
        self.assertTrue(is_cve_affecting_version(detail, "openssl", "3.0.7-25.el9_3", "9"))

    def test_no_rhel9_entry_means_not_affected(self):
        from rpm_cve_check import is_cve_affecting_version
        detail = {"affected_release": [
            {"cpe": "cpe:/o:redhat:enterprise_linux:8", "package": "openssl-1.1.1-99.el8"},
        ]}
        self.assertFalse(is_cve_affecting_version(detail, "openssl", "3.0.7-25.el9_3", "9"))

    def test_rhel9_eus_cpe_matched(self):
        from rpm_cve_check import is_cve_affecting_version
        detail = {"affected_release": [
            {"cpe": "cpe:/a:redhat:rhel_eus:9", "package": "openssl-3.5.5-99.el9_8"},
        ]}
        self.assertTrue(is_cve_affecting_version(detail, "openssl", "3.0.7-25.el9_3", "9"))

    def test_rhel9_will_not_fix_is_affected(self):
        from rpm_cve_check import is_cve_affecting_version
        detail = {"package_state": [
            {"package_name": "openssl", "cpe": "cpe:/o:redhat:enterprise_linux:9", "fix_state": "Will not fix"},
        ]}
        self.assertTrue(is_cve_affecting_version(detail, "openssl", "3.0.7-25.el9_3", "9"))


class TestClassifyCvesWithLockfile(unittest.TestCase):
    def test_cve_fixed_by_lockfile(self):
        from rpm_cve_check import classify_cves_with_lockfile
        image_source_pkgs = {"openssl": [
            {"name": "openssl-libs", "evr": "1:3.0.7-25.el9_3", "sourcerpm": "openssl-3.0.7-25.el9_3.src.rpm"},
        ]}
        lockfile_pkgs = [
            {"name": "openssl-libs", "evr": "1:3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
        ]
        image_cves = {"openssl": [{"cve_id": "CVE-2024-1234", "severity": "important"}]}
        details = {"CVE-2024-1234": {"affected_release": [
            {"cpe": "cpe:/o:redhat:enterprise_linux:9", "package": "openssl-3.5.5-1.el9_8"},
        ]}}
        fixed, remaining = classify_cves_with_lockfile(image_source_pkgs, lockfile_pkgs, image_cves, details, "9")
        self.assertIn("openssl", fixed)
        self.assertNotIn("openssl", remaining)

    def test_cve_still_remaining(self):
        from rpm_cve_check import classify_cves_with_lockfile
        image_source_pkgs = {"openssl": [
            {"name": "openssl-libs", "evr": "3.0.7-25.el9_3", "sourcerpm": "openssl-3.0.7-25.el9_3.src.rpm"},
        ]}
        lockfile_pkgs = [
            {"name": "openssl-libs", "evr": "3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
        ]
        image_cves = {"openssl": [{"cve_id": "CVE-2024-9999", "severity": "critical"}]}
        details = {"CVE-2024-9999": {"affected_release": [
            {"cpe": "cpe:/o:redhat:enterprise_linux:9", "package": "openssl-99.0.0-1.el9"},
        ]}}
        fixed, remaining = classify_cves_with_lockfile(image_source_pkgs, lockfile_pkgs, image_cves, details, "9")
        self.assertNotIn("openssl", fixed)
        self.assertIn("openssl", remaining)


class TestFetchCvesForSource(unittest.TestCase):
    @patch("rpm_cve_check.requests.get")
    def test_parses_api_response(self, mock_get):
        from rpm_cve_check import fetch_cves_for_source
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = [
            {"CVE": "CVE-2024-1234", "severity": "important", "cvss3_score": "7.5",
             "public_date": "2024-01-15T00:00:00Z", "bugzilla_description": "test vuln"},
        ]
        mock_get.return_value = mock_response
        cves = fetch_cves_for_source("openssl")
        self.assertEqual(len(cves), 1)
        self.assertEqual(cves[0]["cve_id"], "CVE-2024-1234")
        self.assertEqual(cves[0]["severity"], "important")

    @patch("rpm_cve_check.requests.get")
    def test_handles_api_error(self, mock_get):
        from rpm_cve_check import fetch_cves_for_source
        mock_response = MagicMock()
        mock_response.ok = False
        mock_response.status_code = 500
        mock_get.return_value = mock_response
        cves = fetch_cves_for_source("openssl")
        self.assertEqual(cves, [])

    @patch("rpm_cve_check.requests.get")
    def test_handles_empty_response(self, mock_get):
        from rpm_cve_check import fetch_cves_for_source
        mock_response = MagicMock()
        mock_response.ok = True
        mock_response.json.return_value = []
        mock_get.return_value = mock_response
        cves = fetch_cves_for_source("nonexistent-pkg")
        self.assertEqual(cves, [])


class TestFilterCvesForPackages(unittest.TestCase):
    def test_filters_by_version(self):
        from rpm_cve_check import filter_cves_for_packages
        source_packages = {"openssl": [
            {"name": "openssl-libs", "evr": "3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"},
        ]}
        initial_cves = {"openssl": [
            {"cve_id": "CVE-old", "severity": "low"},
            {"cve_id": "CVE-new", "severity": "high"},
        ]}
        details = {
            "CVE-old": {"affected_release": [
                {"cpe": "cpe:/o:redhat:enterprise_linux:9", "package": "openssl-3.0.7-1.el9"},
            ]},
            "CVE-new": {"affected_release": [
                {"cpe": "cpe:/o:redhat:enterprise_linux:9", "package": "openssl-99.0.0-1.el9"},
            ]},
        }
        result = filter_cves_for_packages(source_packages, initial_cves, details, "9")
        self.assertEqual(len(result["openssl"]), 1)
        self.assertEqual(result["openssl"][0]["cve_id"], "CVE-new")


class TestFormatMarkdown(unittest.TestCase):
    def test_image_only_with_cves(self):
        from rpm_cve_check import format_markdown_image_only
        pkgs = [{"name": "openssl-libs", "evr": "3.0.7-25.el9_3", "sourcerpm": "openssl-3.0.7-25.el9_3.src.rpm", "images": ["operator"]}]
        cves = {"openssl": [{"cve_id": "CVE-2024-1234", "severity": "important", "cvss3_score": "7.5", "public_date": "2024-01-15", "summary": "test", "link": "https://example.com"}]}
        report = format_markdown_image_only(pkgs, cves, "registry.redhat.io/rhosdt/opentelemetry-rhel9-operator:latest")
        self.assertIn("CVE-2024-1234", report)
        self.assertIn("openssl", report)

    def test_lockfile_fixed_section(self):
        from rpm_cve_check import format_markdown_with_lockfile
        pkgs = [{"name": "openssl-libs", "evr": "3.0.7-25.el9_3", "sourcerpm": "openssl-3.0.7-25.el9_3.src.rpm", "images": ["operator"]}]
        fixed = {"openssl": [{"cve_id": "CVE-2024-1234", "severity": "important", "cvss3_score": "7.5", "public_date": "2024-01-15", "summary": "test", "link": "https://example.com"}]}
        remaining = {}
        lock_by_source = {"openssl": {"name": "openssl-libs", "evr": "3.5.5-6.el9_8", "sourcerpm": "openssl-3.5.5-6.el9_8.src.rpm"}}
        report = format_markdown_with_lockfile(pkgs, fixed, remaining, "rpms.lock.yaml", "registry.redhat.io/rhosdt/opentelemetry-rhel9-operator:latest", lock_by_source)
        self.assertIn("CVEs Fixed by Lock File Update", report)
        self.assertIn("CVE-2024-1234", report)

    def test_none_severity_handled(self):
        from rpm_cve_check import format_markdown_image_only
        pkgs = [{"name": "openssl-libs", "evr": "3.0.7-25.el9_3", "sourcerpm": "openssl-3.0.7-25.el9_3.src.rpm", "images": ["operator"]}]
        cves = {"openssl": [{"cve_id": "CVE-2024-0000", "severity": None, "cvss3_score": None, "public_date": "", "summary": "test", "link": "https://example.com"}]}
        report = format_markdown_image_only(pkgs, cves, "registry.redhat.io/rhosdt/opentelemetry-rhel9-operator:latest")
        self.assertIn("Unknown", report)


class TestFormatYaml(unittest.TestCase):
    def test_image_only(self):
        from rpm_cve_check import format_yaml_image_only
        pkgs = [{"name": "openssl-libs", "evr": "3.0.7-25.el9_3", "sourcerpm": "openssl-3.0.7-25.el9_3.src.rpm", "images": ["operator"]}]
        cves = {"openssl": []}
        output = format_yaml_image_only(pkgs, cves, "registry.redhat.io/rhosdt/opentelemetry-rhel9-operator:latest")
        data = yaml.safe_load(output)
        self.assertIn("packages", data)


if __name__ == "__main__":
    unittest.main()
