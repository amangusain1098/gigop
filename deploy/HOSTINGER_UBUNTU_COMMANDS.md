```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release ufw git

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo adduser deploy
sudo usermod -aG sudo deploy
sudo usermod -aG docker deploy

sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

sudo mkdir -p /opt/gigoptimizer-pro
sudo chown -R deploy:deploy /opt/gigoptimizer-pro

sudo -iu deploy
cd /opt
git clone https://github.com/YOUR_GITHUB_USERNAME/YOUR_REPOSITORY.git gigoptimizer-pro
cd /opt/gigoptimizer-pro
cp .env.production.example .env.production
nano .env.production
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml build
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml up -d postgres redis app worker scheduler nginx certbot
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml run --rm certbot certonly --webroot -w /var/www/certbot -d animha.co.in --email you@example.com --agree-tos --no-eff-email
docker compose --env-file .env.production -f deploy/docker-compose.prod.yml restart nginx
```
