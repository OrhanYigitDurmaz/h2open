# secrets/

Real credentials live here and are ignored by git (only this README is tracked).

- `pjsip_secrets.conf` — Asterisk PJSIP auth secrets (see `infra/asterisk/pjsip_secrets.conf.example`)
- `wg_private.key` — WireGuard private key (`wg genkey > secrets/wg_private.key`)
- `firebase-service-account.json` — Firebase service account key for push
  messages (Firebase console > Project settings > Service accounts >
  Generate new private key); `chmod 600` it. Set `FCM_CREDENTIALS_FILE`
  in `.env`.
