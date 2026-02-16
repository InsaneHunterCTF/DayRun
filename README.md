# DayRun

DayRun is a CLI-tool that enables the user to take focused sessions doing tasks without any disturbances. This makes the user does their tasks faster and better by using some of dayrun's features like Do-Not-Disturb, open apps/URLs, run commands or tmux panes, notifications, session logging.


### Features

- Start a focused session in one command:

-  enable Do-Not-Disturb (DND) when possible
-  open apps or URLs
-  run background shell commands or create a tmux session with panes
-  play music/white noise (open a URL/file)
-  desktop notifications at start/end (best-effort)

- Detach mode: start a session monitor in background (--detach)
- Session logging to ~/.dayrun/sessions.json
- Templates: save and reuse common session presets
- Cross-platform best-effort support for Linux (desktop) and macOS
- Safe fallbacks if system capabilities (tmux, notify-send, osascript) are missing

## Installation: (Linux & macOS)

``
git clone https://github.com/InsaneHunterCTF/DayRun.git
``

``
cd dayrun
``

``
python3 -m venv venv
``

``
source venv/bin/activate
``

``
pip install --upgrade pip
``

``
pip install click pyyaml
``

Recommended:

for Linux:

``
sudo apt update
``

``
sudo apt install -y libnotify-bin tmux
``

for macOS:

``
brew install tmux
``

## Usage

``
python3 dayrun.py --help
``

# Important Links:

Config / templates: ~/.dayrun/config.yml

Session log: ~/.dayrun/sessions.json

Detached monitor PID file: ~/.dayrun/current_session.pid
