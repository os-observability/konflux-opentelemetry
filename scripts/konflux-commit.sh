#!/usr/bin/env bash
set -eu

if [ $# -lt 1 ]
  then
    echo "usage: $0 [commits...]"
    exit 1
fi

for commit in "$@"
do
  echo "SNAPSHOTS of $commit"
  kubectl get snapshot -l pac.test.appstudio.openshift.io/sha=$commit

  echo
  echo "RELEASES of $commit"
  kubectl get release  -l pac.test.appstudio.openshift.io/sha=$commit

  echo && echo
done
