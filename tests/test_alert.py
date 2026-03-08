import types
import unittest
from unittest.mock import patch

from blink_app.services.alert import _play_alert_sound_now


def _build_fake_winsound(
    play_sound_side_effect=None,
) -> tuple[types.ModuleType, dict[str, list[object]]]:
    calls: dict[str, list[object]] = {
        "play_sound": [],
        "message_beep": [],
        "beep": [],
    }

    fake_winsound = types.ModuleType("winsound")
    fake_winsound.SND_MEMORY = 1
    fake_winsound.SND_FILENAME = 2
    fake_winsound.SND_ASYNC = 4
    fake_winsound.SND_ALIAS = 8
    fake_winsound.MB_ICONEXCLAMATION = 16
    fake_winsound.MB_ICONASTERISK = 32
    fake_winsound.MB_ICONHAND = 64
    fake_winsound.MB_ICONQUESTION = 128

    def play_sound(sound, flags) -> None:
        calls["play_sound"].append((sound, flags))
        if play_sound_side_effect is not None:
            play_sound_side_effect(sound, flags)

    def message_beep(kind=None) -> None:
        calls["message_beep"].append(kind)

    def beep(frequency: int, duration: int) -> None:
        calls["beep"].append((frequency, duration))

    fake_winsound.PlaySound = play_sound
    fake_winsound.MessageBeep = message_beep
    fake_winsound.Beep = beep
    return fake_winsound, calls


class AlertServiceTest(unittest.TestCase):
    def test_play_alert_sound_uses_generated_windows_wave(self) -> None:
        fake_winsound, calls = _build_fake_winsound()

        with patch("platform.system", return_value="Windows"):
            with patch.dict("sys.modules", {"winsound": fake_winsound}):
                _play_alert_sound_now(sound="exclamation")

        self.assertEqual(len(calls["play_sound"]), 1)
        sound, flags = calls["play_sound"][0]
        self.assertIsInstance(sound, bytes)
        self.assertEqual(flags, fake_winsound.SND_MEMORY)
        self.assertEqual(calls["message_beep"], [])
        self.assertEqual(calls["beep"], [])

    def test_play_alert_sound_falls_back_to_windows_aliases_when_wave_fails(self) -> None:
        def fail_memory_playback(sound, flags) -> None:
            if flags == fake_winsound.SND_MEMORY:
                raise RuntimeError("memory playback failed")

        fake_winsound, calls = _build_fake_winsound(play_sound_side_effect=fail_memory_playback)

        with patch("platform.system", return_value="Windows"):
            with patch.dict("sys.modules", {"winsound": fake_winsound}):
                _play_alert_sound_now(sound="exclamation")

        self.assertEqual(len(calls["play_sound"]), 2)
        first_sound, first_flags = calls["play_sound"][0]
        second_sound, second_flags = calls["play_sound"][1]
        self.assertIsInstance(first_sound, bytes)
        self.assertEqual(first_flags, fake_winsound.SND_MEMORY)
        self.assertEqual(second_sound, "SystemExclamation")
        self.assertEqual(second_flags, fake_winsound.SND_ALIAS | fake_winsound.SND_ASYNC)

    def test_play_alert_sound_falls_back_to_terminal_bell_without_backend(self) -> None:
        with patch("platform.system", return_value="Linux"):
            with patch("shutil.which", return_value=None):
                with patch("blink_app.services.alert._qt_beep", return_value=False):
                    with patch("sys.stdout.write") as write_mock:
                        with patch("sys.stdout.flush") as flush_mock:
                            _play_alert_sound_now(sound="exclamation")

        write_mock.assert_called_once_with("\a")
        flush_mock.assert_called_once()


if __name__ == "__main__":
    unittest.main()
