#!/usr/bin/env bash

set -e

# The pullspec should be image index, check if all architectures are there with: skopeo inspect --raw docker://$IMG | jq
export OTEL_COLLECTOR_IMAGE_PULLSPEC="quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-collector@sha256:6f27fdde7162167d2a306f281d894de2d0e2d0652b6ba5f8d9f3937cda67e44d"
# Separate due to merge conflicts
export OTEL_TARGET_ALLOCATOR_IMAGE_PULLSPEC="quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-target-allocator@sha256:e840b6fcedee3d488966c5df76e5b535680745753286c4ccd335bdea2422cd10"
# Separate due to merge conflicts
export OTEL_OPERATOR_IMAGE_PULLSPEC="quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-operator@sha256:163f0e973369c3cabf45e4f603bd6b11bf1c6eef26777c6a800efc5767d7fb3a"
# Separate due to merge conflicts
# TODO, we used to set the proxy image per OCP version
export OSE_KUBE_RBAC_PROXY_PULLSPEC="registry.redhat.io/openshift4/ose-kube-rbac-proxy@sha256:8204d45506297578c8e41bcc61135da0c7ca244ccbd1b39070684dfeb4c2f26c"

if [[ $REGISTRY == "registry.redhat.io" ||  $REGISTRY == "registry.stage.redhat.io" ]]; then
  OTEL_COLLECTOR_IMAGE_PULLSPEC="$REGISTRY/rhosdt/opentelemetry-collector-rhel8@${OTEL_COLLECTOR_IMAGE_PULLSPEC:(-71)}"
  OTEL_TARGET_ALLOCATOR_IMAGE_PULLSPEC="$REGISTRY/rhosdt/opentelemetry-target-allocator-rhel8@${OTEL_TARGET_ALLOCATOR_IMAGE_PULLSPEC:(-71)}"
  OTEL_OPERATOR_IMAGE_PULLSPEC="$REGISTRY/rhosdt/opentelemetry-rhel8-operator@${OTEL_OPERATOR_IMAGE_PULLSPEC:(-71)}"
fi

export CSV_FILE=/manifests/opentelemetry-operator.clusterserviceversion.yaml

sed -i "s#opentelemetry-collector-container-pullspec#$OTEL_COLLECTOR_IMAGE_PULLSPEC#g" patch_csv.yaml
sed -i "s#opentelemetry-target-allocator-container-pullspec#$OTEL_TARGET_ALLOCATOR_IMAGE_PULLSPEC#g" patch_csv.yaml
sed -i "s#ose-kube-rbac-proxy-container-pullspec#$OSE_KUBE_RBAC_PROXY_PULLSPEC#g" patch_csv.yaml
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
