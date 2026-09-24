from enum import Enum


class ContentAudioFormat(str, Enum):
    MP3 = "mp3"
    WAV = "wav"

    def __str__(self) -> str:
        return str(self.value)
