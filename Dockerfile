# syntax=docker/dockerfile:1.7

ARG XMRIG_VERSION=6.26.0

FROM ubuntu:24.04 AS builder
ARG XMRIG_VERSION

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git build-essential cmake \
       libuv1-dev libssl-dev libhwloc-dev libmicrohttpd-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /src

RUN git clone --depth 1 --branch "v${XMRIG_VERSION}" https://github.com/xmrig/xmrig.git xmrig \
    && cmake -S xmrig -B xmrig/build -DCMAKE_BUILD_TYPE=Release -DWITH_HWLOC=ON -DWITH_HTTPD=ON -DWITH_TLS=ON -DWITH_OPENCL=OFF -DWITH_CUDA=OFF \
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
