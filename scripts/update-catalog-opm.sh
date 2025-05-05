#!/bin/bash
set -eu

if [ $# -lt 1 ]
  then
    echo "usage: $0 [opentelemetry|tempo|jaeger]"
    exit 1
fi

PRODUCT="$1"

if [[ "$PRODUCT" = "jaeger" ]]; then
  opm alpha render-template basic --output yaml catalog/catalog-template.yaml > catalog/jaeger-product/catalog.yaml &&
  opm alpha render-template basic --output yaml --migrate-level bundle-object-to-csv-metadata catalog/catalog-template.yaml > catalog/jaeger-product-4.17/catalog.yaml &&
  sed -i 's#quay.io/redhat-user-workloads/rhosdt-tenant/jaeger/jaeger-bundle#registry.redhat.io/rhosdt/jaeger-operator-bundle#g' catalog/jaeger-product/catalog.yaml &&
  sed -i 's#quay.io/redhat-user-workloads/rhosdt-tenant/jaeger/jaeger-bundle#registry.redhat.io/rhosdt/jaeger-operator-bundle#g' catalog/jaeger-product-4.17/catalog.yaml &&
  opm validate catalog/jaeger-product &&
  opm validate catalog/jaeger-product-4.17
elif [[ "$PRODUCT" = "opentelemetry" ]]; then
  opm alpha render-template basic --output yaml catalog/catalog-template.yaml > catalog/opentelemetry-product/catalog.yaml
  opm alpha render-template basic --output yaml --migrate-level bundle-object-to-csv-metadata catalog/catalog-template.yaml > catalog/opentelemetry-product-4.17/catalog.yaml
  sed -i 's#quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-bundle#registry.redhat.io/rhosdt/opentelemetry-operator-bundle#g' catalog/opentelemetry-product/catalog.yaml
  sed -i 's#quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-bundle#registry.redhat.io/rhosdt/opentelemetry-operator-bundle#g' catalog/opentelemetry-product-4.17/catalog.yaml
  opm validate catalog/opentelemetry-product
  opm validate catalog/opentelemetry-product-4.17
elif [[ "$PRODUCT" = "tempo" ]]; then
  opm alpha render-template basic --output yaml catalog/catalog-template.yaml > catalog/tempo-product/catalog.yaml &&
  opm alpha render-template basic --output yaml --migrate-level bundle-object-to-csv-metadata catalog/catalog-template.yaml > catalog/tempo-product-4.17/catalog.yaml &&
  sed -i 's#quay.io/redhat-user-workloads/rhosdt-tenant/tempo/tempo-bundle#registry.redhat.io/rhosdt/tempo-operator-bundle#g' catalog/tempo-product/catalog.yaml &&
  sed -i 's#quay.io/redhat-user-workloads/rhosdt-tenant/tempo/tempo-bundle#registry.redhat.io/rhosdt/tempo-operator-bundle#g' catalog/tempo-product-4.17/catalog.yaml &&
  opm validate catalog/tempo-product &&
  opm validate catalog/tempo-product-4.17
else
  echo "This script must be run from a Konflux data repository."
  exit 1
fi
