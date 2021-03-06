from typing import Optional, Tuple


class ErrorWhilePutInQueue(Exception):
    def __init__(self, text: str, data: Optional[Tuple[str, dict]] = None):
        self.text = text
        self.data = data


class ErrorWhileSending(Exception):
    pass


class NoMessageFromPolice(Exception):
    pass


class AppealURLParsingFailed(Exception):
    pass


class CaptchaInputError(Exception):
    pass


class BrowserError(Exception):
    pass


class RancidAppeal(Exception):
    pass
