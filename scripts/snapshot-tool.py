#!/usr/bin/env python
"""
This script fetches the specified Konflux snapshot and shows the git commit information of the component builds.
This helps you confirm that all components of the snapshot are built from a specific commit, which might not be the case if some builds failed.
Additionally, it can update the `bundle-patch/bundle.env` file with the pullspecs from the specified snapshot.

You can specify a snapshot with
* `--snapshot <snapshot>`: fetch the selected snapshot
* `--commit <commit>`: fetch the latest snapshot of a specified commit
* by default, it fetches the latest snapshot triggered by a 'push' event.


Usage:

$ ./scripts/snapshot-tool.py --help
usage: snapshot-tool.py [-h] [--snapshot SNAPSHOT | --commit COMMIT] [--update-bundle-pullspecs]

options:
  -h, --help            show this help message and exit
  --snapshot SNAPSHOT   Fetch the specified snapshot by name
  --commit COMMIT       Fetch the latest snapshot of the specified commit
  --update-bundle-pullspecs
                        Update the pullspecs in the bundle-patch/bundle.env file

                        
Example:

$ ../konflux-opentelemetry/scripts/snapshot-tool.py
Snapshot tempo-main-dxv8s

COMPONENT                   COMMIT DATE           REVISION                                  COMMIT MESSAGE
tempo-bundle-main           2025-01-29T09:00:33Z  15029564f5ed5706cc55d53dc9b005b2436814df  Pin branch name to main
tempo-gateway-main          2025-01-29T09:00:33Z  15029564f5ed5706cc55d53dc9b005b2436814df  Pin branch name to main
tempo-opa-main              2025-01-29T09:00:33Z  15029564f5ed5706cc55d53dc9b005b2436814df  Pin branch name to main
tempo-operator-main         2025-01-29T09:00:33Z  15029564f5ed5706cc55d53dc9b005b2436814df  Pin branch name to main
tempo-query-main            2025-01-29T09:00:33Z  15029564f5ed5706cc55d53dc9b005b2436814df  Pin branch name to main
tempo-tempo-main            2025-01-29T09:00:33Z  15029564f5ed5706cc55d53dc9b005b2436814df  Pin branch name to main
"""
from pathlib import Path
import subprocess
import json
import re
import argparse
from urllib.request import urlopen, Request
from datetime import datetime

repository = Path().absolute().name
application = repository.replace("konflux-", "").replace("opentelemetry", "otel")
if not repository.startswith("konflux-"):
    raise Exception("This script must be run from a Konflux data repository.")

def is_latest_creationTimestamp(a, b):
    """
    verifies creation timestamp of two resources
    returns True if resource B is more recent than A
    """
    date_a = datetime.fromisoformat(a["metadata"]["creationTimestamp"])
    date_b = datetime.fromisoformat(b["metadata"]["creationTimestamp"])
    return date_a < date_b

def get_latest_resource(resources):
    latest_resource = None
    for resource in resources["items"]:
        if not latest_resource or is_latest_creationTimestamp(latest_resource, resource):
            latest_resource = resource
    return latest_resource

def get_snapshot(args):
    if args.snapshot:
        p = subprocess.run(["kubectl", "get", "snapshot", args.snapshot, "-o", "json"], capture_output=True, text=True, check=True)
        return json.loads(p.stdout)
    elif args.commit:
        p = subprocess.run(["kubectl", "get", "snapshot", "-l", f"appstudio.openshift.io/application={application}-{args.version},pac.test.appstudio.openshift.io/sha={args.commit}", "-o", "json"], capture_output=True, text=True, check=True)
        snapshots = json.loads(p.stdout)
        if len(snapshots["items"]) == 0:
            raise Exception("No snapshot found.")
        return get_latest_resource(snapshots)
    else:
        p = subprocess.run(["kubectl", "get", "snapshot", "-l", f"appstudio.openshift.io/application={application}-{args.version},pac.test.appstudio.openshift.io/event-type=push", "-o", "json"], capture_output=True, text=True, check=True)
        snapshots = json.loads(p.stdout)
        if len(snapshots["items"]) == 0:
            raise Exception("No snapshot found.")
        return get_latest_resource(snapshots)

COMMIT_DATA_CACHE = {}
def get_commit_info(commit):
    if commit in COMMIT_DATA_CACHE:
        return COMMIT_DATA_CACHE[commit]

    url = f"https://api.github.com/repos/os-observability/{repository}/commits/{commit}"
    with urlopen(Request(url)) as response:
        COMMIT_DATA_CACHE[commit] = json.load(response)
    return COMMIT_DATA_CACHE[commit]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="main", help="Version, supported values: main, development")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--snapshot", help="Fetch the specified snapshot by name")
    group.add_argument("--commit", help="Fetch the latest snapshot of the specified commit")
    parser.add_argument("--update-bundle-pullspecs", action="store_true", help="Update the pullspecs in the bundle-patch/bundle.env file")
    args = parser.parse_args()

    with open("bundle-patch/bundle.env", "r") as f:
        bundle_env = f.read()

    snapshot = get_snapshot(args)
    components = [{**component, "commit_info": get_commit_info(component["source"]["git"]["revision"])} for component in snapshot["spec"]["components"]]
    components_sorted = sorted(components, key=lambda component: component["commit_info"]["commit"]["committer"]["date"]+component["name"])

    print(f"Snapshot {snapshot['metadata']['name']}\n")
    print(f"{'COMPONENT':<26}  {'COMMIT DATE':<20}  {'REVISION':<40}  {'COMMIT MESSAGE'}")
    for component in components_sorted:
        name = component["name"]
        pullspec = component["containerImage"]
        revision = component["source"]["git"]["revision"]
        commit_date = component["commit_info"]["commit"]["committer"]["date"]
        commit_message = component["commit_info"]["commit"]["message"].split("\n")[0]
        env_name = name.replace(f"-{args.version}", "").replace("-", "_").upper() +  "_IMAGE_PULLSPEC"
        line_regexp = f"^{env_name}=.+$"

        print(f"{name:<26}  {commit_date:<20}  {revision:<40}  {commit_message}")
        if "-bundle-" in name:
            continue

        if not re.search(line_regexp, bundle_env, flags=re.MULTILINE):
            raise Exception(f"Cannot find env var {env_name} in bundle.env")
        bundle_env = re.sub(line_regexp, f"{env_name}={pullspec}", bundle_env, flags=re.MULTILINE)

    if args.update_bundle_pullspecs:
        with open("bundle-patch/bundle.env", "w") as f:
            f.write(bundle_env)

if __name__ == "__main__":
    main()
