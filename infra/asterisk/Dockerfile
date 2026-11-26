# Asterisk for h2open: landlines (via the AudioCodes MP-114) and the drivers'
# WebRTC phones, controlled by the backend over ARI.
#
# Build and run with docker compose from the repo root:
#   docker compose up -d --build asterisk
#
# Alpine only packages Asterisk 22, so Asterisk is built from source here,
# with only the modules listed in config/modules.conf. The base image is a
# stable Alpine release pinned by digest, and both downloads are pinned by
# SHA-256, so a rebuild gets exactly the same inputs. To update:
#   base image  docker buildx imagetools inspect alpine:3.24, change both FROMs
#   Asterisk    ASTERISK_VERSION, and ASTERISK_SHA256 from asterisk-X.sha256
#               next to the tarball on downloads.asterisk.org
ARG ALPINE=alpine:3.24@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf

FROM ${ALPINE} AS build

ARG ASTERISK_VERSION=24.0.0
ARG ASTERISK_SHA256=ece42a75bc965180007c56b03f2fd1dc8484eb84fc4cddc090db0ee5d5da1af9
# codec_opus_open_source: the free Opus transcoder, which Asterisk itself
# only ships as a closed binary. Same commit Alpine's package uses.
ARG OPUS_COMMIT=a959f072d3f364be983dd27e6e250b038aaef747
ARG OPUS_SHA256=52404693d102a577e27f6df03cb8d7c2425973372aceb193d8aff13453ec6076

RUN apk add --no-cache \
        bash build-base bsd-compat-headers curl linux-headers pax-utils patch \
        jansson-dev libedit-dev libsrtp-dev libxml2-dev openssl-dev opus-dev \
        pjproject-dev sqlite-dev util-linux-dev zlib-dev

WORKDIR /src
RUN curl -fsSLo asterisk.tar.gz \
        "https://downloads.asterisk.org/pub/telephony/asterisk/releases/asterisk-${ASTERISK_VERSION}.tar.gz" \
    && echo "${ASTERISK_SHA256}  asterisk.tar.gz" | sha256sum -c - \
    && curl -fsSLo opus.tar.gz \
        "https://github.com/traud/asterisk-opus/archive/${OPUS_COMMIT}.tar.gz" \
    && echo "${OPUS_SHA256}  opus.tar.gz" | sha256sum -c - \
    && mkdir asterisk opus \
    && tar -xzf asterisk.tar.gz -C asterisk --strip-components=1 \
    && tar -xzf opus.tar.gz -C opus --strip-components=1 \
    && cp opus/codecs/* asterisk/codecs/

# Alpine's fixes for building and running on musl (from aports).
COPY patches/ /src/patches/
WORKDIR /src/asterisk
RUN for p in /src/patches/*.patch; do patch -p1 < "$p"; done \
    # libasteriskssl finds libssl's symbols with dlsym, so keep it linked.
    && sed -i 's/ASTSSL_LIBS:=$(OPENSSL_LIB)/ASTSSL_LIBS:=-Wl,--no-as-needed $(OPENSSL_LIB) -Wl,--as-needed/' main/Makefile

# Alpine's pjproject instead of the bundled one, which configure would
# download unpinned.
RUN ./configure \
        --prefix=/usr --sysconfdir=/etc --localstatedir=/var --libdir=/usr/lib \
        --disable-xmldoc --enable-permanent-dlopen \
        --without-pjproject-bundled --with-jansson-bundled=no \
        --with-libedit --with-srtp --with-opus --with-sqlite3 \
        --without-dahdi --without-pri --without-tonezone --without-x11 \
        CFLAGS="-O2"

# Build exactly the modules modules.conf loads, and nothing else: no sound
# downloads, no sample config, no CPU-specific code (BUILD_NATIVE). Turning
# everything off also turns off OPTIONAL_API, without which modules that call
# into optional ones (res_pjsip -> res_statsd) don't load on musl.
COPY config/modules.conf /tmp/modules.conf
RUN make menuselect.makeopts \
    && ./menuselect/menuselect --disable-all \
        --enable OPTIONAL_API --enable ENABLE_SRTP_AES_256 menuselect.makeopts \
    && sed -n 's/^load *= *\(.*\)\.so *$/\1/p' /tmp/modules.conf \
        | xargs -I{} ./menuselect/menuselect --enable {} menuselect.makeopts \
    && make -j"$(nproc)" \
    && make install DESTDIR=/out \
    # /var/run is a symlink to /run on Alpine, so COPY can't write into it.
    && mv /out/var/run /out/run \
    && scanelf --recursive --nobanner --etype ET_DYN,ET_EXEC --format '%F' /out \
        | xargs strip --strip-unneeded \
    # The shared libraries the runtime image needs, as apk "so:" names.
    && scanelf --recursive --nobanner --needed --format '%n#p' /out \
        | tr ',' '\n' | grep -v -e '^$' -e '^libasterisk' | sort -u | sed 's/^/so:/' \
        > /out/runtime-deps \
    # Every module modules.conf loads must have been built.
    && sed -n 's/^load *= *\(.*\)\.so *$/\1/p' /tmp/modules.conf | while read -r m; do \
        [ -f "/out/usr/lib/asterisk/modules/$m.so" ] || { echo "not built: $m" >&2; exit 1; }; \
    done


FROM ${ALPINE}

COPY --from=build /out/ /
RUN apk add --no-cache $(cat /runtime-deps) && rm /runtime-deps \
    && addgroup -S asterisk \
    && adduser -S -D -H -G asterisk -h /var/lib/asterisk -s /sbin/nologin asterisk \
    && mkdir -p /var/lib/asterisk /var/spool/asterisk /var/log/asterisk /run/asterisk \
    && chown -R asterisk:asterisk /var/lib/asterisk /var/spool/asterisk \
        /var/log/asterisk /run/asterisk

COPY --chown=asterisk:asterisk config/ /etc/asterisk/
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh

# 5060/udp SIP (MP-114), 8088/tcp HTTP for ARI, 10000-10099/udp RTP media.
EXPOSE 5060/udp 8088/tcp 10000-10099/udp

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD asterisk -rx "core show uptime" | grep -q "System uptime"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
