#!/usr/bin/env python
"""
This script adds a new bundle to the catalog template and regenerates the catalogs.

The script creates a new entry for the bundle with the version information from the `bundle-patch/patch_csv.yaml` file
and the bundle pullspec from the specified snapshot (`--snapshot <snapshot>`).

Example:
$ ~/redhat/dist/konflux/konflux/scripts/update-catalog.py --snapshot tempo-4jcs8
"""
from pathlib import Path
import subprocess
import json
import argparse
import yaml

repository = Path().absolute().name
application = repository.replace("konflux-", "").replace("opentelemetry", "otel")
if not repository.startswith("konflux-"):
    raise Exception("This script must be run from a Konflux data repository.")

registry_mappings = {
    "jaeger": {
        "stage": "quay.io/redhat-user-workloads/rhosdt-tenant/jaeger/jaeger-bundle",
        "prod": "registry.redhat.io/rhosdt/jaeger-operator-bundle"
    },
    "otel": {
        "stage":"quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-bundle",
        "prod": "registry.redhat.io/rhosdt/opentelemetry-operator-bundle"
    },
    "tempo": {
        "stage": "quay.io/redhat-user-workloads/rhosdt-tenant/tempo/tempo-bundle",
        "prod": "registry.redhat.io/rhosdt/tempo-operator-bundle"
    },
}

def get_bundle_pullspec(args):
    p = subprocess.run(["kubectl", "get", "snapshot", args.snapshot, "-o", "json"], capture_output=True, text=True, check=True)
    snapshot = json.loads(p.stdout)

    for component in snapshot["spec"]["components"]:
        if "-bundle-" in component["name"]:
            return component["containerImage"]
    return None

def update_catalog_template(bundle_pullspec):
    with open("bundle-patch/patch_csv.yaml", "r") as f:
        bundle_patch = yaml.safe_load(f)

    with open("catalog/catalog-template.yaml", "r") as f:
        catalog_template = yaml.safe_load(f)

    # update the registry of all existing (already published) bundles
    for entry in catalog_template["entries"]:
        if "image" in entry:
            entry["image"] = entry["image"].replace(registry_mappings[application]["stage"], registry_mappings[application]["prod"])

    name = bundle_patch["metadata"]["name"]
    replaces = bundle_patch["spec"]["replaces"]
    skipRange = bundle_patch["metadata"]["extra_annotations"]["olm.skipRange"]

    for bundle in catalog_template["entries"][1]["entries"]:
        if bundle["name"] == name:
            bundle["replaces"] = replaces
            bundle["skipRange"] = skipRange
            catalog_template["entries"][-1]["image"] = bundle_pullspec
            break
    else:
        # if bundle does not exist in the catalog template
        catalog_template["entries"][1]["entries"].append({
            "name": name,
            "replaces": replaces,
            "skipRange": skipRange
        })
        catalog_template["entries"].append({
            "image": bundle_pullspec,
            "schema": "olm.bundle",
        })

    with open("catalog/catalog-template.yaml", "w") as f:
        content = "---\n" + yaml.dump(catalog_template)
        f.write(content)

def update_catalog():
    if application == "jaeger":
        subprocess.run("""
        ./scripts/update-catalog-opm.sh jaeger
        """, shell=True, check=True)
    elif application == "otel":
        subprocess.run("""
        ./scripts/update-catalog-opm.sh opentelemetry
        """, shell=True, check=True)
    if application == "tempo":
        subprocess.run("""
        ./scripts/update-catalog-opm.sh tempo
        """, shell=True, check=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--snapshot', required=True)
    args = parser.parse_args()

    print("Get bundle pullspec from snapshot...")
    bundle_pullspec = get_bundle_pullspec(args)
    if not bundle_pullspec:
        raise Exception("bundle image not found")

    print("Updating catalog-template.yaml...")
    update_catalog_template(bundle_pullspec)

    print("Updating catalog...")
    update_catalog()

if __name__ == "__main__":
    main()
