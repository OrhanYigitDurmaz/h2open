#!/bin/sh
# Write logins and addresses from the environment, then run Asterisk in the
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

# The MP-114's address and the desk phones' logins, from the environment.
# A desk phone without a password is left out, so nothing is open.
{
    echo "; Written at startup from MP114_ADDRESS and DESK*_PASSWORD. Do not edit."
    echo "[mp114]"
    echo "type = aor"
    if [ -n "${MP114_ADDRESS:-}" ]; then
        echo "contact = sip:${MP114_ADDRESS}:5060"
        echo
        echo "[mp114-identify]"
        echo "type = identify"
        echo "endpoint = mp114"
        echo "match = ${MP114_ADDRESS}"
    fi
    for desk in desk1 desk2; do
        password=$(printenv "$(echo "$desk" | tr a-z A-Z)_PASSWORD" || true)
        [ -n "$password" ] || continue
        echo
        echo "[$desk](desk)"
        echo "auth = $desk"
        echo "aors = $desk"
        echo
        echo "[$desk](desk-aor)"
        echo
        echo "[$desk]"
        echo "type = auth"
        echo "auth_type = userpass"
        echo "username = $desk"
        echo "password = $password"
    done
} > /etc/asterisk/pjsip_local.conf
chown asterisk:asterisk /etc/asterisk/pjsip_local.conf

exec asterisk -f -U asterisk -G asterisk "$@"
