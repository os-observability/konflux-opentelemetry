# konflux-opentelemetry

This repository contains Konflux configuration to build Red Hat build of OpenTelemetry.

## Multiple release versions

The Konflux project is configured to maintain builds in the `main` and `development` branches.
The build pipelines are identical except the value of pipeline trigger `pipelinesascode.tekton.dev/on-cel-expression`, labels `appstudio.openshift.io/{application,component}` and name.

The branch name can be changed by:
```bash
sed -i 's/main/development/g' .tekton/*.yaml
```

## Build locally

```bash
docker login brew.registry.redhat.io -u
docker login registry.redhat.io -u

git submodule update --init --recursive

podman build -t docker.io/user/otel-operator:$(date +%s) -f Dockerfile.operator 
```

## Release
### Application
Update all base images (merge renovatebot PRs).

Create a PR `Release - update upstream sources x.y`:
1. Update git submodules with upstream versions.
   **Note:** If you use a forked repository instead of upstream, you must sync the git tags.
   The version information is set dynamically using `git describe --tags` in the Dockerfile, and is crucial for e.g. the upgrade process of the operator.
1. Merge the PR and wait until all builds were successful.
   Retrigger failed builds by adding a comment `/test <name>` on the commit (or `/test` to retrigger all pipelines).

#### Change git submodule to another repository

```bash
git submodule set-url opentelemetry-operator https://github.com/os-observability/opentelemetry-operator.git
```

Now change to a different branch:

```bash
cd opentelemetry-operator
git remote -v
git fetch
git checkout rhosdt-3.5
```

Set branch in git `.gitmodules`. It can be useful to update the branch via `git submodule update --recursive --remote`:

```bash
git submodule set-branch --branch rhosdt-3.5 opentelemetry-operator
```

### Bundle
Create a PR `Release - update bundle version x.y` and update [patch_csv.yaml](./bundle-patch/patch_csv.yaml) by submitting a PR with follow-up changes:
1. `metadata.name` with the current version e.g. `opentelemetry-operator.v0.108.0-1`
1. `metadata.extra_annotations.olm.skipRange` with the version being productized e.g. `'>=0.33.0 <0.108.0-1'`
1. `spec.version` with the current version e.g. `opentelemetry-operator.v0.108.0-1`
1. `spec.replaces` with [the previous shipped version](./catalog/catalog-template.yaml) of CSV e.g. `opentelemetry-operator.v0.107.0-4`
1. Update `release`, `version` and `com.redhat.openshift.versions` (minimum OCP version) labels in all Dockerfiles e.g. `sed -i 's/0.107.0-4/0.108.0-1/g' Dockerfile.*`
1. Update image pullspecs of all components:
   ```bash
   KUBECONFIG=~/.kube/kubeconfig-konflux-public-rhosdt.yaml ./scripts/snapshot-tool.py --update-bundle-pullspecs
   ```
   Verify the commit date and hashes of each component.
1. Compare the diff between upstream and downstream ClusterServiceVersion:
   ```bash
   ./scripts/diff-csv.sh
   ```
1. Merge the PR and wait until all builds were successful.

### Catalog

The Konflux nudging is configured from the bundle component to update the [catalog.env](./catalog/catalog.env) file which contains the bundle pullspec.
The Github actions takes it and re-generates the catalogs.
In order to make this work the [catalog-template.yaml](./catalog/catalog-template.yaml) file must contain only a single bundle pullspec from the quay.io registry.

#### Update catalog manually

Once the components are released to prod, create another PR `Release - update catalog x.y` with:
1. Update the catalog:
   ```bash
   KUBECONFIG=~/.kube/kubeconfig-konflux-public-rhosdt.yaml ./scripts/update-catalog.py --snapshot <released_snapshot>
   ```
1. Merge the PR and wait until all builds were successful.

## Test locally

Images can be found at https://quay.io/organization/redhat-user-workloads (search for `rhosdt-tenant/otel`).

### Deploy Image Digest Mirror Set

Before using the bundle or catalog method for installing the operator, the ImageDigestMirrorSet needs to be created. The bundle and catalog uses pullspecs from `registry.redhat.io` which are not available before the release. Therefore the images need to be re-mapped.

From https://konflux.pages.redhat.com/docs/users/getting-started/building-olm-products.html#releasing-a-fbc-component

