#!/bin/bash
# dipeen VPS 초기 설정 스크립트 (Ubuntu 22.04 / Vultr Tokyo)
# 사용법: bash deploy/setup.sh
set -e

DIPEEN_DIR="/opt/dipeen"

echo "=== 1. 시스템 패키지 업데이트 ==="
apt-get update -y && apt-get upgrade -y

echo "=== 2. Docker 설치 ==="
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

echo "=== 3. ufw 방화벽 설정 ==="
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

echo "=== 4. Certbot 설치 ==="
apt-get install -y certbot python3-certbot-nginx

echo "=== 5. 프로젝트 디렉토리 생성 ==="
mkdir -p "$DIPEEN_DIR"

echo ""
echo "=== 설치 완료 ==="
echo ""
echo "다음 단계:"
echo "  1. 코드 배포:  cd $DIPEEN_DIR && git clone <repo-url> ."
echo "  2. 환경변수:   cp .env.example .env && nano .env"
echo "     필수값: ANTHROPIC_API_KEY, DIPEEN_SECRET_KEY, DOMAIN"
echo "  3. SSL 인증서: certbot --nginx -d \$DOMAIN"
echo "  4. nginx 설정: cp deploy/nginx/conf.d/dipeen.conf /etc/nginx/conf.d/"
echo "     sed -i 's/DOMAIN_PLACEHOLDER/'\$DOMAIN'/g' /etc/nginx/conf.d/dipeen.conf"
echo "     nginx -t && systemctl reload nginx"
echo "  5. 서비스 시작: docker compose -f docker-compose.prod.yml up -d"
echo "  6. DB 마이그레이션: docker compose -f docker-compose.prod.yml exec api alembic upgrade head"
