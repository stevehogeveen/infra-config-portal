# GNU xorriso builds the unattended ESXi installer ISO (esxi_installer_artifact requires 1.5.8.pl02+;
# Debian ships 1.5.6). Official GNU release, pinned by SHA-256 (GNU signature checked by Thomas Schmitt
# key E9CBDFC0ABC0A854 when the pin was recorded). Only the finished binary is copied below.
FROM python:3.12-slim AS xorriso
RUN apt-get update && apt-get install -y --no-install-recommends gcc make libc6-dev && rm -rf /var/lib/apt/lists/*
ADD --checksum=sha256:b1455ecafbf0692ddafe1d71002a96f2ce2d77f4deae602678261ce033f97bc8 https://ftp.gnu.org/gnu/xorriso/xorriso-1.5.8.pl02.tar.gz /tmp/xorriso.tar.gz
RUN mkdir /tmp/xorriso && tar xzf /tmp/xorriso.tar.gz -C /tmp/xorriso --strip-components=1 \
    && cd /tmp/xorriso \
    && ./configure --prefix=/usr/local --disable-libreadline --disable-libedit --disable-libacl \
       --disable-xattr --disable-zlib --disable-libbz2 --disable-libjte --disable-libcdio \
    && make -j"$(nproc)" && make install \
    && /usr/local/bin/xorriso -version | head -1

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Inspect signed vendor RPM contents only; never install or execute their payloads.
RUN apt-get update && apt-get install -y --no-install-recommends rpm libarchive-tools && rm -rf /var/lib/apt/lists/*

COPY --from=xorriso /usr/local/bin/xorriso /usr/local/bin/xorriso

# VMware govc signs in to ESXi after install (verification, VM datastore) and is used by the
# Windows deploy step. Official v0.56.0 release, pinned to the SHA-256 in its published checksums.txt.
ADD --checksum=sha256:beabfa250fb91f1a9687586448a24c24fd4f95324fa905d157241d0c9efcfeb0 https://github.com/vmware/govmomi/releases/download/v0.56.0/govc_Linux_x86_64.tar.gz /tmp/govc.tar.gz
RUN tar xzf /tmp/govc.tar.gz -C /usr/local/bin govc && rm /tmp/govc.tar.gz && govc version

COPY app/backend/requirements.txt /tmp/lab-builder-requirements.txt
RUN pip install --no-cache-dir -r /tmp/lab-builder-requirements.txt

COPY . /workspace
RUN mkdir -p /workspace/.local /workspace/artifacts/codex-runs

WORKDIR /workspace/app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
