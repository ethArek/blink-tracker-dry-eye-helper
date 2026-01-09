import cv2
import mediapipe as mp
import math
import time
from datetime import datetime, timedelta

# EAR – Eye Aspect Ratio
def eye_aspect_ratio(landmarks, eye_indices):
    def euclidean(p1, p2):
        return math.dist(p1, p2)
    
    p = [landmarks[i] for i in eye_indices]
    A = euclidean(p[1], p[5])
    B = euclidean(p[2], p[4])
    C = euclidean(p[0], p[3])
    ear = (A + B) / (2.0 * C)
    return ear

# Punkty oczu (MediaPipe)
LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]

# Progi i liczniki
EAR_THRESHOLD = 0.21
EAR_CONSEC_FRAMES = 3

frame_counter = 0
blink_counter = 0
blink_timestamps = []       # jako datetime
blink_timestamps_day = []   # jako float

# Pomocnicza funkcja liczenia
def count_blinks_in_range(blinks, start: datetime, end: datetime) -> int:
    return sum(1 for t in blinks if start <= t <= end)

# Inicjalizacja MediaPipe
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=False, max_num_faces=1, refine_landmarks=True)

# Inicjalizacja kamery
cap = cv2.VideoCapture(0)
if not cap.isOpened():
    print("❌ Nie można otworzyć kamery.")
    exit()

print("🎥 Kamera uruchomiona. Naciśnij ESC lub Ctrl+C, aby zakończyć.")

# Czyszczenie plików na start
open("blinks_per_minute.txt", "w").close()
open("blinks_per_10_minutes.txt", "w").close()
open("blinks_per_hour.txt", "w").close()
open("blinks_per_day.txt", "a").close()

last_stats_time = time.time()

try:
    while True:
        ret, frame = cap.read()
        if not ret:
            print("❌ Nie udało się pobrać obrazu.")
            break

        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)
        now_dt = datetime.now()
        now_ts = time.time()

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
                        print(f"👁️ Mrugnięcie #{blink_counter}")
                    frame_counter = 0

        # Co sekundę przelicz statystyki i zapisz
        if time.time() - last_stats_time >= 1.0:
            last_stats_time = time.time()

            # Filtracja ostatnich 60 minut
            blink_timestamps = [t for t in blink_timestamps if (now_dt - t).total_seconds() <= 3600]
            blink_timestamps_day = [t for t in blink_timestamps_day if datetime.fromtimestamp(t).date() == now_dt.date()]

            # Wyznaczenie zakresów czasu
            # Pełna ostatnia minuta
            end_1m = now_dt.replace(second=0, microsecond=0) - timedelta(seconds=1)
            start_1m = end_1m.replace(second=0)

            # Pełne ostatnie 10 minut
            end_10m = now_dt.replace(minute=(now_dt.minute // 10) * 10, second=0, microsecond=0) - timedelta(seconds=1)
            start_10m = end_10m - timedelta(minutes=10) + timedelta(seconds=1)

            # Pełna ostatnia godzina
            end_1h = now_dt.replace(minute=0, second=0, microsecond=0) - timedelta(seconds=1)
            start_1h = end_1h.replace(minute=0)

            # Zlicz mrugnięcia z zakresów
            blinks_1m = count_blinks_in_range(blink_timestamps, start_1m, end_1m)
            blinks_10m = count_blinks_in_range(blink_timestamps, start_10m, end_10m)
            blinks_1h = count_blinks_in_range(blink_timestamps, start_1h, end_1h)
            blinks_day = len(blink_timestamps_day)

            # Zapis do plików
            timestamp_str = now_dt.strftime("%H:%M:%S")
            with open("blinks_per_minute.txt", "a") as f:
                f.write(f"{timestamp_str} - {blinks_1m}\n")
            with open("blinks_per_10_minutes.txt", "a") as f:
                f.write(f"{timestamp_str} - {blinks_10m}\n")
            with open("blinks_per_hour.txt", "a") as f:
                f.write(f"{timestamp_str} - {blinks_1h}\n")

            # Zapis do pliku dziennego
            date_str = now_dt.strftime("%Y-%m-%d")
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

        # Wyświetl dane na kamerze
        cv2.putText(frame, f"👁️ Mrugnięcia (pełne okresy):", (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        cv2.putText(frame, f"  min:  {blinks_1m}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"  10min: {blinks_10m}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.putText(frame, f"  godz: {blinks_1h}", (10, 120),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        cv2.imshow("Mruganie", frame)
        if cv2.waitKey(1) & 0xFF == 27:  # ESC
            break

except KeyboardInterrupt:
    print("\n🛑 Zatrzymano przez Ctrl+C")

finally:
    cap.release()
    cv2.destroyAllWindows()
    print("✅ Kamera i okna zamknięte. Do zobaczenia!")