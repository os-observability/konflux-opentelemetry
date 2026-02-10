#!/usr/bin/env bash

set -eu
set -a && . bundle.env && set +a

if [[ $REGISTRY == "registry.redhat.io" || $REGISTRY == "registry.stage.redhat.io" ]]; then
  OTEL_COLLECTOR_IMAGE_PULLSPEC="$REGISTRY/rhosdt/opentelemetry-collector-rhel9@${OTEL_COLLECTOR_IMAGE_PULLSPEC:(-71)}"
  OTEL_TARGET_ALLOCATOR_IMAGE_PULLSPEC="$REGISTRY/rhosdt/opentelemetry-target-allocator-rhel9@${OTEL_TARGET_ALLOCATOR_IMAGE_PULLSPEC:(-71)}"
  OTEL_OPERATOR_IMAGE_PULLSPEC="$REGISTRY/rhosdt/opentelemetry-rhel9-operator@${OTEL_OPERATOR_IMAGE_PULLSPEC:(-71)}"
fi

export CSV_FILE=manifests/opentelemetry-operator.clusterserviceversion.yaml

sed -i "s#opentelemetry-collector-container-pullspec#$OTEL_COLLECTOR_IMAGE_PULLSPEC#g" patch_csv.yaml
sed -i "s#opentelemetry-target-allocator-container-pullspec#$OTEL_TARGET_ALLOCATOR_IMAGE_PULLSPEC#g" patch_csv.yaml
sed -i "s#opentelemetry-operator-container-pullspec#$OTEL_OPERATOR_IMAGE_PULLSPEC#g" patch_csv.yaml

#export AMD64_BUILT=$(skopeo inspect --raw docker://${OTEL_OPERATOR_IMAGE_PULLSPEC} | jq -e '.manifests[] | select(.platform.architecture=="amd64")')
#export ARM64_BUILT=$(skopeo inspect --raw docker://${OTEL_OPERATOR_IMAGE_PULLSPEC} | jq -e '.manifests[] | select(.platform.architecture=="arm64")')
#export PPC64LE_BUILT=$(skopeo inspect --raw docker://${OTEL_OPERATOR_IMAGE_PULLSPEC} | jq -e '.manifests[] | select(.platform.architecture=="ppc64le")')
#export S390X_BUILT=$(skopeo inspect --raw docker://${OTEL_OPERATOR_IMAGE_PULLSPEC} | jq -e '.manifests[] | select(.platform.architecture=="s390x")')
export AMD64_BUILT=true
export ARM64_BUILT=true
export PPC64LE_BUILT=true
export S390X_BUILT=true

export EPOC_TIMESTAMP=$(date +%s)

# time for some direct modifications to the csv
python3 patch_csv.py
python3 patch_annotations.py
