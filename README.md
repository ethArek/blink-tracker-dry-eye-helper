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

### Logs

The app writes structured logs into the output directory using rotating log files:

* `blink_events.log` for per-blink events
* `aggregate_metrics.log` for minute/10-minute/hour/day aggregates

Show all options:

```bash
python main.py --help
```
