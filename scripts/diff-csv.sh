#!/bin/bash
set -eu

#
# This script compares the upstream ClusterServiceVersion with the downstream ClusterServiceVersion.
# It only prints the diff output, the release manager must verify the changes between upstream and downstream.
# This is helpful if upstream changed the ClusterServiceVersion in a way which requires downstream changes to the patch script.
#

DIR="${PWD##*/}"

if [[ "$DIR" = "konflux-jaeger" ]]; then
  podman build -t jaeger-bundle -f Dockerfile.bundle . && podman cp $(podman create jaeger-bundle):/manifests/jaeger-operator.clusterserviceversion.yaml .
  git diff --no-index jaeger-operator/bundle/manifests/jaeger-operator.clusterserviceversion.yaml jaeger-operator.clusterserviceversion.yaml || true
  rm jaeger-operator.clusterserviceversion.yaml
elif [[ "$DIR" = "konflux-opentelemetry" ]]; then
  podman build -t opentelemetry-bundle -f Dockerfile.bundle . && podman cp $(podman create opentelemetry-bundle):/manifests/opentelemetry-operator.clusterserviceversion.yaml .
  git diff --no-index opentelemetry-operator/bundle/openshift/manifests/opentelemetry-operator.clusterserviceversion.yaml opentelemetry-operator.clusterserviceversion.yaml || true
  rm opentelemetry-operator.clusterserviceversion.yaml
elif [[ "$DIR" = "konflux-tempo" ]]; then
  podman build -t tempo-bundle -f Dockerfile.bundle . && podman cp $(podman create tempo-bundle):/manifests/tempo-operator.clusterserviceversion.yaml .
  git diff --no-index tempo-operator/bundle/openshift/manifests/tempo-operator.clusterserviceversion.yaml tempo-operator.clusterserviceversion.yaml || true
  rm tempo-operator.clusterserviceversion.yaml
else
  echo "This script must be run from a Konflux data repository."
  exit 1
fi
