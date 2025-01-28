# konflux-opentelemetry

This repository contains Konflux configuration to build Red Hat build of OpenTelemetry.

## Multiple release versions

The Konflux project is configured to maintain builds in the `main` and `development` branch.
The build pipelines are identical except the value of pipeline trigger `pipelinesascode.tekton.dev/on-cel-expression` which defines branch name.

The branch name can be changed by:
```bash
sed -i 's/target_branch == \"main\"/target_branch == \"development\"/g' .tekton/*.yaml
```

## Build locally

```bash
docker login brew.registry.redhat.io -u
docker login registry.redhat.io -u

git submodule update --init --recursive

podman build -t docker.io/user/otel-operator:$(date +%s) -f Dockerfile.operator 
```

### Generate `requirements.txt` for python

```bash
 ~/.local/bin/pip-compile requirements-build.in --generate-hashes  --allow-unsafe 
```

### Generate prefetch for RPM

From [document](https://docs.google.com/document/d/1c58NGQPuuni2hFgz0Ll0vDj0IUvBHa7uF4eKnTVa5Sw/edit).

```bash
podman run --rm -v "$PWD:$PWD:z" -w "$PWD"  registry.redhat.io/ubi8/ubi-minimal:8.10-1052.1724178568  cp -r /etc/yum.repos.d/. .
# Enable -source repositories: `enabled = 1`
# Generate lock file
~/.local/bin/rpm-lockfile-prototype -f Dockerfile.collector  rpms.in.yaml --outfile rpms.lock.yaml
```

## Release
### Application
Update all base images (merge renovatebot PRs).

Create a PR `Release - update upstream sources x.y`:
1. Update git submodules with upstream versions
  **Note:** If you use a forked repository instead of upstream, you must sync the git tags.
  The version information is set dynamically using `git describe --tags` in the Dockerfile, and is crucial for e.g. the upgrade process of the operator.

### Bundle
Wait for renovatebot to create PRs to update the hash in the `bundle-patch/update_bundle.sh` file, and merge all of them.

Create a PR `Release - update bundle version x.y` and update [patch_csv.yaml](./bundle-patch/patch_csv.yaml) by submitting a PR with follow-up changes:
1. `metadata.name` with the current version e.g. `opentelemetry-operator.v0.108.0-1`
1. `metadata.extra_annotations.olm.skipRange` with the version being productized e.g. `'>=0.33.0 <0.108.0-1'`
1. `spec.version` with the current version e.g. `opentelemetry-operator.v0.108.0-1`
1. `spec.replaces` with [the previous shipped version](https://catalog.redhat.com/software/containers/rhosdt/opentelemetry-operator-bundle/615618406feffc5384e84400) of CSV e.g. `opentelemetry-operator.v0.107.0-4`
1. Update `release`, `version` and `com.redhat.openshift.versions` (minimum OCP version) labels in [bundle dockerfile](./Dockerfile.bundle)
1. Verify diff of upstream and downstream ClusterServiceVersion
   ```bash
   podman build -t opentelemetry-bundle -f Dockerfile.bundle . && podman cp $(podman create opentelemetry-bundle):/manifests/opentelemetry-operator.clusterserviceversion.yaml .
   git diff --no-index opentelemetry-operator/bundle/openshift/manifests/opentelemetry-operator.clusterserviceversion.yaml opentelemetry-operator.clusterserviceversion.yaml
   rm opentelemetry-operator.clusterserviceversion.yaml
   ```

### Catalog
Once the PR is merged and bundle is built, create another PR `Release - update catalog x.y` with:
* Updated [catalog template](./catalog/catalog-template.yaml) with the new bundle (get the bundle pullspec from `kubectl get component otel-bundle -o yaml`):
   ```bash
   opm alpha render-template basic --output yaml catalog/catalog-template.yaml > catalog/opentelemetry-product/catalog.yaml && \
   opm alpha render-template basic --output yaml --migrate-level bundle-object-to-csv-metadata catalog/catalog-template.yaml > catalog/opentelemetry-product-4.17/catalog.yaml && \
   sed -i 's#quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-bundle#registry.redhat.io/rhosdt/opentelemetry-operator-bundle#g' catalog/opentelemetry-product/catalog.yaml  && \
   sed -i 's#quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-bundle#registry.redhat.io/rhosdt/opentelemetry-operator-bundle#g' catalog/opentelemetry-product-4.17/catalog.yaml  && \
   opm validate catalog/opentelemetry-product && \
   opm validate catalog/opentelemetry-product-4.17
   ```

## Test locally

Images can be found at https://quay.io/organization/redhat-user-workloads (search for `rhosdt-tenant/otel`).

### Deploy bundle

get latest pullspec from `kubectl get component otel-bundle-quay -o yaml`, then run:
```bash
kubectl create namespace openshift-opentelemetry-operator
operator-sdk run bundle -n openshift-opentelemetry-operator quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-bundle-quay@sha256:7177eceb4ab73de1bda2bc2c648e02bbcbd90f09efc645cff2524b1546bc765c
operator-sdk cleanup -n openshift-opentelemetry-operator opentelemetry-product
```

### Deploy catalog

Get catalog for specific version from [Konflux](https://console.redhat.com/application-pipeline/workspaces/rhosdt/applications/otel-fbc-v4-15/components/otel-fbc-v4-15)

```yaml
kubectl apply -f - <<EOF
apiVersion: operators.coreos.com/v1alpha1
kind: CatalogSource
metadata:
   name: konflux-catalog-otel
   namespace: openshift-marketplace
spec:
   sourceType: grpc
   image: quay.io/redhat-user-workloads/rhosdt-tenant/otel/otel-fbc-v4-15@sha256:337009c69204eed22bd90acf5af45f3db678bd65531c8847c59e9532f8427d29
   displayName: Konflux Catalog OTEL
   publisher: grpc
EOF

kubectl get pods -w -n openshift-marketplace
kubectl delete CatalogSource konflux-catalog-otel -n openshift-marketplace
```

`Konflux catalog OTEL` menu should appear in the OCP console under Operators->OperatorHub.

#### Mirror images

The catalog uses pullspecs from `registry.redhat.io` which are not available before the release. Therefore the images need to be re-mapped.

From https://konflux.pages.redhat.com/docs/users/getting-started/building-olm-products.html#releasing-a-fbc-component

```yaml
kubectl apply -f - <<EOF
apiVersion: config.openshift.io/v1
kind: ImageDigestMirrorSet
metadata:
  name: fbc-testing-idms
spec:
  imageDigestMirrors:
  - source: registry.redhat.io/rhosdt/opentelemetry-collector-rhel8
    mirrors:
      - quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-collector
  - source: registry.redhat.io/rhosdt/opentelemetry-target-allocator-rhel8
    mirrors:
      - quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-target-allocator
  - source: registry.redhat.io/rhosdt/opentelemetry-rhel8-operator
    mirrors:
       - quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-operator
  - source: registry.redhat.io/rhosdt/opentelemetry-operator-bundle
    mirrors:
       - quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-bundle
EOF
```

### Inspect bundle image

```bash
mkdir /tmp/bundle
docker image save -o /tmp/bundle/image.tar quay.io/redhat-user-workloads/rhosdt-tenant/otel/otel-bundle@sha256:193358e912cd6a1d06eacf27363d85f2082c21596084110f026f43682ca3cecf
tar xvf /tmp/bundle/image.tar -C /tmp/bundle
tar xvf /tmp/bundle/c6f6e1b5441a6acfc03bb40f4b2d47b98dcfca1761e77e47fba004653eb596d7/layer.tar -C /tmp/bundle/c6f6e1b5441a6acfc03bb40f4b2d47b98dcfca1761e77e47fba004653eb596d7
```

### List tags

```bash
skopeo list-tags docker://brew.registry.redhat.io/rh-osbs/openshift-golang-builder
```

### Inspect multi-arch image

The pinned image pullspec in [update-bundle.sh](bundle-patch/update_bundle.sh) should be image index digest.
The `skopeo` should return a list of manifests. 

```bash
skopeo inspect --raw docker://quay.io/redhat-user-workloads/rhosdt-tenant/otel/operator@sha256:2a8b137c4b9774405a84c4719da6162a56cb97761dce68e59a0d2ed974fae1f0  | jq                                                                                                                                                                                                  ploffay@fedora
{
  "schemaVersion": 2,
  "mediaType": "application/vnd.oci.image.index.v1+json",
  "manifests": [
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "digest": "sha256:5c7b1445c7d1f170bdcdcb814c7015a898d861807992fe61f8c36b8fe7ebfb3f",
      "size": 947,
      "platform": {
        "architecture": "amd64",
        "os": "linux"
      }
    },
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "digest": "sha256:b69e51d647805347e8e55b16cb2114a8bfc240ac4f91db71e21b78af012f2817",
      "size": 947,
      "platform": {
        "architecture": "arm64",
        "os": "linux"
      }
    },
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "digest": "sha256:761683f288d76d24d75699da56981d3baa9d24883b3bc19f67821d8f6d766321",
      "size": 947,
      "platform": {
        "architecture": "ppc64le",
        "os": "linux"
      }
    },
    {
      "mediaType": "application/vnd.oci.image.manifest.v1+json",
      "digest": "sha256:c1f79211f283a60ca066a4333cc904aeeca35d3aaf351217631d6a21aa58ce18",
      "size": 947,
      "platform": {
        "architecture": "s390x",
        "os": "linux"
      }
    }
  ]
}
```

The `sosign` returns list of platforms even for no image index digest:

```bash
cosign download attestation quay.io/redhat-user-workloads/rhosdt-tenant/otel/operator@sha256:5c7b1445c7d1f170bdcdcb814c7015a898d861807992fe61f8c36b8fe7ebfb3f | jq -r '.payload | @base64d | fromjson | .predicate.invocation.parameters'                                                                                                                        127 ↵ ploffay@fedora
{
  "build-args": [],
  "build-args-file": "",
  "build-image-index": "true",
  "build-platforms": [
    "linux/x86_64",
    "linux/arm64",
    "linux/ppc64le",
    "linux/s390x"
  ],
  "build-source-image": "false",
  "dockerfile": "Dockerfile.operator",
  "git-url": "https://github.com/pavolloffay/konflux-opentelemetry",
  "hermetic": "false",
  "image-expires-after": "",
  "output-image": "quay.io/redhat-user-workloads/rhosdt-tenant/otel/operator:00ebe9a6475bda2c3f7be7278841de0d7d81feab",
  "path-context": ".",
  "prefetch-input": "",
  "rebuild": "false",
  "revision": "00ebe9a6475bda2c3f7be7278841de0d7d81feab",
  "skip-checks": "false"
}

skopeo inspect --raw docker://quay.io/redhat-user-workloads/rhosdt-tenant/otel/operator@sha256:5c7b1445c7d1f170bdcdcb814c7015a898d861807992fe61f8c36b8fe7ebfb3f | jq                                                                                                                                                                                             127 ↵ ploffay@fedora
{
  "schemaVersion": 2,
  "mediaType": "application/vnd.oci.image.manifest.v1+json",
  "config": {
    "mediaType": "application/vnd.oci.image.config.v1+json",
    "digest": "sha256:5bc060cce164bec15ed725164a272c7aa670a211dadab60d4b4ce1a63cb6ba9e",
    "size": 8317
  },
  "layers": [
    {
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
      "digest": "sha256:2384c7c17092245bda9218fee9b2ae475ee8a53cd8a66e63c1d5f37433276ff0",
      "size": 39365328
    },
    {
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
      "digest": "sha256:978e7c294b1c89f7c5f330764d97a80007288964bfd640388024afcd0387dc91",
      "size": 45065115
    },
    {
      "mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
      "digest": "sha256:326159d96fc4212c9c599da6c577e490fb5c87c0f6d51ac3203e69f57c60ccbb",
      "size": 99814
    }
  ],
  "annotations": {
    "org.opencontainers.image.base.digest": "sha256:11bb492c19d974e6f67be661e76691e977184e98aff1cfad365363ae9055cff0",
    "org.opencontainers.image.base.name": "registry.redhat.io/ubi8/ubi-minimal:8.10-1052.1724178568"
  }
}
```

### Extract file based catalog from OpenShift index

```bash
podman cp $(podman create --name tc registry.redhat.io/redhat/redhat-operator-index:v4.17):/configs/opentelemetry-product opentelemetry-product-4.17  && podman rm tc
opm migrate opentelemetry-product-4.17 opentelemetry-product-4.17-migrated
opm alpha convert-template basic --output yaml ./opentelemetry-product-4.17-migrated/opentelemetry-product/catalog.json > catalog/catalog-template.yaml
```
