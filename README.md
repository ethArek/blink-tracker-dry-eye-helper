# Blink Tracker

Blink Tracker is a webcam-based blink monitor that uses MediaPipe FaceMesh
to estimate eye aspect ratio (EAR) and track blink frequency over time. It provides a
live preview with session stats, writes structured logs, stores data in SQLite, and can
export aggregates for analysis.

## Requirements

- Python 3.10+ (uses modern type annotations).
- A working webcam and permission to access it.
- A graphical desktop session (Qt opens a live preview window).

Python packages (see `requirements.txt`):

```bash
pip install -r requirements.txt
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Usage

Run with defaults (same as the original behavior):

```bash
python main.py
```

Specify camera index, thresholds, output directory, or FPS:

```bash
python main.py --camera-index 1 --ear-threshold 0.22 --ear-consec-frames 3 --output-dir logs --fps 30
```

Enable optional CSV exports for downstream analysis:

```bash
python main.py --output-dir logs --csv-output
```

Enable alerts (off by default) and customize the reminder timing:

```bash
python main.py --enable-alerts --alert-after-seconds 25 --alert-repeat-seconds 25
```

Show all options:

```bash
python main.py --help
```

Show version:

```bash
python main.py --version
```

## What you will see

- A live camera preview with a tabbed stats panel on the right (Stats + Per-minute).
- Session blink count, "last blink" time, per-minute/hour aggregates, and today's total.
- An Alerts card with a toggle and live "After" control for reminder timing.
- A Per-minute table showing the most recent minute aggregates (latest first).

Press **ESC** or close the window to exit (Ctrl+C also works in the terminal).

## Configuration and tuning

- **`--ear-threshold`**: Lower values make blinks harder to trigger; higher values
  make blinks more sensitive. Valid range is `(0.0, 1.0]`. If blinks are missed,
  raise it slightly.
- **`--ear-consec-frames`**: Increase to avoid false positives, decrease for quicker
  detection if you blink rapidly. Must be a positive integer.
- **`--enable-alerts`**: Turn on audio alerts (default: off). You can also toggle
  alerts live in the app.
- **`--disable-alerts`**: Force alerts off (mutually exclusive with `--enable-alerts`).
- **`--alert-after-seconds`**: Time without a blink before an alert plays.
  You can also adjust this live in the app under the Alerts card ("After").
- **`--alert-repeat-seconds`**: How often to repeat alerts while no blinks are detected.
- **`--alert-sound`**: Choose the alert sound (default: `exclamation`).
  Options include `exclamation`, `asterisk`, `hand`, `question`, `beep`,
  `glass`, `ping`, `pop`, `basso`, `tink`, `submarine`, or `none` to mute.
- **`--alert-sound-file`**: Play a custom sound file instead of a built-in sound.
- **`--fps`**: Requests a capture frame rate from the camera. Leave unset to use the
  camera default.
- **`--camera-index`**: If you have multiple cameras, use indices 0, 1, 2, etc. to
  find the correct device.

### Advanced (optional)

- **`BLINK_APP_INIT_HEIGHT` / `BLINK_APP_INIT_WIDTH`**: Override the placeholder
  frame size shown while the camera warms up (defaults: 480x640).

## Outputs

All outputs are written under `--output-dir` (default: current directory).

### Logs

The app writes structured logs into the output directory using rotating log files:

- `app.log` for startup/runtime diagnostics.
- `blink_events.log` for per-blink events.
- `aggregate_metrics.log` for minute/10-minute/hour/day aggregates.

### SQLite storage

Blink events and aggregates are stored in a lightweight SQLite database. By default,
the database file is created at `<output-dir>/blinks.db`. You can override the path
with `--db-path`:

```bash
python main.py --output-dir logs --db-path logs/blinks.db
```

Tables created:

- `blink_events` with `event_time` timestamps for each detected blink.
- `blink_aggregates` with `interval_type`, `interval_start`, `interval_end`, and `blink_count`.

### Optional CSV aggregates

Enable `--csv-output` to emit rolling aggregates to CSV files:

- `blinks_per_minute.csv`
- `blinks_per_10_minutes.csv`
- `blinks_per_hour.csv`
- `blinks_per_day.csv`

### Exporting data (CSV/JSON)

Use the export utility to dump the database tables in CSV or JSON format:

```bash
python export_blinks.py --output-dir logs --format csv --table both
python export_blinks.py --output-dir logs --format json --table aggregates
```

## Alerts

Alerts are off by default. Enable them with `--enable-alerts` or toggle the switch
in the Alerts card. If no blink is detected for 30 seconds (default), the app plays
a reminder sound and repeats every 30 seconds until a blink is detected. You can
tune the timing with `--alert-after-seconds` and `--alert-repeat-seconds`, and
change the sound with `--alert-sound` or `--alert-sound-file`. Set
`--alert-sound none` to mute alerts while keeping them enabled. You can also adjust
the "After" value live from the Alerts card in the app window. On systems without
audio playback tools, it falls back to a terminal bell.

## Release installers

Platform-specific release scripts live in `scripts/release`. They use PyInstaller
to build the executable and then package platform installers (EXE, DMG, AppImage).

```bash
# Windows (PowerShell)
.\scripts\release\build_windows.ps1

# macOS
./scripts/release/build_macos.sh

# Linux (AppImage)
./scripts/release/build_linux_appimage.sh
```

The installers are staged under `dist/release`. For more details and dependencies,
see `scripts/release/README.md`.

## Development checks

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

Run tests and coverage locally:

```bash
python -m unittest discover -s tests -v
coverage run -m unittest discover -s tests
coverage report
```

CI (`.github/workflows/ci.yml`) runs tests, bytecode compilation, and coverage
threshold checks on every push/PR.

## Troubleshooting

- **Camera will not open**: Try a different `--camera-index`, close other apps using
  the camera, or ensure the OS has granted camera permissions.
- **Black window or no frames**: Some cameras need a few seconds to warm up. If it
  persists, try reducing `--fps` or switching cameras.
- **Missed or false blinks**: Adjust `--ear-threshold` and `--ear-consec-frames` until
  the stats panel matches your actual blink rate.
- **No audio alerts**: Make sure alerts are enabled (`--enable-alerts` or the UI
  toggle), then install a system audio player (e.g., `paplay`/`aplay` on Linux, or
  ensure audio output is enabled).
