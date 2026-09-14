# Classy AWS deployment

Production API: https://api.classystudy.com

The AWS environment starts with a new database and empty media storage. Existing
Render users, purchases, chat messages, and uploads were not imported.

## Resources

- Region: `ap-northeast-2` (Seoul)
- EC2: `i-0be45a8fcec97bfa0`, `t3.medium`, 2 vCPU / 4 GiB RAM
- Elastic IP: `15.165.25.7`; existing DNS and TLS certificate retained
- Root disk: 30 GiB gp3
- RDS: `classy-test-db`, PostgreSQL 18.3, `db.t4g.micro`, private and encrypted
- Application database: `classy_production`; dedicated application login
- RDS storage: 20 GiB, autoscaling maximum 100 GiB; deletion protection enabled
- S3: `classy-prod-media-482178843291-apne2`, private, encrypted, TLS-only
- Redis: localhost only, 256 MiB maximum, used for channels and cache
- Account budget: `Classy monthly 300 USD`, monthly USD 300, dashboard tracking

EC2 uses standard CPU credits to avoid unlimited CPU credit charges. The budget
tracks expenditure; it does not stop charges and has no email subscribers.
Existing RDS one-day automated backup retention was retained. No migration
backup or snapshot was created.

## Runtime

Code: `/home/ubuntu/classy-aws`

Environment: `/home/ubuntu/classy-aws/.env` (mode 0600; never commit or print).
The environment uses `DJANGO_SETTINGS_MODULE=config.settings.aws`.
S3 access uses the EC2 instance role, not stored AWS access keys. RDS connections
verify the AWS CA certificate. Uvicorn runs two workers under `classy.service`.
Nginx terminates HTTPS and proxies WebSockets. Access logs omit query strings.

Use `ssh classy-aws` with the existing local SSH configuration. Common checks:

```sh
systemctl is-active classy nginx redis-server
curl -fsS https://api.classystudy.com/healthz/
cd /home/ubuntu/classy-aws
export DJANGO_SETTINGS_MODULE=config.settings.aws
/home/ubuntu/classy_aws_venv/bin/python manage.py check --deploy --fail-level WARNING
/home/ubuntu/classy_aws_venv/bin/python manage.py migrate --check
```

Initial administrator username is `superuser_classy`; its email and password were
copied from the existing Render bootstrap settings. Administrator API login uses
the email, whereas Django `/admin/` uses the username. Only the initial admin and
subject/region catalogs remain after synthetic deployment tests.

## Future updates

Upload reviewed source to `/home/ubuntu/classy-aws`, excluding `.env`, `.git`,
virtual environments, local databases, secrets, media, and static build output.
Do not run `prepare-host.sh` for every update; it is host provisioning only.

```sh
cd /home/ubuntu/classy-aws
export DJANGO_SETTINGS_MODULE=config.settings.aws
/home/ubuntu/classy_aws_venv/bin/pip install -r requirements.txt
/home/ubuntu/classy_aws_venv/bin/python manage.py check --deploy --fail-level WARNING
/home/ubuntu/classy_aws_venv/bin/python manage.py migrate --noinput
/home/ubuntu/classy_aws_venv/bin/python manage.py seed_reference_data
/home/ubuntu/classy_aws_venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart classy
curl -fsS https://api.classystudy.com/healthz/
```

`nginx.conf` is installed through `/etc/nginx/sites-enabled/classy`, pointing to
`/etc/nginx/sites-available/classy-aws`. Run `sudo nginx -t` before reload.
The previous code directory remains on disk, but restoring it alone does not
roll back DB migrations. No rollback to the old blank/broken DB configuration is
recommended.

## Client and store configuration still required

- Flutter builds must use `--dart-define=API_BASE_URL=https://api.classystudy.com`
  and disable any demo backend/auth flags. The Flutter source and installed app
  were not modified by this backend deployment.
- Existing Render admin/site deployments were not repointed or redeployed.
- Apple App Store Server Notifications V2 endpoint:
  `https://api.classystudy.com/cash/webhook/apple/`.
- Use `APPLE_IAP_ENVIRONMENT=PRODUCTION` for the AWS production service. Ordinary
  accounts accept only production transactions. A dedicated Apple review account
  can be provisioned server-side with `User.iap_environment='SANDBOX'`; the field
  is not exposed for user editing. Such an account accepts only verified Apple
  sandbox purchases, records no real payment proceeds, and cannot make Google
  purchases. Its rentals retain an immutable sandbox flag and are excluded from
  instructor revenue, settlement requests, and monthly revenue ranks. Do not
  change the environment of accounts with existing purchases or balances.
- The notification endpoint verifies both Apple environments and matches the
  signed transaction environment to the stored purchase before applying refunds.
  An invalid signature never triggers an environment fallback. Both production
  and sandbox App Store notification URLs should point to the AWS endpoint.
- Google Pub/Sub authenticated push endpoint and audience must both be
  `https://api.classystudy.com/cash/webhook/google/`. The AWS backend's audience
  setting is already prepared for this value. The external subscription has not
  been changed.
- Google service-account token authentication and Firebase credential loading
  passed. Actual SMS, device push delivery, and real store purchases require
  end-user/device checks and were not sent during deployment.

## Verification

235 automated tests passed locally with isolated test caches and a fast test-only
password hasher; production password hashing was not changed. Live verification
passed 23 checks covering HTTPS, RDS/Redis, admin/user login, static assets, CORS,
S3 uploads and unsigned access denial, H.264 conversion and duration, byte-range
video playback, authenticated notifications, Redis broadcasts, and two-client
chat. Synthetic users, files, and chat records were removed afterward.

This is a single-instance / single-AZ starting configuration, without automatic
horizontal scaling or high-availability failover.
