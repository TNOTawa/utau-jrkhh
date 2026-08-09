"""结构化错误类型与稳定退出码。"""

from __future__ import annotations

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2
EXIT_VALIDATION = 3
EXIT_STRICT_MISSING = 4

# 错误类别 → 退出码
_CATEGORY_EXIT = {
    "data-error": EXIT_ERROR,
    "not-found": EXIT_ERROR,
    "invalid-input": EXIT_ERROR,
    "missing-dependency": EXIT_ERROR,
    "frozen": EXIT_ERROR,
    "validation-error": EXIT_VALIDATION,
    "conflict": EXIT_VALIDATION,
}


class JRHError(Exception):
    """JRH 领域错误。message 面向用户；category 决定退出码。"""

    def __init__(self, message: str, category: str = "data-error"):
        super().__init__(message)
        self.message = message
        self.category = category

    def exit_code(self) -> int:
        return _CATEGORY_EXIT.get(self.category, EXIT_ERROR)


class DataError(JRHError):
    def __init__(self, message: str):
        super().__init__(message, "data-error")


class NotFoundError(JRHError):
    def __init__(self, message: str):
        super().__init__(message, "not-found")


class InvalidInputError(JRHError):
    def __init__(self, message: str):
        super().__init__(message, "invalid-input")


class FrozenError(JRHError):
    def __init__(self, message: str):
        super().__init__(message, "frozen")


class ValidationError(JRHError):
    def __init__(self, message: str):
        super().__init__(message, "validation-error")


class ConflictError(JRHError):
    def __init__(self, message: str):
        super().__init__(message, "conflict")


class MissingDependencyError(JRHError):
    def __init__(self, message: str):
        super().__init__(message, "missing-dependency")
