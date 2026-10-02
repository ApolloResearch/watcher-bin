FROM python:3.12-bookworm@sha256:771f3160ed1c1115f0ed16cc9992b52418a4b12aee65269a1a040767c554d541
ADD agent-cli-package.tar.gz /opt/cursor/
COPY run_diagnostic.py capture_hook.py /diag/
ENTRYPOINT ["python3", "/diag/run_diagnostic.py"]
