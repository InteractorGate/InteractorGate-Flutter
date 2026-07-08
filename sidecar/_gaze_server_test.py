"""Test determinístico del path de envío de gaze_server._stream (sin cámara ni
cara): mockea cap/tracker/mapper con las dataclasses reales y verifica que se
emite JSON {x,y,blink} bien formado. Debug script (_ prefix)."""
import json

import numpy as np

import gaze_server
from eye_tracker import EyeData, FaceResult


def _fake_res(openness):
    eye = EyeData(patch=np.zeros((36, 60), np.uint8), iris=(0.5, 0.5),
                  openness=openness, h_ratio=0.5, v_ratio=0.5)
    return FaceResult(right=eye, left=eye, pose_matrix=np.eye(4))


class FakeCap:
    def read(self):
        return True, np.zeros((480, 640, 3), np.uint8)


class FakeTracker:
    def __init__(self):
        # alterna: ojo abierto (emite gaze) y un frame "cerrado" (mantiene pos)
        self._seq = [0.30, 0.30, 0.05, 0.30] * 10
        self._i = 0

    def process(self, frame, ts):
        o = self._seq[self._i % len(self._seq)]
        self._i += 1
        return _fake_res(o)


class FakeMapper:
    def transform(self, feat):
        return 0.42, 0.71


class FakeConn:
    def __init__(self, stop_after):
        self.sent = []
        self._stop = stop_after

    def sendall(self, data):
        self.sent.append(data)
        if len(self.sent) >= self._stop:
            raise BrokenPipeError("stop test")


def main():
    ctx = {"cap": FakeCap(), "tracker": FakeTracker(), "mapper": FakeMapper()}
    conn = FakeConn(stop_after=8)
    try:
        gaze_server._stream(conn, ctx)
    except BrokenPipeError:
        pass

    ok = True
    for raw in conn.sent:
        assert raw.endswith(b"\n"), "falta newline"
        d = json.loads(raw)
        assert set(d) == {"x", "y", "blink"}, d
        assert d["x"] == 0.42 and d["y"] == 0.71, d
        assert isinstance(d["blink"], bool), d
        print("  ->", raw.decode().strip())
    print(f"\n{'PASS' if ok else 'FAIL'}: {len(conn.sent)} payloads validos, "
          f"contrato {{x,y,blink}} correcto")


if __name__ == "__main__":
    main()
