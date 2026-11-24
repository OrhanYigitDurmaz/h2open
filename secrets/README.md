# secrets/

Real credentials live here and are ignored by git (only this README is tracked).

- `pjsip_secrets.conf` — Asterisk PJSIP auth secrets (see `infra/asterisk/pjsip_secrets.conf.example`)
- `wg_private.key` — WireGuard private key (`wg genkey > secrets/wg_private.key`)
