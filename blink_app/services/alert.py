import io
import logging
import math
import os
import platform
import shutil
import subprocess
import sys
import threading
import wave

_ALERT_THREAD_LOCK = threading.Lock()
_ALERT_THREAD: threading.Thread | None = None

_ALERT_PROCESS_LOCK = threading.Lock()
_ALERT_PROCESS: subprocess.Popen | None = None


def _qt_beep() -> bool:
    try:
        from PySide6 import QtWidgets
    except Exception:
        return False

    app = QtWidgets.QApplication.instance()
    if app is None:
        return False

    try:
        app.beep()
    except Exception:
        return False

    return True


def _start_alert_process(command: list[str]) -> bool:
    global _ALERT_PROCESS

    with _ALERT_PROCESS_LOCK:
        if _ALERT_PROCESS is not None and _ALERT_PROCESS.poll() is None:
            return True

        try:
            _ALERT_PROCESS = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return False

    return True


def _play_windows_tone(winsound_module, sound: str) -> bool:
    tone_map: dict[str, list[tuple[int, int]]] = {
        "exclamation": [(1240, 110), (880, 170)],
        "asterisk": [(1040, 140)],
        "hand": [(740, 210), (540, 220)],
        "question": [(930, 110), (1130, 120)],
        "beep": [(1100, 180), (850, 180)],
    }
    tones = tone_map.get(sound, tone_map["beep"])
    try:
        for frequency, duration in tones:
            winsound_module.Beep(frequency, duration)
    except Exception:
        return False

    return True


def _build_windows_alert_wave(sound: str) -> bytes:
    tone_map: dict[str, list[tuple[int, int]]] = {
        "exclamation": [(1240, 110), (880, 170)],
        "asterisk": [(1040, 140)],
        "hand": [(740, 210), (540, 220)],
        "question": [(930, 110), (1130, 120)],
        "beep": [(1100, 180), (850, 180)],
    }
    tones = tone_map.get(sound, tone_map["beep"])
    sample_rate = 22050
    amplitude = 0.33

    def append_tone(frames: bytearray, frequency: int, duration_ms: int) -> None:
        total_samples = max(1, int(sample_rate * (duration_ms / 1000.0)))
        fade_samples = min(
            total_samples // 4,
            max(1, int(sample_rate * 0.005)),
        )
        for sample_index in range(total_samples):
            envelope = 1.0
            if sample_index < fade_samples:
                envelope = sample_index / fade_samples
            elif sample_index >= total_samples - fade_samples:
                envelope = (total_samples - sample_index - 1) / fade_samples

            value = int(
                32767
                * amplitude
                * envelope
                * math.sin((2.0 * math.pi * frequency * sample_index) / sample_rate)
            )
            frames.extend(int(value).to_bytes(2, byteorder="little", signed=True))

    pcm_frames = bytearray()
    for tone_index, (frequency, duration_ms) in enumerate(tones):
        append_tone(pcm_frames, frequency, duration_ms)
        if tone_index != len(tones) - 1:
            silence_samples = int(sample_rate * 0.03)
            pcm_frames.extend(b"\x00\x00" * silence_samples)

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(pcm_frames))

    return buffer.getvalue()


def _play_windows_wave(winsound_module, sound: str) -> bool:
    try:
        alert_wave = _build_windows_alert_wave(sound)
        winsound_module.PlaySound(
            alert_wave,
            winsound_module.SND_MEMORY,
        )
    except Exception:
        return False

    return True


def _play_alert_sound_now(sound: str = "exclamation", sound_file: str | None = None) -> None:
    logger = logging.getLogger("app")
    sound = (sound or "exclamation").strip().lower()
    sound_file = sound_file.strip() if isinstance(sound_file, str) else None

    if sound in {"none", "off", "disabled"}:
        return

    system = platform.system()
    custom_path = None
    if sound_file:
        candidate = os.path.expanduser(sound_file)
        if os.path.exists(candidate):
            custom_path = candidate
        else:
            logger.warning("Alert sound file was not found: %s", sound_file)

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
                logger.debug("Windows custom alert playback failed.", exc_info=True)

        if system == "Darwin" and shutil.which("afplay"):
            if _start_alert_process(["afplay", custom_path]):
                return

        if shutil.which("paplay"):
            if _start_alert_process(["paplay", custom_path]):
                return

        if shutil.which("aplay"):
            if _start_alert_process(["aplay", custom_path]):
                return

    if system == "Windows":
        try:
            import winsound

            if _play_windows_wave(winsound, sound):
                return

            logger.debug("Windows generated alert playback failed. Falling back to system sounds.")
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
                    logger.debug("Windows alias alert playback failed.", exc_info=True)

                try:
                    winsound.MessageBeep(message_beep_kind)
                    return
                except Exception:
                    logger.debug("Windows MessageBeep fallback failed.", exc_info=True)

            if _play_windows_tone(winsound, sound):
                return

            try:
                winsound.MessageBeep()
                return
            except Exception:
                logger.debug("Windows default MessageBeep failed.", exc_info=True)
        except Exception:
            logger.debug("winsound was unavailable for alert playback.", exc_info=True)

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
            if _start_alert_process(["afplay", mac_sound]):
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
                if _start_alert_process(["paplay", sound_path]):
                    return

    if shutil.which("aplay"):
        for sound_path in ("/usr/share/sounds/alsa/Front_Center.wav",):
            if os.path.exists(sound_path):
                if _start_alert_process(["aplay", sound_path]):
                    return

    if _qt_beep():
        return

    logger.warning("No usable audio backend was found for alert playback. Falling back to terminal bell.")
    sys.stdout.write("\a")
    sys.stdout.flush()


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

    global _ALERT_THREAD

    alert_thread = threading.Thread(
        target=_play_alert_sound_now,
        args=(sound, sound_file),
        daemon=True,
    )
    with _ALERT_THREAD_LOCK:
        if _ALERT_THREAD is not None and _ALERT_THREAD.is_alive():
            return
        _ALERT_THREAD = alert_thread
    alert_thread.start()
