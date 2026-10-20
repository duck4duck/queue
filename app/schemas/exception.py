class UserNotFound(Exception):
    def __init__(self, msg: str = "Пользователь не найден!"):
        self.msg = msg


class QueueException(Exception):
    def __init__(self, msg: str = "Такую ошибку мы не ожидали!"):
        self.msg = msg


class UserAlreadyInQueue(QueueException):
    def __init__(self, msg: str = "Пользователь уже в очереди!"):
        super().__init__(msg)


class UserNotInQueue(QueueException):
    def __init__(self, msg: str = "Пользователя нет в очереди!"):
        super().__init__(msg)


class PositionTaken(QueueException):
    def __init__(self, msg: str = "Место занято!"):
        super().__init__(msg)


class PositionEmpty(QueueException):
    def __init__(self, msg: str = "Место пустое!"):
        super().__init__(msg)


class InvalidPosition(QueueException):
    def __init__(self, msg: str = "Некорректный номер позиции!"):
        super().__init__(msg)


class Forbidden(Exception):
    def __init__(self, msg: str = "Нет прав для выполнения этого действия!"):
        self.msg = msg


class QueueAlreadyExists(QueueException):
    def __init__(self, msg: str = "Очередь с таким названием уже существует!"):
        super().__init__(msg)


class QueueNotFound(QueueException):
    def __init__(self, msg: str = "Очередь не найдена!"):
        super().__init__(msg)


class QueuePaused(QueueException):
    def __init__(self, msg: str = "Очередь временно приостановлена!"):
        super().__init__(msg)


class SwapRequestException(Exception):
    def __init__(self, msg: str = "Ошибка запроса обмена!"):
        self.msg = msg


class SwapRequestNotFound(SwapRequestException):
    def __init__(self, msg: str = "Запрос на обмен не найден!"):
        super().__init__(msg)


class SwapRequestAlreadyExists(SwapRequestException):
    def __init__(self, msg: str = "У вас уже есть активный запрос на обмен в этой очереди!"):
        super().__init__(msg)


class SwapRequestExpired(SwapRequestException):
    def __init__(self, msg: str = "Запрос на обмен истёк или стал недействительным!"):
        super().__init__(msg)


class SubjectNotFound(Exception):
    def __init__(self, msg: str = "Предмет не найден!"):
        self.msg = msg


class SubjectAlreadyExists(Exception):
    def __init__(self, msg: str = "Предмет с таким именем уже существует!"):
        self.msg = msg


class InvalidRole(Exception):
    def __init__(self, msg: str = "Недопустимая роль! Допустимые роли: student, curator."):
        self.msg = msg
