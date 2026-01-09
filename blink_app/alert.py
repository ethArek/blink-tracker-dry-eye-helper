import os
import platform
import shutil
import subprocess
import sys
import threading


def play_alert_sound() -> None:
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

    def _play() -> None:
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
