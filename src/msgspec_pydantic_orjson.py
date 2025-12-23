import json
import timeit
from typing import Any, Callable, Dict, List, Tuple

import msgspec
import orjson
from msgspec import DecodeError
from pydantic import BaseModel, Field, ValidationError, field_validator

# Установка количества прогонов для timeit
NUMBER = 10
NUM_RECORDS = 1000
ITEMS_PER_ORDER = 5


# --- 1. Определение Плоских Моделей (оставлено без изменений) ---
class MsgspecUser(msgspec.Struct):
    id: int
    name: str
    is_active: bool
    data: dict[str, Any]
    secret_code: str
    email: str | None = None

    @property
    def validate_code(self):
        code = self.secret_code
        if len(code) != 8 or not code.isdigit():
            raise ValueError("Secret code must be 8 digits long.")
        return True


class PydanticUser(BaseModel):
    id: int
    name: str
    email: str | None = None
    is_active: bool
    data: dict[str, Any]
    secret_code: str
    model_config = {"extra": "forbid"}

    @field_validator("secret_code", mode="before")
    @classmethod
    def validate_secret_code(cls, v):
        if not isinstance(v, str):
            raise ValueError("Secret code must be a string")
        if len(v) != 8 or not v.isdigit():
            raise ValueError("Secret code must be 8 digits long.")
        return v


# --- 2. Определение Вложенных Моделей (оставлено без изменений) ---
class Item(msgspec.Struct):
    product_id: int
    name: str
    price: float
    quantity: int


class PydanticItem(BaseModel):
    product_id: int
    name: str
    price: float
    quantity: int


class Order(msgspec.Struct):
    order_id: int
    customer_name: str
    items: list[Item]
    details: dict[str, Any]
    is_shipped: bool = False


class PydanticOrder(BaseModel):
    order_id: int
    customer_name: str
    items: list[PydanticItem]
    is_shipped: bool = Field(default=False)
    details: dict[str, Any]
    model_config = {"extra": "forbid"}


# --- 3. Создание Тестовых Данных (оставлено без изменений) ---


def create_flat_data(num_records):
    data = []
    for i in range(num_records):
        data.append(
            {
                "id": i,
                "name": f"User {i}",
                "email": f"user{i}@example.com",
                "is_active": (i % 2 == 0),
                "data": {"key1": i * 10},
                "secret_code": f"{i:08d}",
            }
        )
    return data


flat_test_data = create_flat_data(NUM_RECORDS)
msgspec_flat_objects = [MsgspecUser(**d) for d in flat_test_data]
pydantic_flat_objects = [PydanticUser(**d) for d in flat_test_data]


def create_nested_data(num_orders, items_per_order):
    data = []
    for i in range(num_orders):
        items_data = [
            {"product_id": j, "name": f"P{j}", "price": 10.0 + j, "quantity": 1} for j in range(items_per_order)
        ]
        data.append(
            {
                "order_id": i + 5000,
                "customer_name": f"Client {i}",
                "items": items_data,
                "is_shipped": (i % 3 == 0),
                "details": {"region": "East"},
            }
        )
    return data


nested_test_data = create_nested_data(NUM_RECORDS, ITEMS_PER_ORDER)
msgspec_nested_objects = [Order(**d) for d in nested_test_data]
pydantic_nested_objects = [PydanticOrder(**d) for d in nested_test_data]


def create_failure_test_data(num_records):
    # 1. Unknown Fields
    data_unknown = create_flat_data(num_records)
    for d in data_unknown:
        d["extra_field_for_fail"] = "should fail Pydantic/Msgspec"

    # 2. Coercion Data
    data_coercion = create_flat_data(num_records)
    for d in data_coercion:
        d["id"] = str(d["id"])
        d["is_active"] = str(d["is_active"])

    # 3. Invalid Data
    data_invalid = create_flat_data(num_records)
    for d in data_invalid:
        d["id"] = "not_an_int"
    return data_unknown, data_coercion, data_invalid


