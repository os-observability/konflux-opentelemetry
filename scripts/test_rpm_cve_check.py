#!/usr/bin/env python
import os
import tempfile
import unittest

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


if __name__ == "__main__":
    unittest.main()
