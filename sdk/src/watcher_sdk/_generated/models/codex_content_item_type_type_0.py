from enum import Enum


class CodexContentItemTypeType0(str, Enum):
    INPUT_IMAGE = "input_image"
    INPUT_TEXT = "input_text"
    OUTPUT_TEXT = "output_text"
    TEXT = "text"

    def __str__(self) -> str:
        return str(self.value)
