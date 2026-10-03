FROM ubuntu:24.04

ARG XMRIG_VERSION=6.25.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl libuv1t64 libhwloc15 libmicrohttpd12 \
    && rm -rf /var/lib/apt/lists/*

RUN arch="$(dpkg --print-architecture)" \
    && case "$arch" in \
         amd64) asset="xmrig-${XMRIG_VERSION}-linux-static-x64.tar.gz" ;; \
         arm64) asset="xmrig-${XMRIG_VERSION}-linux-static-arm64.tar.gz" ;; \
         *) echo "Unsupported architecture: $arch" >&2; exit 1 ;; \
       esac \
    && curl -fsSL "https://github.com/xmrig/xmrig/releases/download/v${XMRIG_VERSION}/${asset}" -o /tmp/xmrig.tar.gz \
    && mkdir -p /opt/xmrig \
    && tar -xzf /tmp/xmrig.tar.gz --strip-components=1 -C /opt/xmrig \
    && test -x /opt/xmrig/xmrig \
    && rm -f /tmp/xmrig.tar.gz

COPY entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh

WORKDIR /data
EXPOSE 8080
ENTRYPOINT ["/entrypoint.sh"]
