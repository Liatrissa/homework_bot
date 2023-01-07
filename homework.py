import logging
import os
import time
import requests
import telegram
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from exceptions import (RequestExceptionError,
                        UndocumentedStatusError,
                        APIResponseError,
                        StatusCodeError)

load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
TOKENS = ('PRACTICUM_TOKEN', 'TELEGRAM_TOKEN', 'TELEGRAM_CHAT_ID')
TOKENS_NOT_FOUND = ('Программа принудительно остановлена. '
                    'Отсутствует обязательная переменная окружения:{}')
TOKENS_ERROR = 'Ошибка в токенах.'

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}
# Задаем глобальную конфигурацию для всех логгеров
logging.basicConfig(
    level=logging.DEBUG,
    filename='program.log',
    filemode='w',
    format='%(asctime)s - %(levelname)s - %(message)s - %(name)s'
)
# Устанавливаем настройки логгера для текущего файла
logger = logging.getLogger(__name__)
# Устанавливаем уровень, с которого логи будут сохраняться в файл
logger.setLevel(logging.INFO)
# Указываем обработчик логов
handler = RotatingFileHandler('my_logger.log',
                              maxBytes=50000000, backupCount=5)
logger.addHandler(handler)
# Создаем форматер
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Применяем его к хэндлеру
handler.setFormatter(formatter)


def check_tokens():
    """Проверка наличия токенов."""
    for tokens in TOKENS:
        if globals()[tokens] is None:
            logger.critical(TOKENS_NOT_FOUND.format(tokens))
            raise ValueError(TOKENS_ERROR)


def send_message(bot, message):
    """Отправка сообщения в Телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(
            f'Сообщение в Telegram отправлено: {message}')
    except telegram.TelegramError as telegram_error:
        logger.error(
            f'Сообщение в Telegram не отправлено: {telegram_error}')


def get_api_answer(timestamp):
    """Получение данных с API Yandex Practicum."""
    timestamp = timestamp or int(time.time())
    params = {'from_date': timestamp}
    data = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': params
    }
    try:
        # Делаем GET-запрос к эндпоинту url
        response = requests.get(**data)
        if response.status_code != 200:
            code_api_msg = (
                f'Эндпоинт {response.url} недоступен.'
                f' Код ответа API: {response.status_code}')
            logger.error(code_api_msg)
            raise StatusCodeError(code_api_msg)
        return response.json()
    except requests.exceptions.RequestException as request_error:
        code_api_msg = f'Код ответа API (RequestException): {request_error}'
        logger.error(code_api_msg)
        raise RequestExceptionError(code_api_msg) from request_error


def check_response(response):
    """Проверяем данные API на соответствие документации."""
    if not isinstance(response, dict) or response is None:
        message = 'Ответ API не содержит словаря с данными'
        raise TypeError(message)
    if not isinstance(response.get('homeworks'), list):
        message = 'Ключ homeworks в ответе API не содержит списка'
        raise TypeError(message)
    if response.get('homeworks') is None:
        code_api_msg = (
            'Ошибка ключа homeworks или response')
        logger.error(code_api_msg)
        raise KeyError('Отсутствует ключ homeworks.')
    status = response['homeworks'][0].get('status')
    if status not in HOMEWORK_VERDICTS:
        code_api_msg = f'Ошибка- недокументированный статус: {status}'
        logger.error(code_api_msg)
        raise UndocumentedStatusError(code_api_msg)
    return response['homeworks'][0]


def parse_status(homework):
    """Информация о статусе домашней работы."""
    status = homework.get('status')
    homework_name = homework.get('homework_name')
    if status is None:
        message = f'Ошибка- пустое значение: {status}'
        logger.error(message)
        raise KeyError(message)
    if homework_name is None:
        message = f'Ошибка- пустое значение: {homework_name}'
        logger.error(message)
        raise KeyError(message)
    if status in HOMEWORK_VERDICTS:
        verdict = HOMEWORK_VERDICTS[status]
    else:
        message = 'Статус проверки работы не известен'
        logger.debug(message)
        raise APIResponseError(message)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    tmp_status = 'reviewing'
    errors = True
    while True:
        try:
            response = get_api_answer(timestamp)
            homework = check_response(response)
            if homework and tmp_status != homework['status']:
                message = parse_status(homework)
                send_message(bot, message)
                tmp_status = homework['status']
            logger.info(
                'Изменений нет, ждем 10 минут и проверяем API')
            time.sleep(RETRY_PERIOD)
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if errors:
                errors = False
                send_message(bot, message)
            logger.critical(message)
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
