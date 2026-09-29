#!/usr/bin/env bash
set -euo pipefail
# Run on classy-aws ONLY after classystudy.com and www.classystudy.com resolve
# to 15.165.25.7 and port 80's ACME challenge is reachable there.
python3 - <<'PY'
import socket
for name in ('classystudy.com', 'www.classystudy.com'):
    addresses={row[4][0] for row in socket.getaddrinfo(name, 80, type=socket.SOCK_STREAM)}
    if addresses != {'15.165.25.7'}:
        raise SystemExit(f'DNS not ready: {name} -> {sorted(addresses)}')
print('Both DNS records point to the Classy EC2.')
PY
sudo certbot certonly --webroot -w /var/www/classy-web/acme \
    --cert-name classystudy.com -d classystudy.com -d www.classystudy.com \
    --non-interactive --agree-tos
sudo cp /etc/nginx/sites-available/classy-web /var/www/classy-web/nginx-before-https.conf
sudo install -m 644 /var/www/classy-web/deploy/nginx-production.conf /etc/nginx/sites-available/classy-web
if ! sudo nginx -t; then
    sudo cp /var/www/classy-web/nginx-before-https.conf /etc/nginx/sites-available/classy-web
    exit 1
fi
sudo systemctl reload nginx
curl -fsS --resolve classystudy.com:443:127.0.0.1 https://classystudy.com/api/healthz/
curl -fsS https://api.classystudy.com/healthz/