data_unknown, data_coercion, data_invalid = create_failure_test_data(NUM_RECORDS)
print(f"✅ Создано {NUM_RECORDS} плоских записей и {NUM_RECORDS} вложенных заказов для теста.")

# --- 4. Функции Бенчмарка (Обновлена логика для orjson) ---


def bench_encode(objects: List[Any], lib_type: str, model_type: Any) -> List[bytes]:
    if lib_type == "msgspec":
        return [msgspec.json.encode(obj) for obj in objects]
    if lib_type == "pydantic":
        return [obj.model_dump_json().encode("utf-8") for obj in objects]
    if lib_type == "json":
        return [json.dumps(d).encode("utf-8") for d in objects]
    if lib_type == "orjson":
        # orjson требует, чтобы входные данные были словарем (dict) или pydantic/dataclass
        return [orjson.dumps(d) for d in objects]
    raise ValueError(f"Неизвестный тип библиотеки: {lib_type}")


def bench_decode(json_list: List[bytes], lib_type: str, model_class: Any, perform_coercion: bool = False) -> List[Any]:
    results = []

    # Специальная логика для Msgspec (Coercion)
    if lib_type == "msgspec" and perform_coercion:
        # Сценарий Coercion: JSON -> Dict (msgspec decode dict) -> Coercion (Python) -> MsgspecUser
        for j in json_list:
            # 1. Std Json Decode (используем msgspec для быстрого декода в dict)
            data_dict = msgspec.json.decode(j)  # TODO why type=dict = +200ms

            # 2. Manual Coercion (имитация pydantic)
            data_dict["id"] = int(data_dict["id"])
            data_dict["is_active"] = data_dict["is_active"].lower() == "true"

            # 3. Msgspec Struct Creation
            obj = model_class(**data_dict)

            # 4. Custom Validation
            if model_class == MsgspecUser:
                obj.validate_code
            results.append(obj)
        return results

    # Основная логика для Decode
    if lib_type == "msgspec":
        if model_class == MsgspecUser:
            for j in json_list:
                obj = msgspec.json.decode(j, type=model_class)
                obj.validate_code
                results.append(obj)
        else:
            results = [msgspec.json.decode(j, type=model_class) for j in json_list]
        return results

    if lib_type == "pydantic":
        return [model_class.model_validate_json(j) for j in json_list]

    if lib_type == "json":
        return [json.loads(j) for j in json_list]

    if lib_type == "orjson":
        return [orjson.loads(j) for j in json_list]

    return results


def bench_decode_error(json_list: List[bytes], lib_type: str, model_class: Any) -> bool:
    if lib_type == "msgspec":
        for j in json_list:
            try:
                msgspec.json.decode(j, type=model_class)
            except (DecodeError, TypeError):
                pass
        return True

    if lib_type == "pydantic":
        for j in json_list:
            try:
                model_class.model_validate_json(j)
            except ValidationError:
                pass
        return True

    return False


# Предварительная сериализация
msgspec_flat_json = bench_encode(msgspec_flat_objects, "msgspec", MsgspecUser)
pydantic_flat_json = bench_encode(pydantic_flat_objects, "pydantic", PydanticUser)
std_flat_json = bench_encode(flat_test_data, "json", dict)

msgspec_nested_json = bench_encode(msgspec_nested_objects, "msgspec", Order)
pydantic_nested_json = bench_encode(pydantic_nested_objects, "pydantic", PydanticOrder)
std_nested_json = bench_encode(nested_test_data, "json", dict)

# Предварительная сериализация для тестов отказа/coercion
json_unknown = bench_encode(data_unknown, "json", dict)
json_coercion = bench_encode(data_coercion, "json", dict)
json_invalid = bench_encode(data_invalid, "json", dict)


# --- 5. Запуск Бенчмарка и Сбор Результатов (ОБНОВЛЕННЫЙ МОДУЛЬ) ---


def run_test(test_func: Callable, label: str) -> Tuple[str, float]:
    """Запускает один тест и возвращает метку и время в мс."""
    total_time = timeit.timeit(test_func, number=NUMBER)
    avg_time_ms = (total_time / NUMBER) * 1000
    return label, avg_time_ms


