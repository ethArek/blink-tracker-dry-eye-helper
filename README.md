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

Show all options:

```bash
python main.py --help
```
