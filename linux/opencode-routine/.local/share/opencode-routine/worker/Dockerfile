# Build only through an approved administration step, never from a launch request.
# BASE_IMAGE must be an approved Debian-family image pinned by registry digest.
ARG BASE_IMAGE
FROM ${BASE_IMAGE}
ARG OPENCODE_SHA256
ARG BUNDLE_SHA256
RUN apt-get update && apt-get install -y --no-install-recommends python3 git zsh ca-certificates libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --create-home --shell /bin/zsh worker \
    && mkdir -p /control /inputs /opt/routine/empty-template /opt/routine/config/opencode
# The administration build context supplies a separately verified V2.0.22 binary.
COPY opencode /usr/local/bin/opencode
RUN test -n "$OPENCODE_SHA256" \
    && echo "$OPENCODE_SHA256  /usr/local/bin/opencode" | sha256sum --check --strict \
    && chmod 0555 /usr/local/bin/opencode \
    && test "$(opencode --version)" = "opencode v2.0.22"
COPY Dockerfile worker.py opencode.json proxy.py /opt/routine/bundle/
RUN cp /opt/routine/bundle/opencode.json /control/opencode.json \
    && cp /opt/routine/bundle/opencode.json /opt/routine/config/opencode/opencode.json \
    && printf '[core]\n\thooksPath = /dev/null\n\tfsmonitor = false\n[gc]\n\tauto = 0\n' > /opt/routine/gitconfig \
    && chmod -R a-w /control /opt/routine
LABEL routine.bundle-sha256=$BUNDLE_SHA256 routine.opencode-version="2.0.22"
USER 10001:10001
WORKDIR /control
ENTRYPOINT ["python3", "-B", "/opt/routine/bundle/worker.py"]