def run_bench_group(label: str, tests: List[Tuple[Callable, str]]) -> Dict[str, float]:
    """Запускает группу тестов и возвращает словарь результатов."""
    print(f"Запуск: {label}...")
    group_results = {}
    for test_func, test_label in tests:
        _, time_ms = run_test(test_func, test_label)
        group_results[test_label] = time_ms
    return group_results


# 5.1. Плоская структура (Encode/Decode)
flat_results = {}

# Сериализация (Encode)
flat_results["Encode"] = run_bench_group(
    "Плоская Encode",
    [
        (lambda: bench_encode(msgspec_flat_objects, "msgspec", MsgspecUser), "Msgspec (Плоская Encode)"),
        (lambda: bench_encode(pydantic_flat_objects, "pydantic", PydanticUser), "Pydantic (Плоская Encode)"),
        (lambda: bench_encode(flat_test_data, "json", dict), "Std Json (Плоская Dict Encode)"),
        (lambda: bench_encode(flat_test_data, "orjson", dict), "Orjson (Плоская Dict Encode)"),
    ],
)

# Десериализация (Decode + Custom Val)
flat_results["Decode"] = run_bench_group(
    "Плоская Decode + Custom Val",
    [
        (lambda: bench_decode(msgspec_flat_json, "msgspec", MsgspecUser), "Msgspec (Плоская Decode + Custom Val)"),
        (lambda: bench_decode(pydantic_flat_json, "pydantic", PydanticUser), "Pydantic (Плоская Decode + Custom Val)"),
        (lambda: bench_decode(std_flat_json, "json", dict), "Std Json (Плоская Decode to Dict)"),
        (lambda: bench_decode(std_flat_json, "orjson", dict), "Orjson (Плоская Decode to Dict)"),
    ],
)


# 5.2. Вложенная структура (Encode/Decode)
nested_results = {}

# Сериализация (Encode)
nested_results["Encode"] = run_bench_group(
    "Вложенная Encode",
    [
        (lambda: bench_encode(msgspec_nested_objects, "msgspec", Order), "Msgspec (Вложенная Encode)"),
        (lambda: bench_encode(pydantic_nested_objects, "pydantic", PydanticOrder), "Pydantic (Вложенная Encode)"),
        (lambda: bench_encode(nested_test_data, "json", dict), "Std Json (Вложенная Dict Encode)"),
        # orjson для вложенной структуры
        (lambda: bench_encode(nested_test_data, "orjson", dict), "Orjson (Вложенная Dict Encode)"),
    ],
)

# Десериализация (Decode + Val)
nested_results["Decode"] = run_bench_group(
    "Вложенная Decode + Val",
    [
        (lambda: bench_decode(msgspec_nested_json, "msgspec", Order), "Msgspec (Вложенная Decode + Val)"),
        (lambda: bench_decode(pydantic_nested_json, "pydantic", PydanticOrder), "Pydantic (Вложенная Decode + Val)"),
        (lambda: bench_decode(std_nested_json, "json", dict), "Std Json (Вложенная Decode to Dict)"),
        # orjson для вложенной структуры
        (lambda: bench_decode(std_nested_json, "orjson", dict), "Orjson (Вложенная Decode to Dict)"),
    ],
)


# 5.3. Тесты отказа и Coercion
special_results = run_bench_group(
    "Тесты Отказа и Coercion",
    [
        # E1. Обработка Лишних Полей (Unknown Field)
        (lambda: bench_decode_error(json_unknown, "pydantic", PydanticUser), "Pydantic (Fail - Unknown Field)"),
        (lambda: bench_decode_error(json_unknown, "msgspec", MsgspecUser), "Msgspec (Fail - Unknown Field)"),
        # E2. Приведение Типов (Coercion)
        (lambda: bench_decode(json_coercion, "pydantic", PydanticUser), "Pydantic (Success - Coercion)"),
        (
            lambda: bench_decode(json_coercion, "msgspec", MsgspecUser, perform_coercion=True),
            "Msgspec (Success - Coercion, MANUAL)",
        ),
        # E3. Обработка Ошибок Типа (Invalid Data)
        (lambda: bench_decode_error(json_invalid, "pydantic", PydanticUser), "Pydantic (Fail - Invalid Data)"),
        (lambda: bench_decode_error(json_invalid, "msgspec", MsgspecUser), "Msgspec (Fail - Invalid Data)"),
    ],
)

