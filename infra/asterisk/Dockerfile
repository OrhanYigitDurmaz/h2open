# Asterisk for h2open: landlines (via the AudioCodes MP-114) and the drivers'
# WebRTC phones, controlled by the backend over ARI.
#
# Build and run with docker compose from the repo root:
#   docker compose up -d --build asterisk
# A stable Alpine release (Asterisk 22 LTS), pinned by digest so a rebuild
# gets exactly this base image. Edge is a rolling development branch. To
# update: docker buildx imagetools inspect alpine:3.24, then change both.
FROM alpine:3.24@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf

# Only what we use:
#   asterisk        the PBX, with PJSIP, ARI, the WebSocket transport and G.711
#   asterisk-srtp   encrypted media (DTLS-SRTP), which WebRTC requires
#   asterisk-opus   the codec WebRTC phones prefer on mobile networks
RUN apk add --no-cache asterisk asterisk-srtp asterisk-opus

COPY --chown=asterisk:asterisk config/ /etc/asterisk/
COPY --chmod=755 entrypoint.sh /usr/local/bin/entrypoint.sh

# 5060/udp SIP (MP-114), 8088/tcp HTTP for ARI, 10000-10099/udp RTP media.
EXPOSE 5060/udp 8088/tcp 10000-10099/udp

HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD asterisk -rx "core show uptime" | grep -q "System uptime"

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
