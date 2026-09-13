#!/usr/bin/env bash
set -euo pipefail

# The existing root EBS volume is expanded through the EC2 API first.
if [ "$(lsblk -bn -o SIZE /dev/nvme0n1p1)" -lt 25000000000 ]; then
    sudo growpart /dev/nvme0n1 1
    sudo resize2fs /dev/nvme0n1p1
fi
sudo apt-get update -qq
sudo env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq redis-server ffmpeg python3.12-venv
sudo systemctl enable --now redis-server
python3.12 -m venv /home/ubuntu/classy_aws_venv
/home/ubuntu/classy_aws_venv/bin/pip install --quiet --upgrade pip
/home/ubuntu/classy_aws_venv/bin/pip install --quiet -r /home/ubuntu/classy-aws/requirements.txt
sudo install -d -m 0755 /etc/redis
sudo tee /etc/redis/classy-limits.conf >/dev/null <<'CONFIG'
bind 127.0.0.1 ::1
protected-mode yes
maxmemory 256mb
maxmemory-policy noeviction
save ""
appendonly no
CONFIG
if ! sudo grep -q '^include /etc/redis/classy-limits.conf$' /etc/redis/redis.conf; then
    printf '\ninclude /etc/redis/classy-limits.conf\n' | sudo tee -a /etc/redis/redis.conf >/dev/null
fi
sudo systemctl restart redis-server
redis-cli ping
ffmpeg -version | head -n 1
df -h /