# --- 6. Форматирование и Печать Результатов (ОБНОВЛЕННАЯ ЛОГИКА) ---

def format_results_for_print(
    flat_res: Dict, nested_res: Dict, special_results: Dict[str, float]
) -> List[Tuple[str, float]]:
    """Преобразует структурированные словари обратно в плоский список для печати."""
    all_results = []

    # Плоская структура
    for label, time_ms in flat_res["Encode"].items():
        all_results.append((label, time_ms))
    for label, time_ms in flat_res["Decode"].items():
        all_results.append((label, time_ms))

    # Вложенная структура
    for label, time_ms in nested_res["Encode"].items():
        all_results.append((label, time_ms))
    for label, time_ms in nested_res["Decode"].items():
        all_results.append((label, time_ms))

    # Специальные тесты
    for label, time_ms in special_results.items():
        all_results.append((label, time_ms))

    return all_results


def print_structured_results(flat_res: Dict, nested_res: Dict, spec_res: Dict):
    """Выводит результаты из структурированных словарей."""

    # Объединяем все метки для определения ширины
    all_labels = list(flat_res["Encode"].keys()) + list(nested_res["Encode"].keys()) + list(spec_res.keys())
    max_label_width = max(len(label) for label in all_labels)
    total_width = max_label_width + 19

    def print_separator(header=None):
        if header:
            print(f"| {header:<{total_width - 3}} |")
        print("-" * total_width)

    def print_group(group_data: Dict[str, float]):
        for label, time_ms in group_data.items():
            print(f"| {label:<{max_label_width + 2}} | {time_ms:>10.4f} |")

    print("\n" + "=" * total_width)
    print("📊 КОМПЛЕКСНЫЙ БЕНЧМАРК: Скорость, Вложенность, Валидация, Ошибки")
    print("=" * total_width)
    print(f"{'| Операция':<{max_label_width + 2}} | {'Время (мс)':>10} |")

    # 1. ПЛОСКАЯ СТРУКТУРА
    print_separator("*** ПЛОСКАЯ СТРУКТУРА (Flat) - С CUSTOM VAL ***")
    print_separator("--- СЕРИАЛИЗАЦИЯ (Encode) ---")
    print_group(flat_res["Encode"])
    print_separator()
    print_separator("--- ДЕСЕРИАЛИЗАЦИЯ (Decode + Custom Val) ---")
    print_group(flat_res["Decode"])

    # 2. ВЛОЖЕННАЯ СТРУКТУРА
    print_separator("*** ВЛОЖЕННАЯ СТРУКТУРА (Nested) ***")
    print_separator("--- СЕРИАЛИЗАЦИЯ (Encode) ---")
    print_group(nested_res["Encode"])
    print_separator()
    print_separator("--- ДЕСЕРИАЛИЗАЦИЯ (Decode + Val) ---")
    print_group(nested_res["Decode"])

    # 3. ТЕСТЫ ОТКАЗА И COERCION
    print("=" * total_width)
    print_separator("*** ТЕСТЫ ОТКАЗА И COERCION (Flat Data) ***")
    print_separator("--- ТЕСТЫ С ОШИБКАМИ И COERCION ---")
    print_group(spec_res)
    print("=" * total_width)


# Вывод результатов
print_structured_results(flat_results, nested_results, special_results)

# --- 7. Анализ (Обновлен для работы со словарями) ---


