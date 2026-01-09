# Dry Eye Blink Detector

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

### SQLite storage

Blink events and aggregates are stored in a lightweight SQLite database. By default,
the database file is created at `<output-dir>/blinks.db`. You can override the path
with `--db-path`:

```bash
python main.py --output-dir logs --db-path logs/blinks.db
```

Tables created:

* `blink_events` with `event_time` timestamps for each detected blink
* `blink_aggregates` with `interval_type`, `interval_start`, `interval_end`, and `blink_count`

### Exporting data (CSV/JSON)

Use the export utility to dump the database tables in CSV or JSON format:

```bash
python export_blinks.py --output-dir logs --format csv --table both
python export_blinks.py --output-dir logs --format json --table aggregates
```

### Logs

The app writes structured logs into the output directory using rotating log files:

* `blink_events.log` for per-blink events
* `aggregate_metrics.log` for minute/10-minute/hour/day aggregates

Show all options:

```bash
python main.py --help
```
