"""
assistant.py
Core orchestrator: takes raw user text, tries commands.py first (fast,
deterministic actions like weather/news/reminders/files/system), falls
back to ai.py for chit-chat, logs the exchange to memory, and optionally
speaks the reply. This is the single entry point the GUI (or a CLI/voice
loop) should call.

An optional `user` (email) argument threads through to memory.py so
chat/vision history is saved to that person's own private data folder
instead of the single shared memory file. Pass None (or omit it) for
single-user / CLI usage -- behavior is unchanged in that case.
"""
import re

import ai
import commands
import memory
import screen
import speech
import vision
import webcam
from utils import get_logger

log = get_logger("assistant")

_WEBCAM_TRIGGERS = re.compile(
    r"\b(what am i looking at|look through the webcam|use the webcam|"
    r"take a (picture|photo|snapshot) (of me|with the webcam)|check the webcam)\b",
    re.IGNORECASE,
)
_SCREEN_TRIGGERS = re.compile(
    r"\b(what'?s on my screen|read my screen|look at my screen|"
    r"take a screenshot|describe my screen)\b",
    re.IGNORECASE,
)


class Assistant:
    def __init__(self, speak_replies: bool = True):
        self.speak_replies = speak_replies

    def process(self, text: str, user: str = None, conversation_id: str = None) -> str:
        text = (text or "").strip()
        if not text:
            return ""

        if _WEBCAM_TRIGGERS.search(text):
            return self._capture_and_analyze(
                webcam.capture_frame(), source="webcam snapshot",
                unavailable_msg="I can't access a webcam on this machine "
                                 "(no camera, or opencv-python isn't installed).",
                user=user,
            )
        if _SCREEN_TRIGGERS.search(text):
            return self._capture_and_analyze(
                screen.capture_screen(), source="screenshot",
                unavailable_msg="I can't capture the screen on this machine.",
                user=user,
            )

        memory.add_turn("user", text, user=user, conversation_id=conversation_id)
        log.info("user: %s", text)

        try:
            response = commands.handle(text)
        except Exception as e:
            log.exception("command handling failed")
            response = f"Something went wrong running that command: {e}"

        if response is None:
            try:
                response = ai.reply(text, user=user, conversation_id=conversation_id)
            except Exception as e:
                log.exception("ai fallback failed")
                response = "Sorry, I hit an error trying to respond to that."

        memory.add_turn("assistant", response, user=user, conversation_id=conversation_id)
        log.info("assistant: %s", response)

        if self.speak_replies:
            speech.say(response)

        return response

    def _capture_and_analyze(self, image_bytes, source: str, unavailable_msg: str, user: str = None, conversation_id: str = None) -> str:
        if not image_bytes:
            memory.add_turn("assistant", unavailable_msg, user=user)
            if self.speak_replies:
                speech.say(unavailable_msg)
            return unavailable_msg
        return self.process_image(image_bytes, source=source, user=user, conversation_id=conversation_id)

    def process_image(self, image_bytes: bytes, prompt: str = None, source: str = "image", user: str = None, conversation_id: str = None) -> str:
        """Analyze an image (upload / webcam / screen capture) via
        vision.py, log it to memory like a normal turn, and optionally
        speak the result -- same contract as process()."""
        if not image_bytes:
            return "I didn't get an image to look at."

        user_note = prompt.strip() if prompt else f"[sent a {source}]"
        memory.add_turn("user", user_note, user=user)
        log.info("user sent %s (prompt=%r)", source, prompt)

        try:
            response = vision.analyze_image(image_bytes, prompt or vision.DEFAULT_PROMPT)
        except Exception as e:
            log.exception("vision analysis failed")
            response = "Something went wrong analyzing that image."

        memory.add_turn("assistant", response, user=user, conversation_id=conversation_id)
        log.info("assistant: %s", response)

        if self.speak_replies:
            speech.say(response)

        return response
