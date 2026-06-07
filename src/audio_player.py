import queue
import threading
from pathlib import Path
from typing import Optional

import numpy as np
import sounddevice as sd
import soundfile as sf


class AudioPlayer:
    def __init__(self):
        self._playing = False
        self._lock = threading.Lock()
        self._cmd_queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()

    def play_segment(self, wav_path: Path, offset_ms: float, cutoff_ms: float):
        with self._lock:
            self._playing = True
        self._cmd_queue.put(("play", wav_path, offset_ms, cutoff_ms))

    def stop(self):
        with self._lock:
            self._playing = False
        self._cmd_queue.put(("stop",))

    @property
    def is_playing(self) -> bool:
        return self._playing

    @staticmethod
    def _silent_stop():
        try:
            sd.stop()
        except Exception:
            pass

    def _drain_latest(self, first_play: tuple) -> tuple:
        """排空队列，返回最新的 play 参数 (wav_path, offset_ms, cutoff_ms)"""
        latest = (first_play[1], first_play[2], first_play[3])
        while True:
            try:
                c = self._cmd_queue.get_nowait()
                if c[0] == "play":
                    latest = (c[1], c[2], c[3])
                elif c[0] == "stop":
                    self._silent_stop()
            except queue.Empty:
                break
        return latest

    def _worker_loop(self):
        while True:
            cmd = self._cmd_queue.get()
            if cmd[0] == "stop":
                self._silent_stop()
                continue

            wav_path, offset_ms, cutoff_ms = self._drain_latest(cmd)
            self._silent_stop()

            try:
                data, sr = sf.read(str(wav_path))
            except Exception:
                continue
            if data.ndim > 1:
                data = data[:, 0]

            seg_s = abs(cutoff_ms) / 1000.0
            start_idx = max(0, int(offset_ms / 1000.0 * sr))
            end_idx = min(len(data), int((offset_ms / 1000.0 + seg_s) * sr))
            if end_idx <= start_idx:
                continue
            segment = data[start_idx:end_idx]
            del data

            try:
                sd.play(segment, sr, blocking=False)
            except Exception:
                continue

            while True:
                try:
                    c = self._cmd_queue.get(timeout=0.12)
                except queue.Empty:
                    try:
                        if not sd.get_stream().active:
                            break
                    except Exception:
                        break
                    continue
                self._silent_stop()
                if c[0] == "play":
                    self._cmd_queue.put(c)
                break

            with self._lock:
                if self._playing:
                    self._playing = False

    def cleanup(self):
        self.stop()
