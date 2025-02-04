#!/bin/bash
set -eu

#
# This script compares the upstream ClusterServiceVersion with the downstream ClusterServiceVersion.
# It only prints the diff output, the release manager must verify the changes between upstream and downstream.
# This is helpful if upstream changed the ClusterServiceVersion in a way which requires downstream changes to the patch script.
#

PRODUCT="${PWD##*/konflux-}"

podman build -t operator-bundle -f Dockerfile.bundle .
podman create --name operator-bundle operator-bundle
podman cp operator-bundle:/manifests/${PRODUCT}-operator.clusterserviceversion.yaml .

if [[ "$PRODUCT" = "jaeger" ]]; then
  git diff --no-index jaeger-operator/bundle/manifests/jaeger-operator.clusterserviceversion.yaml jaeger-operator.clusterserviceversion.yaml || true
elif [[ "$PRODUCT" = "opentelemetry" ]]; then
  git diff --no-index opentelemetry-operator/bundle/openshift/manifests/opentelemetry-operator.clusterserviceversion.yaml opentelemetry-operator.clusterserviceversion.yaml || true
elif [[ "$PRODUCT" = "tempo" ]]; then
  git diff --no-index tempo-operator/bundle/openshift/manifests/tempo-operator.clusterserviceversion.yaml tempo-operator.clusterserviceversion.yaml || true
else
  echo "This script must be run from a Konflux data repository."
  exit 1
fi

podman rm operator-bundle > /dev/null
rm *.clusterserviceversion.yaml
