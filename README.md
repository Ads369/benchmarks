# benchmarks

Набор небольших performance-тестов для Python-библиотек.

## Установка

Проект использует `uv`.

```bash
uv sync
```

Если зависимости уже установлены, можно сразу запускать нужный бенчмарк через
`uv run`.

## Доступные тесты

### HTTP-клиенты

Файл: `src/httpx_aiohhtp_pyreqwest.py`

Сравнивает асинхронные HTTP GET-запросы к `https://httpbun.com/delay/0.5`.

Участники:

- `pyreqwest`
- `httpx`
- `aiohttp`
- `zapros` через `AsyncPyreqwestHandler`

Параметры по умолчанию:

- `CONCURRENCY = 200`
- `ITERATIONS = 5`
- `TEST_URL = "https://httpbun.com/delay/0.5"`

Запуск:

```bash
uv run python src/httpx_aiohhtp_pyreqwest.py
```

Скрипт выводит среднее время выполнения, средний RPS и количество успешных /
ошибочных запросов. Внешний endpoint может быть нестабилен под высокой
параллельностью, поэтому ошибки подключения считаются в результате и не
останавливают весь бенчмарк.

### JSON, сериализация и валидация

Файл: `src/msgspec_pydantic_orjson.py`

Сравнивает скорость работы с плоскими и вложенными структурами данных.

Участники:

- `msgspec`
- `pydantic`
- стандартный `json`
- `orjson`

Сценарии:

- сериализация плоских моделей
- десериализация плоских моделей с custom validation
- сериализация вложенных моделей
- десериализация вложенных моделей
- обработка лишних полей
- приведение типов
- обработка неверных типов данных

Параметры по умолчанию:

- `NUMBER = 10`
- `NUM_RECORDS = 1000`
- `ITEMS_PER_ORDER = 5`

Запуск:

```bash
uv run python src/msgspec_pydantic_orjson.py
```

Скрипт печатает таблицу со временем выполнения в миллисекундах и короткий
анализ специфических сценариев.

## Проверки кода

Синтаксическая проверка конкретного скрипта:

```bash
uv run python -m py_compile src/httpx_aiohhtp_pyreqwest.py
uv run python -m py_compile src/msgspec_pydantic_orjson.py
```

Линтер:

```bash
uv run ruff check src
```
