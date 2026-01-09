import cv2
import mediapipe as mp
import math
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta

# EAR - Eye Aspect Ratio
def eye_aspect_ratio(landmarks, eye_indices):
    def euclidean(p1, p2):
        return math.dist(p1, p2)
    
    p = [landmarks[i] for i in eye_indices]
    A = euclidean(p[1], p[5])
    B = euclidean(p[2], p[4])
    C = euclidean(p[0], p[3])
    ear = (A + B) / (2.0 * C)
    return ear

# Eye landmark indices (MediaPipe)
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# Thresholds
EAR_THRESHOLD = 0.21
EAR_CONSEC_FRAMES = 3
ALERT_NO_BLINK_SECONDS = 30
ALERT_REPEAT_SECONDS = 30

frame_counter = 0
blink_counter = 0
blink_timestamps = []       # datetime
blink_timestamps_day = []   # float (timestamp)

# Play a sound alert when no blink is detected for a while
def play_alert_sound():
    """
    Play an alert sound asynchronously using a best-effort, platform-specific backend.

    The sound is played in a separate daemon thread so that calls to this function
    are non-blocking and do not interrupt the main video-processing loop.

    Platform behavior:
      * Windows: use ``winsound.Beep`` if available.
      * macOS (Darwin): use ``afplay`` to play the system ``Glass.aiff`` sound if
        the command and sound file are present.
      * Linux/other Unix-like systems:
          - Prefer ``paplay`` (PulseAudio) with common freedesktop sound files, if
            both the command and at least one sound file exist.
          - Otherwise, try ``aplay`` (ALSA) with a common system sound file.

    If no platform-specific method succeeds, the function falls back to writing the
    ASCII bell character (``\\a``) to standard output to trigger a terminal beep
    when supported.
    """
    def _play():
        if platform.system() == "Windows":
            try:
                import winsound
                winsound.Beep(1000, 500)
                return
            except Exception:
                pass

        if platform.system() == "Darwin":
            mac_sound = "/System/Library/Sounds/Glass.aiff"
            if shutil.which("afplay") and os.path.exists(mac_sound):
                subprocess.Popen(
                    ["afplay", mac_sound],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

        if shutil.which("paplay"):
            for sound_path in (
                "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
                "/usr/share/sounds/freedesktop/stereo/complete.oga",
            ):
                if os.path.exists(sound_path):
                    subprocess.Popen(
                        ["paplay", sound_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return

        if shutil.which("aplay"):
            for sound_path in ("/usr/share/sounds/alsa/Front_Center.wav",):
                if os.path.exists(sound_path):
                    subprocess.Popen(
                        ["aplay", sound_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    return

        sys.stdout.write("\a")
        sys.stdout.flush()

    threading.Thread(target=_play, daemon=True).start()

# Count blinks in a given time range
def count_blinks_in_range(blinks, start: datetime, end: datetime) -> int:
    return sum(1 for t in blinks if start <= t <= end)

# Init mediapipe
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=True)

# Init camera
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("Cannot open camera.")
    exit()

print("Camera started. Press ESC or Ctrl+C to exit.")

# Time trackers
last_stats_time = time.time()
last_logged_minute = None
last_logged_10minute = None
last_logged_hour = None
# NOTE: These time-tracking variables are written from the main thread only.
# Background threads may read them, and we currently rely on CPython's GIL and
# simple float assignments being effectively atomic. If more complex, compound
# operations are added in the future, protect access with a threading.Lock or
# another explicit synchronization mechanism.
last_blink_time = time.time()
last_alert_time = 0.0

# Values to show on screen
blinks_1m = 0
blinks_10m = 0
blinks_1h = 0



try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("Failed to read frame.")
            break

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)
        now_dt = datetime.now()
        now_ts = time.time()

        date_str = now_dt.strftime("%Y-%m-%d")


        if results.multi_face_landmarks:
            for face_landmarks in results.multi_face_landmarks:
                landmarks = [(lm.x * w, lm.y * h) for lm in face_landmarks.landmark]

                left_ear = eye_aspect_ratio(landmarks, LEFT_EYE)
                right_ear = eye_aspect_ratio(landmarks, RIGHT_EYE)
                ear = (left_ear + right_ear) / 2.0

                if ear < EAR_THRESHOLD:
                    frame_counter += 1
                else:
                    if frame_counter >= EAR_CONSEC_FRAMES:
                        blink_counter += 1
                        blink_timestamps.append(now_dt)
                        blink_timestamps_day.append(now_ts)
                        last_blink_time = now_ts
                        print(f"Blink #{blink_counter}")
                    frame_counter = 0

        # Every second: check if it's time to log full intervals
        if time.time() - last_stats_time >= 1.0:
            last_stats_time = time.time()

            if (
                now_ts - last_blink_time >= ALERT_NO_BLINK_SECONDS
                and now_ts - last_alert_time >= ALERT_REPEAT_SECONDS
            ):
                play_alert_sound()
                last_alert_time = now_ts

            # Filter old data
            blink_timestamps = [t for t in blink_timestamps if (now_dt - t).total_seconds() <= 3600]
            blink_timestamps_day = [t for t in blink_timestamps_day if datetime.fromtimestamp(t).date() == now_dt.date()]

            # FULL MINUTE LOG
            current_minute = now_dt.replace(second=0, microsecond=0) - timedelta(minutes=1)
            if last_logged_minute != current_minute:
                blinks_1m = count_blinks_in_range(blink_timestamps, current_minute, current_minute + timedelta(minutes=1) - timedelta(seconds=1))
                with open("blinks_per_minute.txt", "a") as f:
                    f.write(f"{date_str} {current_minute.strftime('%H:%M:%S')} - {blinks_1m}\n")
                last_logged_minute = current_minute

            # FULL 10-MINUTE LOG
            minute_mod = now_dt.minute % 10
            current_10minute = now_dt.replace(minute=now_dt.minute - minute_mod, second=0, microsecond=0) - timedelta(minutes=10)
            if last_logged_10minute != current_10minute:
                blinks_10m = count_blinks_in_range(blink_timestamps, current_10minute, current_10minute + timedelta(minutes=10) - timedelta(seconds=1))
                with open("blinks_per_10_minutes.txt", "a") as f:
                    f.write(f"{date_str} {current_10minute.strftime('%H:%M:%S')} - {blinks_10m}\n")
                last_logged_10minute = current_10minute

            # FULL HOUR LOG
            current_hour = now_dt.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
            if last_logged_hour != current_hour:
                blinks_1h = count_blinks_in_range(blink_timestamps, current_hour, current_hour + timedelta(hours=1) - timedelta(seconds=1))
                with open("blinks_per_hour.txt", "a") as f:
                    f.write(f"{date_str} {current_hour.strftime('%H:%M:%S')} - {blinks_1h}\n")
                last_logged_hour = current_hour

            # DAILY LOG (still logs every second — acceptable)
            blinks_day = len(blink_timestamps_day)
            day_line = f"{date_str} - {blinks_day}\n"

            try:
                with open("blinks_per_day.txt", "r") as f:
                    lines = f.readlines()
            except FileNotFoundError:
                lines = []

            found = False
            for i, line in enumerate(lines):
                if line.startswith(date_str):
                    lines[i] = day_line
                    found = True
                    break

            if not found:
                lines.append(day_line)

            with open("blinks_per_day.txt", "w") as f:
                f.writelines(lines)

        # Display info on camera frame
        cv2.putText(frame, "Blinks (full intervals):", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"  min:   {blinks_1m}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"  10min: {blinks_10m}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"  hour:  {blinks_1h}", (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow("Blink detection", frame)
        if cv2.waitKey(1) & 0xFF == 27:
            break

except KeyboardInterrupt:
    print("\nStopped by Ctrl+C")

finally:
    cap.release()
    cv2.destroyAllWindows()
    print("Camera and windows closed. Goodbye!")
