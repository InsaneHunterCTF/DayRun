#!/usr/bin/env python3

from __future__ import annotations
import os
import sys
import json
import shlex
import shutil
import subprocess
import time
import signal
from pathlib import Path
from typing import Dict, Any, List, Optional
import platform

import click
import yaml

# Paths (that were mentioned in Readme)
HOME = Path.home()
DAYRUN_DIR = HOME / ".dayrun"
DAYRUN_DIR.mkdir(exist_ok=True)
CONFIG_PATH = DAYRUN_DIR / "config.yml"
SESSIONS_PATH = DAYRUN_DIR / "sessions.json"
PID_PATH = DAYRUN_DIR / "current_session.pid"

# Defaults
DEFAULT_CONFIG = {
    "default_duration": "25m",
    "dnd_on_start": True,
    "templates": {
        "deep-work": {
            "duration": "90m",
            "dnd": True,
            "apps": [],  
            "cmds": [],  
            "tmux": {
                "session_name": "dayrun_deep",
                "panes": []  
            },
            "notifications": True,
            "volume_before": None,
            "music": None
        }
    }
}



def load_config() -> Dict[str, Any]:
    if not CONFIG_PATH.exists():
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(DEFAULT_CONFIG, f)
        return DEFAULT_CONFIG.copy()
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        cfg = {}
    # ensure keys
    cfg.setdefault("default_duration", DEFAULT_CONFIG["default_duration"])
    cfg.setdefault("dnd_on_start", DEFAULT_CONFIG["dnd_on_start"])
    cfg.setdefault("templates", DEFAULT_CONFIG["templates"])
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)


