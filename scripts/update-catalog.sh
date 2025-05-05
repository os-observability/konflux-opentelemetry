#!/bin/bash
set -xe

opm alpha render-template basic --output yaml catalog/catalog-template.yaml > catalog/opentelemetry-product/catalog.yaml
opm alpha render-template basic --output yaml --migrate-level bundle-object-to-csv-metadata catalog/catalog-template.yaml > catalog/opentelemetry-product-4.17/catalog.yaml
sed -i 's#quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-bundle#registry.redhat.io/rhosdt/opentelemetry-operator-bundle#g' catalog/opentelemetry-product/catalog.yaml
sed -i 's#quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-bundle#registry.redhat.io/rhosdt/opentelemetry-operator-bundle#g' catalog/opentelemetry-product-4.17/catalog.yaml
opm validate catalog/opentelemetry-product
opm validate catalog/opentelemetry-product-4.17