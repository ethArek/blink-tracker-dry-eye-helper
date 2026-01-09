import os
import platform
import shutil
import subprocess
import sys
import threading


def play_alert_sound(sound: str = "exclamation", sound_file: str | None = None) -> None:
    """
    Play an alert sound asynchronously using a best-effort, platform-specific backend.

    The sound is played in a separate daemon thread so that calls to this function
    are non-blocking and do not interrupt the main video-processing loop.

    Platform behavior:
      * Windows:
          - Use a system sound alias (e.g. ``SystemExclamation``) when possible.
          - Otherwise fall back to ``winsound.MessageBeep`` / ``winsound.Beep``.
      * macOS (Darwin): use ``afplay`` with a system sound under
        ``/System/Library/Sounds`` when available.
      * Linux/other Unix-like systems:
          - Prefer ``paplay`` (PulseAudio) with common freedesktop sound files, if
            both the command and at least one sound file exist.
          - Otherwise, try ``aplay`` (ALSA) with a common system sound file.

    If no platform-specific method succeeds, the function falls back to writing the
    ASCII bell character (``\\a``) to standard output to trigger a terminal beep
    when supported.
    """

    sound = (sound or "exclamation").strip().lower()
    sound_file = sound_file.strip() if isinstance(sound_file, str) else None

    def _play() -> None:
        if sound in {"none", "off", "disabled"}:
            return

        system = platform.system()
        custom_path = None
        if sound_file:
            candidate = os.path.expanduser(sound_file)
            if os.path.exists(candidate):
                custom_path = candidate

        if custom_path is not None:
            if system == "Windows":
                try:
                    import winsound

                    winsound.PlaySound(
                        custom_path,
                        winsound.SND_FILENAME | winsound.SND_ASYNC,
                    )
                    return
                except Exception:
                    pass

            if system == "Darwin" and shutil.which("afplay"):
                subprocess.Popen(
                    ["afplay", custom_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

            if shutil.which("paplay"):
                subprocess.Popen(
                    ["paplay", custom_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

            if shutil.which("aplay"):
                subprocess.Popen(
                    ["aplay", custom_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

        if system == "Windows":
            try:
                import winsound

                alias_map: dict[str, tuple[str, int]] = {
                    "exclamation": ("SystemExclamation", winsound.MB_ICONEXCLAMATION),
                    "asterisk": ("SystemAsterisk", winsound.MB_ICONASTERISK),
                    "hand": ("SystemHand", winsound.MB_ICONHAND),
                    "question": ("SystemQuestion", winsound.MB_ICONQUESTION),
                }

                if sound in alias_map:
                    alias, message_beep_kind = alias_map[sound]
                    try:
                        winsound.PlaySound(
                            alias,
                            winsound.SND_ALIAS | winsound.SND_ASYNC,
                        )
                        return
                    except Exception:
                        pass

                    try:
                        winsound.MessageBeep(message_beep_kind)
                        return
                    except Exception:
                        pass

                if sound == "beep":
                    winsound.Beep(1100, 180)
                    winsound.Beep(850, 180)
                    return

                try:
                    winsound.MessageBeep()
                    return
                except Exception:
                    pass
            except Exception:
                pass

        if system == "Darwin":
            mac_sounds: dict[str, str] = {
                "glass": "Glass.aiff",
                "ping": "Ping.aiff",
                "pop": "Pop.aiff",
                "basso": "Basso.aiff",
                "tink": "Tink.aiff",
                "submarine": "Submarine.aiff",
            }
            mac_sound = os.path.join(
                "/System/Library/Sounds",
                mac_sounds.get(sound, "Glass.aiff"),
            )
            if shutil.which("afplay") and os.path.exists(mac_sound):
                subprocess.Popen(
                    ["afplay", mac_sound],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return

        if shutil.which("paplay"):
            preferred = {
                "exclamation": "/usr/share/sounds/freedesktop/stereo/dialog-warning.oga",
                "asterisk": "/usr/share/sounds/freedesktop/stereo/complete.oga",
                "hand": "/usr/share/sounds/freedesktop/stereo/dialog-error.oga",
                "question": "/usr/share/sounds/freedesktop/stereo/message.oga",
                "beep": "/usr/share/sounds/freedesktop/stereo/bell.oga",
            }.get(sound)
            candidates = [preferred] if preferred else []
            candidates += [
                "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga",
                "/usr/share/sounds/freedesktop/stereo/complete.oga",
            ]
            for sound_path in candidates:
                if sound_path and os.path.exists(sound_path):
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
