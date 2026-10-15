from enum import StrEnum


class ContentAudioFormat(StrEnum):
    MP3 = "mp3"
    WAV = "wav"

    def __str__(self) -> str:
        return str(self.value)
