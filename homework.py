import logging
import os
import time
import requests
import sys
from http import HTTPStatus
import telegram
from dotenv import load_dotenv
from exceptions import (RequestExceptionError,
                        UndocumentedStatusError,
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
logging.basicConfig(
    level=logging.INFO,
    filename='main.log',
    format='%(funcName)s, %(lineno)s, %(levelname)s, %(message)s',
)
handlers = [logging.FileHandler('log.txt'),
            logging.StreamHandler(sys.stdout)]


def check_tokens():
    """Проверка наличия токенов.
    Если отсутствует хотя бы одна переменная окружения — функция
    должна вернуть False, иначе — True.
    """
    return all([PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID])


def send_message(bot, message):
    """Отправка сообщения в Телеграм."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logging.debug(
            f'Сообщение в Telegram отправлено: {message}')
    except telegram.TelegramError as telegram_error:
        logging.exception(
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
        homework_statuses = requests.get(**data)
    except Exception as error:
        raise Exception(f'Ошибка при запросе к основному API: {error}')
    if homework_statuses.status_code != HTTPStatus.OK:
        logging.error(f'Ошибка {homework_statuses.status_code}')
        raise StatusCodeError(f'Ошибка {homework_statuses.status_code}')
    try:
        return homework_statuses.json()
    except ValueError:
        raise ValueError('Ошибка парсинга ответа из формата json')


def check_response(response):
    """Проверяем данные API на соответствие документации."""
    if not isinstance(response, dict) or response is None:
        raise TypeError('Ответ API не содержит словаря с данными')
    if not isinstance(response.get('homeworks'), list):
        raise TypeError('Ключ homeworks в ответе API не содержит списка')
    try:
        homework = response['homeworks'][0]
    except (KeyError, IndexError):
        logging.error('Список домашних работ пуст')
        raise RequestExceptionError('Список домашних работ пуст')
    return homework


def parse_status(homework):
    """Информация о статусе домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError('Отсутствует ключ "homework_name" в ответе API')
    if 'status' not in homework:
        raise KeyError('Отсутствует ключ "status" в ответе API')
    status = homework.get('status')
    homework_name = homework.get('homework_name')
    if status in HOMEWORK_VERDICTS:
        verdict = HOMEWORK_VERDICTS[status]
    else:
        message = 'Статус проверки работы не известен'
        logging.debug(message)
        raise UndocumentedStatusError(message)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logging.critical('Отсутствуют переменные окружения')
        return Exception('Отсутствуют переменные окружения')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    tmp_status = ''
    errors = ''
    while True:
        try:
            response = get_api_answer(timestamp)
            message = parse_status(check_response(response))
            if message != tmp_status:
                send_message(bot, message)
                tmp_status = message
            logging.info(
                'Изменений нет, ждем 10 минут и проверяем API')
            time.sleep(RETRY_PERIOD)
        except Exception as error:
            logging.error(error)
            message_t = f'{error}'
            if message_t != errors:
                send_message(bot, message_t)
                errors = message_t
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