```
kubectl apply -f .tekton/images-mirror-set.yaml
```

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

## Guides

### Generate prefetch for RPMs

From [document](https://docs.google.com/document/d/1c58NGQPuuni2hFgz0Ll0vDj0IUvBHa7uF4eKnTVa5Sw/edit).

It requires a local installation of https://github.com/konflux-ci/rpm-lockfile-prototype.

```bash
podman run --rm -v "$PWD:$PWD:z" -w "$PWD"  registry.redhat.io/ubi8/ubi-minimal:8.10-1052.1724178568  cp -r /etc/yum.repos.d/. .
# Enable -source repositories: `enabled = 1`
# Generate lock file
~/.local/bin/rpm-lockfile-prototype -f Dockerfile.collector  rpms.in.yaml --outfile rpms.lock.yaml
```

### Generate new Konflux build pipeline file
```bash
KUBECONFIG=~/.kube/kubeconfig-konflux-public-rhosdt.yaml k annotate component otel-operator-main build.appstudio.openshift.io/request=configure-pac
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

#### Get image index pull spec
```bash
skopeo inspect --raw docker://brew.registry.redhat.io/rh-osbs/openshift-golang-builder:rhel_8_golang_1.23
{
    "Name": "brew.registry.redhat.io/rh-osbs/openshift-golang-builder",
    "Digest": "sha256:ca0c771ecd4f606986253f747e2773fe2960a6b5e8e7a52f6a4797b173ac7f56",
...
```

```bash
skopeo inspect --raw docker://brew.registry.redhat.io/rh-osbs/openshift-golang-builder@sha256:ca0c771ecd4f606986253f747e2773fe2960a6b5e8e7a52f6a4797b173ac7f56
{
    "manifests": [
        {
            "digest": "sha256:2d5976ded2a3abda6966949c4d545d0cdd88a4d6a15989af38ca5e30e430a619",
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "platform": {
                "architecture": "amd64",
                "os": "linux"
            },
            "size": 596
        },
        {
            "digest": "sha256:e5f5973d201e688987434e3a92d531fa62ec2defa0ff04f51c324b7c82e29dc8",
            "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "platform": {
                "architecture": "arm64",
                "os": "linux"
            },
            "size": 596
...
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

### Check currently allowed Konflux tasks with tags and pullspecs

```bash
CGO_ENABLED=0 go install github.com/open-policy-agent/conftest@latest
conftest pull --policy '.' oci::quay.io/konflux-ci/tekton-catalog/data-acceptable-bundles:latest 
```

### Extract file based catalog from OpenShift index

```bash
podman cp $(podman create --name tc registry.redhat.io/redhat/redhat-operator-index:v4.17):/configs/opentelemetry-product opentelemetry-product-4.17  && podman rm tc
opm migrate opentelemetry-product-4.17 opentelemetry-product-4.17-migrated
opm alpha convert-template basic --output yaml ./opentelemetry-product-4.17-migrated/opentelemetry-product/catalog.json > catalog/catalog-template.yaml
```

### Upgrade existing packages in the base image

We can request an upgraded version of a package in the base image, e.g. in case of a CVE in the base image, where a fixed package is available in the repository, but there is no new base image:

Add the package NVR (name-version-release) to the `rpms.in.yaml` file, for example:

```
packages:
  - libxml2-2.9.7-19.el8_10
  - krb5-libs-1.18.2-31.el8_10
```

and then re-generate `rpms.lock.yaml` with `rpm-lockfile-prototype rpms.in.yaml`.

### Read RPM database from container which does not have `rpm` installed

```bash
podman cp $(podman create --name tc  quay.io/redhat-user-workloads/rhosdt-tenant/otel/opentelemetry-operator:on-pr-100a8f7ef53eed8d72ce929cd4213ebf8c599683-localhost):/var/lib/rpm var-lib-rpm && podman rm tc
rpm -qa --dbpath /home/ploffay/tmp/rpm/var-lib-rpm
```

or read RPMs from SBOM
```bash
cosign download sbom quay.io/redhat-user-workloads/rhosdt-tenant/tempo/tempo-operator@sha256:e724feb8fbe20184ee270d290d31e5f1bf6f70e2d6ad584922f34426277e1f58 --platform linux/amd64 | grep -F 'pkg:rpm' | grep arch=x86_64 | sort | uniq
```