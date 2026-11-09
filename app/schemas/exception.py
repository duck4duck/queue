class AppException(Exception):
    status_code: int = 500

    def __init__(self, msg: str = "Внутренняя ошибка сервиса"):
        super().__init__(msg)
        self.msg = msg


# ──────────────────── User Exceptions ────────────────────

class UserNotFound(AppException):
    status_code: int = 404

    def __init__(self, msg: str = "Пользователь не найден!"):
        super().__init__(msg)


class Forbidden(AppException):
    status_code: int = 403

    def __init__(self, msg: str = "Нет прав для выполнения этого действия!"):
        super().__init__(msg)


class InvalidRole(AppException):
    status_code: int = 400

    def __init__(self, msg: str = "Недопустимая роль! Допустимые роли: student, curator."):
        super().__init__(msg)


# ──────────────────── Subject Exceptions ────────────────────

class SubjectNotFound(AppException):
    status_code: int = 404

    def __init__(self, msg: str = "Предмет не найден!"):
        super().__init__(msg)


class SubjectAlreadyExists(AppException):
    status_code: int = 409

    def __init__(self, msg: str = "Предмет с таким именем уже существует!"):
        super().__init__(msg)


# ──────────────────── Queue Exceptions ────────────────────

class QueueException(AppException):
    status_code: int = 500

    def __init__(self, msg: str = "Такую ошибку мы не ожидали!"):
        super().__init__(msg)


class UserAlreadyInQueue(QueueException):
    status_code: int = 409

    def __init__(self, msg: str = "Вы уже находитесь в этой очереди!"):
        super().__init__(msg)


class UserNotInQueue(QueueException):
    status_code: int = 404

    def __init__(self, msg: str = "Пользователя нет в очереди!"):
        super().__init__(msg)


class PositionTaken(QueueException):
    status_code: int = 409

    def __init__(self, msg: str = "Место занято!"):
        super().__init__(msg)


class PositionEmpty(QueueException):
    status_code: int = 404

    def __init__(self, msg: str = "Место пустое!"):
        super().__init__(msg)


class InvalidPosition(QueueException):
    status_code: int = 400

    def __init__(self, msg: str = "Некорректный номер позиции!"):
        super().__init__(msg)


class QueueAlreadyExists(QueueException):
    status_code: int = 409

    def __init__(self, msg: str = "Очередь с таким названием уже существует!"):
        super().__init__(msg)


class QueueNotFound(QueueException):
    status_code: int = 404

    def __init__(self, msg: str = "Очередь не найдена!"):
        super().__init__(msg)


class QueuePaused(QueueException):
    status_code: int = 403

    def __init__(self, msg: str = "Очередь временно приостановлена!"):
        super().__init__(msg)


# ──────────────────── Swap Request Exceptions ────────────────────

class SwapRequestException(AppException):
    status_code: int = 400

    def __init__(self, msg: str = "Ошибка запроса обмена!"):
        super().__init__(msg)


class SwapRequestNotFound(SwapRequestException):
    status_code: int = 404

    def __init__(self, msg: str = "Запрос на обмен не найден!"):
        super().__init__(msg)


class SwapRequestAlreadyExists(SwapRequestException):
    status_code: int = 409

    def __init__(self, msg: str = "У вас уже есть активный запрос на обмен в этой очереди!"):
        super().__init__(msg)


class SwapRequestExpired(SwapRequestException):
    status_code: int = 400

    def __init__(self, msg: str = "Запрос на обмен истёк или стал недействительным!"):
        super().__init__(msg)
