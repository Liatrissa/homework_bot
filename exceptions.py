class StatusCodeError(Exception):
    """Сервер не отвечает"""
    pass


class RequestExceptionError(Exception):
    """Ошибка запроса"""
    pass


class UndocumentedStatusError(Exception):
    """Недокументированный статус."""
    pass
