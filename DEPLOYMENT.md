# Google Maps Lead Scraper - Ubuntu / GoDaddy Deployment

## Project

The application is a Streamlit + Playwright Google Maps scraper.

It does NOT use SQLite or another persistent database.

Results are held in the Streamlit session and can be downloaded as:

- CSV
- Excel (.xlsx)

Exported columns:

1. Business Name
2. Category
3. Phone
4. Address
5. Website

## Recommended server layout

/opt/google-maps-lead-scraper/

    dashboard.py
    requirements.txt
    venv/

Nginx receives public HTTP/HTTPS traffic and proxies it to Streamlit on:

127.0.0.1:8501

## Important

Use a dedicated non-root Linux user named `mapscraper`.

The Playwright browser is installed for that same user.

The dashboard uses:

headless=True

because an Ubuntu server normally does not have a graphical desktop.

## DNS

In GoDaddy DNS, create an A record:

Type: A
Name: @
Value: YOUR_SERVER_PUBLIC_IP
TTL: 600 or Automatic

If using a subdomain:

Type: A
Name: scraper
Value: YOUR_SERVER_PUBLIC_IP
TTL: 600 or Automatic

Then use:

scraper.YOUR_DOMAIN

## Ubuntu installation

sudo apt update
sudo apt upgrade -y

sudo apt install -y python3 python3-venv python3-pip nginx curl ufw

Create application user:

sudo adduser --system --group --home /opt/google-maps-lead-scraper mapscraper

Create directory:

sudo mkdir -p /opt/google-maps-lead-scraper
sudo chown -R mapscraper:mapscraper /opt/google-maps-lead-scraper

Copy dashboard.py and requirements.txt into that directory.

Create virtual environment:

sudo -u mapscraper python3 -m venv /opt/google-maps-lead-scraper/venv

Install packages:

sudo -u mapscraper /opt/google-maps-lead-scraper/venv/bin/pip install --upgrade pip
sudo -u mapscraper /opt/google-maps-lead-scraper/venv/bin/pip install -r /opt/google-maps-lead-scraper/requirements.txt

Install Playwright Chromium:

sudo -u mapscraper /opt/google-maps-lead-scraper/venv/bin/python -m playwright install chromium

Install Playwright Linux dependencies:

sudo /opt/google-maps-lead-scraper/venv/bin/python -m playwright install-deps chromium

## Test application

sudo -u mapscraper /opt/google-maps-lead-scraper/venv/bin/streamlit run /opt/google-maps-lead-scraper/dashboard.py --server.address=127.0.0.1 --server.port=8501

Test locally on server:

curl http://127.0.0.1:8501

Stop the test with Ctrl+C.

## systemd

Copy google-maps-lead-scraper.service to:

/etc/systemd/system/google-maps-lead-scraper.service

Then:

sudo systemctl daemon-reload
sudo systemctl enable google-maps-lead-scraper
sudo systemctl start google-maps-lead-scraper

Check:

sudo systemctl status google-maps-lead-scraper

Logs:

sudo journalctl -u google-maps-lead-scraper -f

Restart:

sudo systemctl restart google-maps-lead-scraper

## Nginx

Copy nginx.conf to:

/etc/nginx/sites-available/google-maps-lead-scraper

Edit YOUR_DOMAIN:

sudo nano /etc/nginx/sites-available/google-maps-lead-scraper

Enable:

sudo ln -s /etc/nginx/sites-available/google-maps-lead-scraper /etc/nginx/sites-enabled/google-maps-lead-scraper

Test:

sudo nginx -t

Reload:

sudo systemctl reload nginx

## Firewall

Allow SSH:

sudo ufw allow OpenSSH

Allow HTTP:

sudo ufw allow 80/tcp

Allow HTTPS:

sudo ufw allow 443/tcp

Enable:

sudo ufw enable

Check:

sudo ufw status

Do NOT expose port 8501 publicly. Nginx should be the public entry point.

## SSL / HTTPS

Install Certbot:

sudo apt install -y certbot python3-certbot-nginx

After DNS has propagated and HTTP works:

sudo certbot --nginx -d YOUR_DOMAIN

If also using www:

sudo certbot --nginx -d YOUR_DOMAIN -d www.YOUR_DOMAIN

Certbot will configure HTTPS and can install the HTTP-to-HTTPS redirect.

Test renewal:

sudo certbot renew --dry-run

## Troubleshooting

Check application:

sudo systemctl status google-maps-lead-scraper

Check application logs:

sudo journalctl -u google-maps-lead-scraper -n 200 --no-pager

Follow live logs:

sudo journalctl -u google-maps-lead-scraper -f

Check Nginx:

sudo nginx -t

Check Nginx logs:

sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

Check port 8501:

sudo ss -lntp | grep 8501

Check Playwright:

sudo -u mapscraper /opt/google-maps-lead-scraper/venv/bin/python -c "from playwright.sync_api import sync_playwright; print('Playwright OK')"

## Updating the application

Copy the new dashboard.py:

sudo cp dashboard.py /opt/google-maps-lead-scraper/dashboard.py

Fix ownership:

sudo chown mapscraper:mapscraper /opt/google-maps-lead-scraper/dashboard.py

Restart:

sudo systemctl restart google-maps-lead-scraper

## No Docker

Docker is not required.

The deployment uses:

GoDaddy DNS
    ->
Ubuntu VPS
    ->
Nginx
    ->
Streamlit
    ->
Playwright / Chromium
    ->
Google Maps

## Important Google Maps consideration

The scraper removes the application's fixed scroll limit and continues until new listings stop appearing.

However, Google Maps controls the result set and may:

- stop returning additional listings
- change its HTML/UI
- require consent
- display verification/challenge pages
- limit automated traffic

Therefore "unlimited" means no artificial application scroll cap, not a guarantee that Google will return every business listing.
