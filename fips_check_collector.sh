#!/usr/bin/env bash

set -ex

# This scrip does not guarantee if the compiled binary if FIPS compliant
# 1. go mod vendor
# 2. x/crypto: grep -r -n -i --include="*.go" golang.org/x/crypto .
# 3. check for imports of x/crypto and investigate if it is used in the product by: go mod why github.com/go-jose/go-jose/v4
# 4. objdump can be used to check if a function importing x/crypto is actually included in the binary

# https://github.com/go-jose/go-jose
# Check for golang.org/x/crypto/pbkdf2
# PBKDF2 is used only by JWE
# https://github.com/go-jose/go-jose/blob/fdc2ceb0bbe2a29c582edfe07ea914c8dacd7e1b/symmetric.go#L333
pattern="decryptKey"
if [[ $(go tool objdump -s "$pattern" _build/opentelemetry-collector) ]]; then
    echo "found $pattern"
    exit 1
fi
# https://github.com/go-jose/go-jose/blob/fdc2ceb0bbe2a29c582edfe07ea914c8dacd7e1b/symmetric.go#L435
pattern="encryptKey"
if [[ $(go tool objdump -s "$pattern" _build/opentelemetry-collector) ]]; then
    echo "found $pattern"
    exit 1
fi

# Verify the FIPS 140 module version embedded in the binary
go version -m _build/opentelemetry-collector | grep "GOFIPS140=v1.0.0"