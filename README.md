🚀 Among Us Ranked Discord Bot

### Overview

A Discord bot for managing ranked Among Us games on an Impostor server, including automute, queues, and a comprehensive leaderboard.

### Prerequisites

- Linux host with systemd
- Python 3.10+
- Git
- Access to your Discord server (manage roles, channels, and emojis)

### 1) Create a dedicated system user

Create a non-login user named `discordbot` to run the service and own files:

```bash
sudo adduser --system --group --home /home/discordbot discordbot
sudo mkdir -p /home/discordbot/discordBot
sudo chown -R discordbot:discordbot /home/discordbot/discordBot
```

### 2) Clone and create a virtual environment

```bash
cd /home/discordbot/discordBot
sudo -u discordbot git clone https://github.com/alecto98/AmongUsRankedDiscordBot.git .
sudo -u discordbot python3 -m venv .venv
sudo -u discordbot .venv/bin/pip install -U pip
sudo -u discordbot .venv/bin/pip install -r requirements.txt
```

### 3) Configure the bot

- Copy the example config and fill in real values locally (the real config is ignored by git):

```bash
sudo -u discordbot cp config/config.example.yaml config/config.yaml
```

- Edit `config/config.yaml` and set your Discord bot token, guild/channel/role IDs, paths, and VIP role settings.
- Edit `config/emojis.yaml` to match your server’s emoji names.
- Add all emojis from the `zip for emojis.zip` file to your Discord server so names match what the bot expects.

### 4) Build a single executable (optional)

If you prefer running a single binary, build with PyInstaller:

```bash
sudo -u discordbot .venv/bin/pyinstaller --onefile discord_bot.py
```

This will create `dist/discord_bot`. The bot writes logs and needs write access where your Impostor server is installed, so ensure file permissions allow `discordbot` to write to those paths configured in `config/config.yaml`.

### 5) Run under systemd

Create a systemd unit to keep the bot running and auto-restart:

```ini
[Unit]
Description=Among Us Ranked Discord Bot

[Service]
WorkingDirectory=/home/discordbot/discordBot
ExecStart=/home/discordbot/discordBot/dist/discord_bot
Restart=always
RestartSec=5

User=discordbot
Group=discordbot

# Make all created files group-writable
UMask=0007

TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
```

Install and start the service:

```bash
sudo tee /etc/systemd/system/discord-bot.service >/dev/null <<'UNIT'
[Unit]
Description=Among Us Ranked Discord Bot

[Service]
WorkingDirectory=/home/discordbot/discordBot
ExecStart=/home/discordbot/discordBot/dist/discord_bot
Restart=always
RestartSec=5
User=discordbot
Group=discordbot
UMask=0007
TimeoutStopSec=10

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now discord-bot
sudo systemctl status discord-bot --no-pager
```

### Development notes

- Keep your real token only in `config/config.yaml`. That file is `.gitignore`d and not pushed to GitHub.
- If you develop without PyInstaller, you can run the bot directly:

```bash
sudo -u discordbot .venv/bin/python discord_bot.py
```

### Contributions

Contributions are welcome. Open issues and PRs with improvements or bug fixes.
