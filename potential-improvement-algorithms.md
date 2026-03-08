# Potential Issues

## [P1] No-face periods are treated as no-blink periods

- File: `blink_app/domain/aggregates.py:67`
- Summary: Alerting and aggregate updates are driven only from `blink_state.last_blink_time`.
- Risk: If tracking drops or the user steps away, the app can log zero-blink intervals and fire "no blink" alerts even though there is no subject to observe.
- Notes: `BlinkState` is only updated when a face is present in the frame loop, so this needs recent-face or tracking state and a pause path for alerts and aggregates when no face is available.

## [P1] Camera startup timeout is not actually enforceable

- File: `blink_app/runtime/camera.py:40`
- Summary: `_wait_for_first_frame` checks the timeout around `local_cap.read()`, but OpenCV backends can block inside `read()`.
- Risk: `--camera-startup-timeout-seconds` is not a real hard bound, so startup and shutdown can hang well past the configured timeout.
- Notes: This needs a probe strategy that can be abandoned independently of a stuck `read()` call.

## [P2] FaceMesh runs on the GUI thread

- File: `blink_app/ui/window.py:560`
- Summary: Capture, RGB conversion, FaceMesh inference, and final frame presentation all run in the Qt event loop thread.
- Risk: On slower CPUs or when MediaPipe spikes, the window can stutter or become unresponsive, and the intended 30 ms cadence becomes inaccurate.
- Notes: Moving frame processing off the GUI thread would reduce both UI freezes and sampling jitter.

## [P2] Output fallback is gated on the literal `.`

- File: `blink_app/app.py:27`
- Summary: Automatic fallback to a user-writable output directory only happens when `args.output_dir == "."`.
- Risk: Equivalent paths like an absolute current-working-directory path, `".\\"`, or any other unwritable user-supplied directory hard-fail even though `resolve_runtime_output_dir()` already implements fallback behavior.
- Notes: This is surprising and does not match the README wording about automatic fallback.

## Future Blink Detector Options

### Candidate Algorithms

1. Multi-gap eyelid aperture plus phase state machine
- Replace classic 6-point EAR as the main signal with several upper/lower eyelid gaps per eye, normalized by eye width.
- Detect blink phases explicitly: `open -> closing -> closed -> reopening -> open`.
- Pros: Fast, practical, fits the current app well.
- Cons: Still heuristic and still limited by landmark quality.

2. Valley detector on the aperture curve
- Treat a blink as a local minimum between two open plateaus instead of a single threshold crossing.
- Pros: Better for shallow but real blinks.
- Cons: Needs a short sliding window and careful timing logic.

3. Velocity-based detector
- Use closing and reopening speed in addition to depth.
- Pros: Rejects slow pose drift and many false positives.
- Cons: Sensitive to noisy landmarks without good smoothing.

4. Rolling-percentile open baseline
- Estimate open-eye baseline from the recent 90th or 95th percentile of high-quality samples.
- Pros: More stable than simple EMA against slow drift.
- Cons: Needs good sample filtering.

5. Quality-gated detector
- Pause blink counting when the eye region is too small, head pose is too angled, landmarks are unstable, or left/right quality disagrees.
- Pros: Large false-positive reduction.
- Cons: Detection will intentionally pause more often.

6. Personal calibration mode
- Collect a short open-eye baseline and optionally a few intentional blinks at startup.
- Pros: Strong low-cost accuracy improvement.
- Cons: Adds UX complexity.

7. Hidden Markov Model or probabilistic state model
- Model `open`, `closing`, `closed`, and `opening` as explicit latent states.
- Pros: Better temporal behavior than raw thresholds.
- Cons: More engineering and tuning work.

8. Tiny sequence classifier
- Feed a short feature sequence into a small model to classify blink versus non-blink.
- Pros: Highest ceiling for accuracy.
- Cons: Requires labeled data and a proper evaluation set.

9. Optical-flow hybrid
- Combine landmarks with local eyelid motion inside the eye ROI.
- Pros: Helps when landmarks wobble.
- Cons: Higher CPU cost and more edge cases.

### Recommended Next Algorithm

- Main feature: `aperture_eye = median(vertical_lid_gaps) / eye_width`
- Baseline: Rolling high-percentile of recent good open samples
- Signals: Left ratio, right ratio, average ratio, closing speed, reopening speed, symmetry gap
- Candidate start: Ratio falling quickly and crossing a soft close threshold
- Candidate minimum: Validated local valley with enough depth
- Confirm blink: Duration roughly 60-250 ms, strong reopen, good symmetry, acceptable tracking quality
- Reject: Slow drift, one-eye wink, long closure, missing face, low-quality landmarks

### Recommended Implementation Order

1. Better feature extraction
- Move from classic EAR to multi-gap eyelid aperture.

2. New hybrid detector
- Combine rolling baseline, normalized aperture ratio, velocity, valley validation, and duration/symmetry checks.

3. Quality gating
- Explicitly pause detection on poor eye geometry, unstable landmarks, bad pose, or too-small eye boxes.

4. Optional calibration
- Add a startup calibration path for per-user thresholds and baselines.

5. Debug overlay
- Show detector state, per-eye ratio, quality, and blink confidence on the camera preview for tuning.

6. Replay and evaluation harness
- Build a recorded-session evaluation path so detector changes are measured rather than guessed.