def load_sessions() -> List[Dict[str, Any]]:
    if not SESSIONS_PATH.exists():
        return []
    try:
        return json.loads(SESSIONS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_session_entry(entry: Dict[str, Any]) -> None:
    s = load_sessions()
    s.insert(0, entry)
    try:
        SESSIONS_PATH.write_text(json.dumps(s, indent=2), encoding="utf-8")
    except Exception:
        pass


def parse_duration(s: str) -> int:
    """Return seconds. Accepts '25m', '1h', '90m', '30' (minutes)"""
    s = str(s).strip().lower()
    if s.endswith("h"):
        try:
            return int(float(s[:-1]) * 3600)
        except Exception:
            pass
    if s.endswith("m"):
        try:
            return int(float(s[:-1]) * 60)
        except Exception:
            pass
    # if numbers, treat as minutes
    if s.isdigit():
        return int(s) * 60

    try:
        return int(float(s))
    except Exception:
        raise click.BadParameter(f"Can't parse duration '{s}'")


def human_readable_seconds(sec: int) -> str:
    if sec < 60:
        return f"{sec}s"
    m = sec // 60
    h = m // 60
    m = m % 60
    if h:
        return f"{h}h{m}m"
    return f"{m}m"


def run_subprocess(cmd: str, cwd: Optional[str] = None, background: bool = False) -> Optional[subprocess.Popen]:
    """Run shell command. If background, return Popen."""
    try:
        if background:
            p = subprocess.Popen(cmd, shell=True, cwd=cwd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return p
        else:
            subprocess.run(cmd, shell=True, cwd=cwd)
            return None
    except Exception:
        return None


def which(name: str) -> Optional[str]:
    return shutil.which(name)


def notification(title: str, message: str) -> None:
    """Send desktop notification (best-effort)."""
    system = platform.system()
    try:
        if system == "Darwin":
            # macOS: use AppleScript
            script = f'display notification {shlex.quote(message)} with title {shlex.quote(title)}'
            subprocess.run(["osascript", "-e", script], check=False)
        elif system == "Linux":
            
            if which("notify-send"):
                subprocess.run(["notify-send", title, message], check=False)
            else:
                # last resort: echo to stdout
                print(f"[notify] {title}: {message}")
        else:
            print(f"[notify] {title}: {message}")
    except Exception:
        pass



def enable_dnd_mac(enable: bool) -> bool:
   
    try:
        # Newer macOS versions don't have a simple applescript toggle available across versions.
        # We'll attempt an approach using shell commands that modify the Notification Center preference.
        # NOTE: This is best-effort and may not work on all macOS versions; do not raise.
        # Use `do shell script` to avoid permission dialogues.
        # Fallback: just show a notification instructing the user.
        script = f'display notification "Do Not Disturb {"enabled" if enable else "disabled"} by DayRun (if supported on your macOS)." with title "DayRun"'
        subprocess.run(["osascript", "-e", script], check=False)
        return True
    except Exception:
        return False


def enable_dnd_linux(enable: bool) -> bool:
    """
    Try GNOME / Ubuntu approach using gdbus to toggle Do Not Disturb via Notifications
    Works on recent GNOME with org.freedesktop.Notifications.SetHints (best-effort).
    Alternatively try gsettings for some desktop environments.
    """
    try:
        
        if which("gsettings"):
            val = "false" if enable else "true"
            subprocess.run(["gsettings", "set", "org.gnome.desktop.notifications", "show-banners", val], check=False)
            return True
        # notify-send warning
        if which("notify-send"):
            subprocess.run(["notify-send", "DayRun", f"Do Not Disturb {'enabled' if enable else 'disabled'} (attempt)"], check=False)
            return True
    except Exception:
        pass
    return False


def set_dnd(enable: bool) -> bool:
    """Unified set DND; return True if any attempt was made."""
    system = platform.system()
    if system == "Darwin":
        return enable_dnd_mac(enable)
    elif system == "Linux":
        return enable_dnd_linux(enable)
    else:
        # unsupported
        return False


def open_app_or_url(item: str) -> bool:
    """Open an app name (best-effort) or URL/file path."""
    system = platform.system()
    try:
        if system == "Darwin":
            
            if item.startswith("http://") or item.startswith("https://") or os.path.exists(item):
                subprocess.run(["open", item], check=False)
                return True
            
            try:
                subprocess.run(["open", "-a", item], check=False)
                return True
            except Exception:
                # try as URL
                subprocess.run(["open", item], check=False)
                return True
        elif system == "Linux":
            # xdg-open works for URLs and files
            if item.startswith("http://") or item.startswith("https://") or os.path.exists(item):
                if which("xdg-open"):
                    subprocess.run(["xdg-open", item], check=False)
                    return True
                else:
                    
                    print(f"Open: {item}")
                    return False
            
            if which(item):
                subprocess.Popen([item], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            # gtk-launch (I hope it works)
            if which("gtk-launch"):
                subprocess.run(["gtk-launch", item], check=False)
                return True
            
            if which("xdg-open"):
                subprocess.run(["xdg-open", item], check=False)
                return True
        else:
            return False
    except Exception:
        return False
    return False



def has_tmux() -> bool:
    return which("tmux") is not None


def create_tmux_session(session_name: str, panes: List[Dict[str, str]]) -> bool:
    """
    Create tmux session detached and create panes running specified commands.
    panes: list of {"cwd": "...", "cmd": "..."}
    """
    if not has_tmux():
        return False
    try:
        
        base_name = session_name
        name = base_name
        i = 1
        while subprocess.run(["tmux", "has-session", "-t", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
            name = f"{base_name}_{i}"
            i += 1
        
        if panes:
            first = panes[0]
            cwd = first.get("cwd", None)
            cmd = first.get("cmd", None)
            if cmd:
                subprocess.run(["tmux", "new-session", "-d", "-s", name, "-c", cwd or str(HOME), cmd], check=False)
            else:
                subprocess.run(["tmux", "new-session", "-d", "-s", name, "-c", cwd or str(HOME)], check=False)
           
            for p in panes[1:]:
                cwd = p.get("cwd", None)
                cmd = p.get("cmd", None)
                
                subprocess.run(["tmux", "split-window", "-t", name, "-c", cwd or str(HOME)], check=False)
                if cmd:
                    subprocess.run(["tmux", "send-keys", "-t", name, cmd, "Enter"], check=False)
           
            subprocess.run(["tmux", "select-layout", "-t", name, "tiled"], check=False)
        else:
            # just create session with shell
            subprocess.run(["tmux", "new-session", "-d", "-s", name], check=False)
        return True
    except Exception:
        return False



def write_pid(pid: int) -> None:
    try:
        PID_PATH.write_text(str(pid), encoding="utf-8")
    except Exception:
        pass


def read_pid() -> Optional[int]:
    try:
        if PID_PATH.exists():
            p = int(PID_PATH.read_text(encoding="utf-8").strip())
            return p
    except Exception:
        return None
    return None


def clear_pid() -> None:
    try:
        if PID_PATH.exists():
            PID_PATH.unlink()
    except Exception:
        pass



@click.group()
def cli():
    """DayRun — focused session launcher (terminal-first)."""
    pass


@cli.group()
def templates():
    """Manage session templates (add/list/remove)."""
    pass


@templates.command("list")
def templates_list():
    cfg = load_config()
    temps = cfg.get("templates", {})
    if not temps:
        click.echo("No templates found.")
        return
    click.echo("Templates:")
    for name, data in temps.items():
        d = data.get("duration", cfg.get("default_duration"))
        click.echo(f" - {name}: duration={d}, dnd={data.get('dnd', cfg.get('dnd_on_start'))}, apps={data.get('apps') or '[]'}")


@templates.command("add")
@click.option("--name", prompt=True, help="Template name")
@click.option("--duration", default=None, help="Duration (e.g. 25m, 1h)")
@click.option("--dnd/--no-dnd", default=None, help="Enable DND for template")
@click.option("--apps", default="", help="Comma-separated apps or urls to open")
@click.option("--cmds", default="", help="Comma-separated shell commands to run")
@click.option("--tmux-session", default=None, help="tmux session name (optional)")
def templates_add(name, duration, dnd, apps, cmds, tmux_session):
    cfg = load_config()
    temps = cfg.setdefault("templates", {})
    if name in temps:
        if not click.confirm(f"Template '{name}' exists. Overwrite?"):
            click.echo("Aborted.")
            return
    entry = {}
    if duration:
        entry["duration"] = duration
    if dnd is not None:
        entry["dnd"] = bool(dnd)
    entry["apps"] = [a.strip() for a in apps.split(",") if a.strip()] if apps else []
    entry["cmds"] = [c.strip() for c in cmds.split(",") if c.strip()] if cmds else []
    entry["tmux"] = {"session_name": tmux_session or f"dayrun_{name}", "panes": []}
    temps[name] = entry
    save_config(cfg)
    click.echo(f"Saved template '{name}'.")


@templates.command("remove")
@click.argument("name")
def templates_remove(name):
    cfg = load_config()
    if name in cfg.get("templates", {}):
        del cfg["templates"][name]
        save_config(cfg)
        click.echo(f"Removed template {name}")
    else:
        click.echo("Template not found.")


@cli.command()
@click.option("--template", "-t", default=None, help="Template name to use.")
@click.option("--duration", "-d", default=None, help="Duration (overrides template): e.g. 25m, 1h")
@click.option("--dnd/--no-dnd", default=None, help="Enable/disable Do Not Disturb for this session.")
@click.option("--apps", default="", help="Comma-separated apps or URLs to open.")
@click.option("--cmd", "cmds", multiple=True, help="Shell command to run (repeatable).")
@click.option("--tmux", is_flag=True, default=False, help="Use tmux if available to start panes (requires tmux).")
@click.option("--tmux-session", default=None, help="tmux session name to use (when --tmux).")
@click.option("--notify/--no-notify", default=True, help="Send notifications at start and end.")
@click.option("--detach", is_flag=True, default=False, help="Start session detached (background).")
@click.option("--log/--no-log", default=True, help="Log session to history.")
def start(template, duration, dnd, apps, cmds, tmux, tmux_session, notify, detach, log):
    """
    Start a DayRun session. Use a template or provide ad-hoc options.
    By default this command blocks and shows the countdown. Use --detach to run in background.
    """
    cfg = load_config()
    template_data = {}
    if template:
        template_data = cfg.get("templates", {}).get(template, {})
        if not template_data:
            click.echo(f"Template '{template}' not found.")
            return

    # duration
    dur_str = duration or template_data.get("duration") or cfg.get("default_duration")
    try:
        dur_seconds = parse_duration(dur_str)
    except Exception as e:
        click.echo(f"Invalid duration: {e}")
        return

    # dnd
    if dnd is None:
        dnd_mode = bool(template_data.get("dnd", cfg.get("dnd_on_start", True)))
    else:
        dnd_mode = bool(dnd)

    # openning apps
    apps_list = []
    if template_data.get("apps"):
        apps_list.extend(template_data.get("apps", []))
    if apps:
        apps_list.extend([x.strip() for x in apps.split(",") if x.strip()])

    cmds_list = list(cmds) if cmds else []
    if template_data.get("cmds"):
        cmds_list.extend(template_data.get("cmds", []))

    # tmux panes from template
    tmux_panes = []
    if tmux and template_data.get("tmux"):
        tmux_cfg = template_data.get("tmux", {})
        panes = tmux_cfg.get("panes", [])
        tmux_panes = panes[:]  
        
        session_name = tmux_session or tmux_cfg.get("session_name", f"dayrun_{int(time.time())}")
    else:
        session_name = tmux_session or f"dayrun_{int(time.time())}"

    click.echo(f"Starting DayRun session: duration={human_readable_seconds(dur_seconds)}, dnd={dnd_mode}, detach={detach}")

    # trying to enable DND
    if dnd_mode:
        ok = set_dnd(True)
        if not ok:
            click.echo("Could not enable Do Not Disturb automatically on your system. Please enable it manually if desired.")


    for item in apps_list:
        opened = open_app_or_url(item)
        if not opened:
            click.echo(f"Could not open '{item}' automatically. (Best-effort)")


    background_procs: List[int] = []
    if tmux and tmux_panes:
        created = create_tmux_session(session_name, tmux_panes)
        if created:
            click.echo(f"Created tmux session '{session_name}'. Attach with: tmux attach -t {session_name}")
        else:
            click.echo("tmux requested but failed to create session. Falling back to background commands.")

            for c in cmds_list:
                p = run_subprocess(c, background=True)
                if p:
                    background_procs.append(p.pid)
    else:

        for c in cmds_list:
            p = run_subprocess(c, background=True)
            if p:
                background_procs.append(p.pid)


    music = template_data.get("music")
    if music:

        open_app_or_url(music)

    # start sending notifications
    if notify:
        notification("DayRun", f"Session started: {human_readable_seconds(dur_seconds)}")


    start_ts = int(time.time())
    session_entry = {
        "template": template or None,
        "duration_seconds": dur_seconds,
        "start_ts": start_ts,
        "dnd": dnd_mode,
        "apps": apps_list,
        "cmds": cmds_list,
        "tmux_session": session_name if tmux else None
    }


    if detach:

        python = shutil.which("python3") or shutil.which("python") or sys.executable
        args = [python, str(Path(__file__).absolute()), "_monitor", str(dur_seconds)]

        try:
            env = os.environ.copy()
 
            tmp_entry_file = DAYRUN_DIR / f"pending_session_{start_ts}.json"
            tmp_entry_file.write_text(json.dumps(session_entry), encoding="utf-8")
            args.append(str(tmp_entry_file))

            if platform.system() == "Windows":
                # not supported here
                pass
            else:
                p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
                write_pid(p.pid)
                click.echo(f"Detached monitor started (pid {p.pid}).")
                if log:
                    session_entry["detached_pid"] = p.pid
                    save_session_entry(session_entry)
                return
        except Exception as e:
            click.echo(f"Failed to start detached monitor: {e}")

    try:
        remaining = dur_seconds
        tick = 1
        last_print = -1
        while remaining > 0:

            if remaining > 60:
                interval = 10
            else:
                interval = 1
            rr = remaining
            if rr % interval == 0:
                mins = rr // 60
                secs = rr % 60
                if mins > 0:
                    click.echo(f"Time left: {mins}m {secs}s", err=False)
                else:
                    click.echo(f"Time left: {secs}s", err=False)
            time.sleep(interval)
            remaining -= interval
    except KeyboardInterrupt:
        click.echo("Session interrupted by user.")

        if dnd_mode:
            set_dnd(False)
        return


    if notify:
        notification("DayRun", "Session finished")


    if dnd_mode:
        set_dnd(False)

    # Save session
    session_entry["end_ts"] = int(time.time())
    if log:
        save_session_entry(session_entry)
    click.echo("Session completed.")


@cli.command()
def status():
    """Show status of current detached session (if any)."""
    pid = read_pid()
    if not pid:
        click.echo("No detached session found.")
        return

    try:
        os.kill(pid, 0)
        click.echo(f"Detached session monitor running (pid {pid}).")
    except Exception:
        click.echo("No detached session running (stale PID file).")
        clear_pid()


@cli.command()
def stop():
    """Stop a detached monitor session (if exists)."""
    pid = read_pid()
    if not pid:
        click.echo("No detached session found.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        click.echo(f"Signaled detached session (pid {pid}) to stop.")
        clear_pid()
    except Exception as e:
        click.echo(f"Failed to stop pid {pid}: {e}")
        clear_pid()


@cli.command()
@click.option("--last", default=20, help="Show last N sessions")
def history(last):
    s = load_sessions()
    if not s:
        click.echo("No sessions logged yet.")
        return
    for idx, entry in enumerate(s[:last], 1):
        st = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry.get("start_ts", 0)))
        et = entry.get("end_ts")
        if et:
            et = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(et))
        else:
            et = "-"
        dur = entry.get("duration_seconds")
        click.echo(f"[{idx}] {st} -> {et}  duration={human_readable_seconds(dur or 0)} template={entry.get('template')}")


@cli.command(hidden=True)
@click.argument("seconds", type=int)
@click.argument("entry_file", type=click.Path())
def _monitor(seconds, entry_file):
    """
    Internal: monitors a detached session. It receives a small JSON file with session entry data.
    This process sleeps for `seconds` then performs finishing actions (notifications, DND off, logging).
    """
    # read entry
    try:
        with open(entry_file, "r", encoding="utf-8") as f:
            entry = json.load(f)
    except Exception:
        entry = {}

    pid = os.getpid()
    write_pid(pid)
    try:
        time.sleep(seconds)
        # notify end
        notification("DayRun", "Detached session finished")
        if entry.get("dnd"):
            set_dnd(False)
        entry["end_ts"] = int(time.time())
        save_session_entry(entry)
    finally:
        try:

            Path(entry_file).unlink(missing_ok=True)
        except Exception:
            pass
        clear_pid()


if __name__ == "__main__":
    cli()