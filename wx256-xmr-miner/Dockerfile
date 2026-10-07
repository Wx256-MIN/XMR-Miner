# syntax=docker/dockerfile:1.7

ARG XMRIG_VERSION=6.26.0

FROM ubuntu:24.04 AS builder
ARG XMRIG_VERSION

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git build-essential cmake python3 \
       libuv1-dev libssl-dev libhwloc-dev libmicrohttpd-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN git clone --depth 1 --branch "v${XMRIG_VERSION}" https://github.com/xmrig/xmrig.git xmrig

# XMRig normally tries to write the MSR allow_writes sysfs parameter during
# startup. Umbrel's container sysfs is read-only, even when the host has
# already enabled MSR writes. Treat an existing "on" value as sufficient.
RUN python3 - <<'PY'
from pathlib import Path

path = Path("/src/xmrig/src/hw/msr/Msr_linux.cpp")
text = path.read_text()

old = '''#include <sys/types.h>
#include <unistd.h>


namespace xmrig {
'''

new = '''#include <sys/types.h>
#include <unistd.h>
#include <string>


namespace xmrig {
'''

if old not in text:
    raise SystemExit("XMRig include marker not found")

text = text.replace(old, new, 1)

old = '''    inline bool msr_allow_writes()
    {
        std::ofstream file("/sys/module/msr/parameters/allow_writes", std::ios::out | std::ios::binary | std::ios::trunc);
        if (file.is_open()) {
            file << "on";
        }

        return file.good();
    }
'''

new = '''    inline bool msr_allow_writes()
    {
        // In containers the sysfs parameter can be read-only even when the
        // host already enabled MSR writes. Accept an existing enabled value.
        std::ifstream check("/sys/module/msr/parameters/allow_writes");
        if (check.is_open()) {
            std::string value;
            check >> value;
            if (value == "on" || value == "1" || value == "Y" || value == "y") {
                return true;
            }
        }

        std::ofstream file("/sys/module/msr/parameters/allow_writes", std::ios::out | std::ios::binary | std::ios::trunc);
        if (file.is_open()) {
            file << "on";
        }

        return file.good();
    }
'''

if old not in text:
    raise SystemExit("XMRig msr_allow_writes marker not found")

path.write_text(text.replace(old, new, 1))
PY

RUN cmake -S xmrig -B xmrig/build -DCMAKE_BUILD_TYPE=Release -DWITH_HWLOC=ON -DWITH_HTTPD=ON -DWITH_TLS=ON -DWITH_OPENCL=OFF -DWITH_CUDA=OFF \
    && cmake --build xmrig/build --config Release --parallel "$(nproc)" \
    && test -x xmrig/build/xmrig

FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl python3 libuv1t64 libhwloc15 libmicrohttpd12 libssl3t64 libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home --home-dir /data xmrig

COPY --from=builder /src/xmrig/build/xmrig /opt/xmrig
COPY entrypoint.sh /entrypoint.sh
COPY dashboard.py /dashboard.py
COPY dashboard /dashboard

RUN chmod 0755 /entrypoint.sh /dashboard.py \
    && mkdir -p /data \
    && chown -R 10001:10001 /data

WORKDIR /data
EXPOSE 80 8080
ENTRYPOINT ["/entrypoint.sh"]
