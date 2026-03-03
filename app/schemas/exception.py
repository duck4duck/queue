

class UserNotFound(Exception):
     def __init__(self, msg: str = "Пользователь не найден!"):
        self.msg = msg


class QueueException(Exception):
    def __init__(self, msg: str = "Такую ошибку мы не ожидали!"):
        self.msg = msg


    


class UserAlreadyInQueue(QueueException):
    def __init__(self,msg: str = "Пользователь уже в очереди!"):
        super().__init__(msg)


class UserNotInQueue(QueueException):
    def __init__(self,msg: str = "Пользователя нет в очереди!"):
        super().__init__(msg)

class PositionTaken(QueueException):
    def __init__(self,msg: str = "Место занято!"):
        super().__init__(msg)

class PositionEmpty(QueueException):
    def __init__(self,msg: str = "Место пустое!"):
        super().__init__(msg)

class InvalidPosition(QueueException):
    def __init__(self,msg: str = "Неккоректый номер позиции"):
        super().__init__(msg)