def get_time_from_dict(res_dict: Dict, target_label: str) -> float:
    """
    Извлекает время по метке из словаря результатов.
    Обрабатывает одноуровневую вложенность (как в flat_results или nested_results)
    или простую структуру (как в special_results).
    """

    # Сценарий A: Прямой поиск (как в special_results)
    if target_label in res_dict:
        return res_dict[target_label]

    # Сценарий B: Поиск во вложенных группах (как в flat_results или nested_results)
    for sub_dict in res_dict.values():
        # Убеждаемся, что это словарь, а не какое-то другое значение
        if isinstance(sub_dict, dict) and target_label in sub_dict:
            return sub_dict[target_label]

    # Если не найдено
    # print(f"!!! Ошибка: Метка '{target_label}' не найдена в словаре.")
    return 1.0


# Извлекаем времена
pydantic_coercion_time = get_time_from_dict(special_results, "Pydantic (Success - Coercion)")
msgspec_manual_coercion_time = get_time_from_dict(special_results, "Msgspec (Success - Coercion, MANUAL)")
pydantic_custom_val_time = get_time_from_dict(flat_results, "Pydantic (Плоская Decode + Custom Val)")

pydantic_fail_unknown = get_time_from_dict(special_results, "Pydantic (Fail - Unknown Field)")
msgspec_fail_unknown = get_time_from_dict(special_results, "Msgspec (Fail - Unknown Field)")
pydantic_fail_invalid = get_time_from_dict(special_results, "Pydantic (Fail - Invalid Data)")
msgspec_fail_invalid = get_time_from_dict(special_results, "Msgspec (Fail - Invalid Data)")

print("\n🔥 АНАЛИЗ СПЕЦИФИЧЕСКИХ СЦЕНАРИЕВ:")
print("-" * 65)

# A. Тест на Coercion
print("| 1. Сравнение Coercion (Приведение Типов):")
print(f"|   Pydantic (Автоматический Coercion): {pydantic_coercion_time:.4f} мс")
print(f"|   Msgspec (Ручной Coercion + Std Json Decode): {msgspec_manual_coercion_time:.4f} мс")
print(f"|   Pydantic Custom Val (для сравнения): {pydantic_custom_val_time:.4f} мс")
print("-" * 65)
if msgspec_manual_coercion_time > pydantic_coercion_time:
    overhead_ratio = msgspec_manual_coercion_time / pydantic_coercion_time
    print(f"|   Вывод: Автоматический Coercion Pydantic в {overhead_ratio:.2f}x быстрее, чем ручной подход Msgspec.")
else:
    print(
        f"|   Вывод: Ручной Coercion оказался неожиданно быстрым (Pydantic / Msgspec: {pydantic_coercion_time / msgspec_manual_coercion_time:.2f}x)."
    )

# B. Тест на Ошибки (Unknown Field)
print("-" * 65)
print("| 2. Сравнение Обработки Ошибки (Лишнее Поле):")
print(f"|   Msgspec (Fail - Unknown Field): {msgspec_fail_unknown:.4f} мс")
print(f"|   Pydantic (Fail - Unknown Field): {pydantic_fail_unknown:.4f} мс")
if msgspec_fail_unknown < pydantic_fail_unknown:
    print(
        f"|   Вывод: Msgspec быстрее обрабатывает ошибку 'лишнее поле' (в {pydantic_fail_unknown / msgspec_fail_unknown:.2f}x)."
    )
else:
    print("|   Вывод: Pydantic быстрее обрабатывает ошибку 'лишнее поле'.")

# C. Тест на Ошибки (Invalid Data Type)
print("-" * 65)
print("| 3. Сравнение Обработки Ошибки (Неверный Тип Данных):")
print(f"|   Msgspec (Fail - Invalid Data): {msgspec_fail_invalid:.4f} мс")
print(f"|   Pydantic (Fail - Invalid Data): {pydantic_fail_invalid:.4f} мс")
if msgspec_fail_invalid < pydantic_fail_invalid:
    print(
        f"|   Вывод: Msgspec быстрее обрабатывает ошибку 'неверный тип' (в {pydantic_fail_invalid / msgspec_fail_invalid:.2f}x)."
    )
else:
    print("|   Вывод: Pydantic быстрее обрабатывает ошибку 'неверный тип'.")
print("-" * 65)
