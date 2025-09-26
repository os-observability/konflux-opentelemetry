# Instructions 

* create a CLI tool in Golang
* the tool talks a Kubernetes cluster
* create the tool in the konflux-tool directory

## Requirements

* add to help that ./bundle-patch/bundle.env should have comment  konflux component: for every component

### check-bundle command

* The tool reads kubernetes `component` custom resources from the cluster listed in the ./bundle-patch/bundle.env file and checks if the pullspecs are latests ones. If they are not, it prints what needs to be updated.
* The latest pullspec is in the `component` `status.lastPromotedImage` fields.
* Print as well `status.lastBuiltCommit` field in the output
* If the pullspecs are outdated exit with 1

### check-release command

* command reads `snapshot` objects from Kubernetes ordered by the most recent one and checks if all images from ./bundle-patch/bundle.env are in the `snapshot` in `spec.components[].containerImage` fields.
* If such snapshot does not exist, print an error message and exit with a non-zero code and suggest triggering a build with `kubectl annotate components/otel-bundle-main build.appstudio.openshift.io/request=trigger-pac-build`
* If the snapshot exists get the `release` object from kubernetes that references the snapshot in `spec.snapshot` field and print the snapshot and release names.
* print the `status.conditions` with `type: Released` and print the `condition.message` and `condition.reason` od that condition.
* print the bundle pullsec from the snapshot
* print in the oputput that the state of the ./bundle-patch/bundle.env components in the snapshot and was or was not released
