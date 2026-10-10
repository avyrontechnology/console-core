from .base import BaseLogger


class ConsoleServiceLogger(BaseLogger):
    def __init__(self) -> None:
        super().__init__()
