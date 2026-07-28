"""
webcam.py
Grabs a single still frame from the default camera using OpenCV. Used by
the desktop GUI's "what am I looking at" / webcam-snapshot feature. The
web UI does the equivalent in-browser via getUserMedia instead — this
module is desktop-only since it needs local camera hardware access.
"""
from utils import get_logger, safe_import

log = get_logger("webcam")

_cv2 = safe_import("cv2")


def is_available() -> bool:
    return _cv2 is not None


def capture_frame(camera_index: int = 0):
    """Return a single frame as JPEG bytes, or None on failure (no camera,
    package missing, camera in use by another app, etc.)."""
    if _cv2 is None:
        log.info("opencv-python not installed; webcam capture disabled")
        return None

    cam = _cv2.VideoCapture(camera_index)
    try:
        if not cam.isOpened():
            log.warning("could not open camera %s", camera_index)
            return None
        # Some cameras need a couple of warm-up frames before exposure settles.
        for _ in range(3):
            cam.read()
        ok, frame = cam.read()
        if not ok:
            log.warning("failed to read a frame from the camera")
            return None
        ok, buf = _cv2.imencode(".jpg", frame)
        if not ok:
            return None
        return buf.tobytes()
    finally:
        cam.release()
