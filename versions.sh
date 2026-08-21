#!/bin/bash
set -euo pipefail

# Propagates version information to various static files.
# This file is intentionally kept as a shellscript, to simplify product-specific modifications.


# TODO: update version
RHOSDT_VERSION=3.11
# TODO: set latest supported OCP version, see https://access.redhat.com/support/policy/updates/openshift#dates
MIN_OPENSHIFT_VERSION=4.12


echo "Fetching tags of all submodules..."
git submodule foreach --recursive "git fetch --tags" > /dev/null 2>&1
OPERATOR_VERSION=$(cd opentelemetry-operator && awk -F= '/^opentelemetry-collector=/ {print $2}' versions.txt)
COLLECTOR_VERSION=$(cd redhat-opentelemetry-collector && yq '.dist.version' manifest.yaml)

echo "Fetching version of latest released bundle..."
RELEASED_BUNDLE_VERSION=$(kubectl get packagemanifests.packages.operators.coreos.com opentelemetry-product -o jsonpath='{.status.channels[0].currentCSV}' | sed 's/^.*\.v//')
RELEASED_VERSION=${RELEASED_BUNDLE_VERSION%%-*}
RELEASED_BUILDNUMBER=${RELEASED_BUNDLE_VERSION##*-}
if [[ "${OPERATOR_VERSION}" = "${RELEASED_VERSION}" ]]; then
  BUNDLE_BUILDNUMBER=$((RELEASED_BUILDNUMBER+1))
else
  BUNDLE_BUILDNUMBER=1
fi
BUNDLE_VERSION=${OPERATOR_VERSION}-${BUNDLE_BUILDNUMBER}

echo "Updating version numbers in Dockerfiles and bundle..."
echo
echo "Operator: ${OPERATOR_VERSION}"
echo "Collector: ${COLLECTOR_VERSION}"
echo "Bundle: ${BUNDLE_VERSION} (previous: ${RELEASED_BUNDLE_VERSION})"
echo "Min OpenShift version: ${MIN_OPENSHIFT_VERSION}"

# container labels
sed -Ei "s/^ARG VERSION=.*/ARG VERSION=${BUNDLE_VERSION}/g" Dockerfile.*
sed -Ei "s/cpe=[^ ]*/cpe=\"cpe:\/a:redhat:openshift_distributed_tracing:${RHOSDT_VERSION}::el9\"/g" Dockerfile.*
sed -Ei "s/com.redhat.openshift.versions=[^ ]*/com.redhat.openshift.versions=v${MIN_OPENSHIFT_VERSION}/g" Dockerfile.bundle

# CSV
yq -i e ".spec.version = \"${BUNDLE_VERSION}\"" bundle-patch/patch_csv.yaml
yq -i e ".metadata.name = \"opentelemetry-operator.v${BUNDLE_VERSION}\"" bundle-patch/patch_csv.yaml
yq -i e ".spec.replaces = \"opentelemetry-operator.v${RELEASED_BUNDLE_VERSION}\"" bundle-patch/patch_csv.yaml
sed -Ei "s/olm.skipRange: '>=(.*) <[^']*/olm.skipRange: '>=\1 <${BUNDLE_VERSION}/g" bundle-patch/patch_csv.yaml

# Integration test pipeline defaults.
# The IntegrationTestScenario does not override these params, so the defaults are the source of truth
# for the versions asserted by the check-opentelemetry-version task and the test branch that is cloned.
# OPERATOR_VERSION and COLLECTOR_VERSION are computed above; only the target allocator version is not.
TARGETALLOCATOR_VERSION=$(cd opentelemetry-operator && awk -F= '/^targetallocator=/ {print $2}' versions.txt)
TESTS_BRANCH="rhosdt-${RHOSDT_VERSION}"

# Sets a pipeline param's default value, targeting the "default:" line that follows "- name: <param>".
set_pipeline_default() {
  local file=$1 param=$2 value=$3
  sed -Ei "/^ *- name: ${param}$/,/default:/ s|default: .*|default: \"${value}\"|" "$file"
}

E2E_PIPELINES=(
  .tekton/integration-tests/pipelines/opentelemetry-operator-e2e-test-pipeline-4-14.yaml
  .tekton/integration-tests/pipelines/opentelemetry-operator-e2e-test-pipeline-4-18.yaml
)
for pipeline in "${E2E_PIPELINES[@]}"; do
  set_pipeline_default "${pipeline}" operator_version "${OPERATOR_VERSION}"
  set_pipeline_default "${pipeline}" operator_otel_collector_version "${OPERATOR_VERSION}"
  set_pipeline_default "${pipeline}" operator_targetallocator_version "${TARGETALLOCATOR_VERSION}"
  set_pipeline_default "${pipeline}" otel_collector_version "${COLLECTOR_VERSION}"
  set_pipeline_default "${pipeline}" otel_tests_branch "${TESTS_BRANCH}"
  set_pipeline_default "${pipeline}" rhosdt_version "${RHOSDT_VERSION}"
done

# The 4-21-olmv1 pipeline intentionally has no defaults (params supplied externally) and is skipped.

UPGRADE_PIPELINES=(
  .tekton/integration-tests/pipelines/opentelemetry-operator-upgrade-test-fbc-pipeline-4-14.yaml
  .tekton/integration-tests/pipelines/opentelemetry-operator-upgrade-test-fbc-pipeline-4-18.yaml
)
for pipeline in "${UPGRADE_PIPELINES[@]}"; do
  set_pipeline_default "${pipeline}" operator_csv_version "opentelemetry-operator.v${BUNDLE_VERSION}"
  set_pipeline_default "${pipeline}" collector_version "${COLLECTOR_VERSION}"
  set_pipeline_default "${pipeline}" ta_version "${TARGETALLOCATOR_VERSION}"
  set_pipeline_default "${pipeline}" otel_tests_branch "${TESTS_BRANCH}"
done
