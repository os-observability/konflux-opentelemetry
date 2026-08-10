FROM registry.access.redhat.com/ubi9/ubi-minimal:latest

RUN microdnf install -y python3 python3-pip skopeo rpm tar gzip && \
    microdnf clean all

RUN pip3 install --no-cache-dir pyyaml requests

COPY rpm_cve_check.py /usr/local/bin/rpm_cve_check.py

ENTRYPOINT ["python3", "/usr/local/bin/rpm_cve_check.py"]
