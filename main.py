import cv2
import logging
import os
import sys
import time
from datetime import datetime

import mediapipe as mp

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

    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=False,
        max_num_faces=1,
        refine_landmarks=True,
    )

    cap = cv2.VideoCapture(args.camera_index)
    if not cap.isOpened():
        app_logger.error("Cannot open camera.")
        sys.exit(1)
    if args.fps is not None:
        cap.set(cv2.CAP_PROP_FPS, args.fps)

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

            render_overlay(frame, aggregate_state)

            cv2.imshow("Blink detection", frame)
            if cv2.waitKey(1) & 0xFF == 27:
                break

    except KeyboardInterrupt:
        app_logger.info("Stopped by Ctrl+C")

    finally:
        db_conn.close()
        cap.release()
        cv2.destroyAllWindows()
        app_logger.info("Camera and windows closed. Goodbye!")


if __name__ == "__main__":
    main()
