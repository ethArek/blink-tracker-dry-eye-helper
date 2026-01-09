import cv2
import logging
import os
import sys
import threading
import time
from datetime import datetime

import mediapipe as mp
import numpy as np

from blink_app.aggregates import AggregateState, update_aggregates
from blink_app.cli import parse_args
from blink_app.constants import LEFT_EYE, RIGHT_EYE
from blink_app.db import init_db
from blink_app.detection import BlinkState, eye_aspect_ratio
from blink_app.logging_utils import setup_logging
from blink_app.render import render_overlay


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    try:
        os.makedirs(output_dir, exist_ok=True)
    except OSError as e:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger("app").error(
            "Could not create output directory '%s': %s",
            output_dir,
            e,
        )
        sys.exit(1)

    app_logger, blink_logger, aggregate_logger = setup_logging(output_dir)
    db_path = args.db_path or os.path.join(output_dir, "blinks.db")
    db_conn = init_db(db_path)

    cap: cv2.VideoCapture | None = None
    camera_ready = threading.Event()
    camera_result: dict[str, str | cv2.VideoCapture | None] = {"error": None, "cap": None}

    def open_camera() -> None:
        local_cap = None
        try:
            local_cap = cv2.VideoCapture(args.camera_index)
            if not local_cap.isOpened():
                camera_result["error"] = "Cannot open camera."
                if local_cap is not None:
                    local_cap.release()
                camera_ready.set()
                return
            if args.fps is not None:
                local_cap.set(cv2.CAP_PROP_FPS, args.fps)
            camera_result["cap"] = local_cap
        except Exception as e:
            camera_result["error"] = f"Camera initialization error: {e}"
            if local_cap is not None:
                local_cap.release()
        finally:
            camera_ready.set()

    app_logger.info("Starting blink detection. Initializing camera...")
    window_name = "Blink detection"
    cv2.namedWindow(window_name)
    camera_thread = threading.Thread(target=open_camera, daemon=False)
    camera_thread.start()

    waiting_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    user_exit_during_init = False
    while not camera_ready.is_set():
        frame = waiting_frame.copy()
        cv2.putText(
            frame,
            "Initializing camera...",
            (30, 240),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        cv2.imshow(window_name, frame)
        if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
            app_logger.info("Window closed during camera initialization.")
            user_exit_during_init = True
            break
        if cv2.waitKey(50) & 0xFF == 27:
            app_logger.info("Exit requested during camera initialization.")
            user_exit_during_init = True
            break

    # Wait for the camera thread to complete
    camera_thread.join()

    # If user requested exit during initialization, clean up and exit
    if user_exit_during_init:
        cap = camera_result["cap"]
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        db_conn.close()
        app_logger.info("Exited during initialization. Goodbye!")
        sys.exit(0)

    if camera_result["error"]:
        app_logger.error("%s", camera_result["error"])
        cv2.destroyAllWindows()
        db_conn.close()
        sys.exit(1)

    cap = camera_result["cap"]
    if cap is None:
        app_logger.error("Camera did not initialize.")
        cv2.destroyAllWindows()
        db_conn.close()
        sys.exit(1)

    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,
    )

    app_logger.info("Camera started. Press ESC or Ctrl+C to exit.")

    blink_state = BlinkState(last_blink_time=time.time())
    aggregate_state = AggregateState(last_stats_time=time.time())

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                app_logger.warning("Failed to read frame.")
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

                    blink_state.update(
                        ear,
                        now_dt,
                        now_ts,
                        args.ear_threshold,
                        args.ear_consec_frames,
                        blink_logger,
                        db_conn,
                    )

            update_aggregates(
                args,
                aggregate_state,
                now_dt,
                now_ts,
                blink_state,
                db_conn,
                aggregate_logger,
                output_dir,
            )

            rendered = render_overlay(frame, aggregate_state, blink_state, now_ts)

            cv2.imshow(window_name, rendered)
            if cv2.getWindowProperty(window_name, cv2.WND_PROP_VISIBLE) < 1:
                app_logger.info("Window closed by user.")
                break
            if cv2.waitKey(1) & 0xFF == 27:
                break

    except KeyboardInterrupt:
        app_logger.info("Stopped by Ctrl+C")

    finally:
        db_conn.close()
        if cap is not None:
            cap.release()
        cv2.destroyAllWindows()
        app_logger.info("Camera and windows closed. Goodbye!")


if __name__ == "__main__":
    main()
