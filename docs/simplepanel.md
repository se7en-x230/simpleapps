# Simplepanel

Show a desktop status panel or open the system dashboard. The panel includes desktop and media information; workspace/title integration currently targets Mango. Start the panel explicitly with simplepanel-session.

### Panel bar

![Simplepanel bar in demo mode](screenshots/simplepanel-bar.png)

### System dashboard

![Simplepanel system dashboard with Lisbon clock](screenshots/simplepanel.png)

Screenshot captured in an isolated profile; no personal accounts are connected.

## Install and start

From the repository root on an Arch-based system:

```sh
./install --install simplepanel
simplepanel --system-dashboard
```

Or extract the individual `simplepanel-installer-YYYYMMDD.tar.gz` release archive and run `./install` inside it. Run as your normal user. Add `$HOME/.local/bin` to PATH if your desktop has not already done so.

**Compatibility:** Panel: Wayland layer-shell; workspace/title integration: Mango. Dashboard: normal GTK window..

Application menu opens the system dashboard. Start simplepanel-session explicitly for the panel; no existing panel is replaced.

## Remove

```sh
./install --uninstall simplepanel
```

An individual installer also provides `./uninstall`. Uninstallation preserves personal settings/data, changed files, system packages and shared files still needed by other apps.

## Code

[Source directory](../simplepanel/) · [Dependency and option catalog](../simpleinstaller/components.json) · [All apps](../README.md)

Runtime packages: `gtk4`, `json-c`, `python`, `gtk4-layer-shell`, `libpulse`, `fastfetch`.

Screenshot uses demo hostname and network labels in a temporary preview build. The distributed source reads real system information.

## Clock and market configuration

Edit `~/.config/simplepanel/config.ini` (or `$XDG_CONFIG_HOME/simplepanel/config.ini`). Example:

```ini
[panel]
clock=true
clock_timezone=Europe/London
clock_format=%a %d  %H:%M %Z
invest=true
calendar_command=simple-calendar

[dashboard]
clocks=true
clock_labels=London;Tokyo;
clock_zones=Europe/London;Asia/Tokyo;
clock_format=%H:%M\n%a %d %b · %Z
markets=true

[markets]
ids=bitcoin;ethereum;
labels=BTC;ETH;
currency=usd
decimals=2
```

Merge these keys into existing sections; keep the other panel settings. Clock and market lists accept 1–4 entries; each label list must match its corresponding zone/ID list. An empty panel time zone uses the system time zone. `clock=false` hides the panel clock; `invest=false` hides panel quotes. Dashboard visibility is independent.

Markets share their choices between panel and dashboard. Use [CoinGecko coin IDs and supported quote currencies](https://docs.coingecko.com/reference/simple-price), not arbitrary stock or commodity tickers. `tether-gold` represents XAUT; it is not a spot-XAU feed. Quotes refresh at most hourly per process after a successful request, retry failures after five minutes, and keep the last successful cache. The cache is separate for each asset/currency selection, so old THB values cannot be relabelled as USD. Provider errors or unavailable quotes show as unavailable, or retain cached values with a timestamp in the dashboard tooltip. `curl` is required; no separate investment script is needed. The legacy `SIMPLEPANEL_INVEST_COMMAND` environment override still takes precedence for panel text only.

Check and apply:

```sh
simplepanel --check
simplepanel-session restart
```

Close and reopen the dashboard after edits. `--config /path/to/config.ini` also works with `--system-dashboard` and `--check`. To show the optional calendar report when clicking the panel clock, set `calendar_command=simple-calendar --show-90-day-report`. This command is parsed into arguments without invoking a shell.
