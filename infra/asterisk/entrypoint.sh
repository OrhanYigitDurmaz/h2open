#!/bin/sh
# Write the ARI login from the environment, then run Asterisk in the
# foreground. Asterisk starts as root only to read its config and drops to
# the asterisk user (-U/-G) before loading any module.
set -eu

: "${ARI_USERNAME:?set ARI_USERNAME in .env}"
: "${ARI_PASSWORD:?set ARI_PASSWORD in .env}"

umask 077
cat > /etc/asterisk/ari_users.conf <<CONF
; Written at startup from ARI_USERNAME / ARI_PASSWORD. Do not edit.
[${ARI_USERNAME}]
type = user
read_only = no
password = ${ARI_PASSWORD}
CONF
chown asterisk:asterisk /etc/asterisk/ari_users.conf

exec asterisk -f -U asterisk -G asterisk "$@"
