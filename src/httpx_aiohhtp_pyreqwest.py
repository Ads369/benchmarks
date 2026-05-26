import asyncio
import time
from contextlib import suppress
from datetime import timedelta

import aiohttp
import httpx
from pyreqwest.client import ClientBuilder
from zapros import AsyncClient as ZaprosAsyncClient
from zapros import AsyncPyreqwestHandler

# --- ПАРАМЕТРЫ ТЕСТА ---
CONCURRENCY = 200
TEST_URL = "https://httpbun.com/delay/0.5"
ITERATIONS = 5
# -------------------------


async def fetch_pyreqwest(client):
    """Задача для pyreqwest"""
    await client.get(TEST_URL).build().send()


async def fetch_httpx(client):
    """Задача для httpx"""
    await client.get(TEST_URL)


async def fetch_aiohttp(client):
    """Задача для aiohttp"""
    async with client.get(TEST_URL) as response:
        # aiohttp требует, чтобы вы прочитали ответ для закрытия соединения
        await response.read()


async def fetch_zapros(client):
    """Задача для zapros"""
    await client.get(TEST_URL)


async def run_benchmark(name, fetch_func, ClientClass, builder=False):
    """Запускает бенчмарк для одного клиента"""
    total_time = 0
    successful_requests = 0
    failed_requests = 0

    # Создание клиента (Session/Builder)
    if builder:
        # pyreqwest использует ClientBuilder
        client = ClientBuilder().build()
    elif ClientClass == aiohttp.ClientSession:
        # aiohttp Session
        client = ClientClass(timeout=aiohttp.ClientTimeout(total=30))
    elif ClientClass == ZaprosAsyncClient:
        # zapros поверх pyreqwest handler
        client = ClientClass(
            handler=AsyncPyreqwestHandler(
                ClientBuilder().timeout(timedelta(seconds=30))
            )
        )
    else:
        # httpx AsyncClient
        client = ClientClass(timeout=30.0)

    try:
        for _ in range(ITERATIONS):
            start_time = time.perf_counter()
            # Создание N асинхронных задач (Tasks)
            tasks = [fetch_func(client) for _ in range(CONCURRENCY)]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            end_time = time.perf_counter()
            total_time += end_time - start_time
            successful_requests += sum(
                not isinstance(result, Exception) for result in results
            )
            failed_requests += sum(isinstance(result, Exception) for result in results)

        avg_time = total_time / ITERATIONS
        rps = (successful_requests / ITERATIONS) / avg_time

        print(f"--- {name} ---")
        print(f"Среднее время выполнения: {avg_time:.4f} с")
        print(f"Средний RPS (Запросов/с): {rps:.2f}")
        print(f"Успешно/ошибок: {successful_requests}/{failed_requests}")

    finally:
        # Закрытие клиента/сессии
        with suppress(Exception):
            await client.close()
            await client.aclose()  # ty:ignore[possibly-missing-attribute]


async def main():
    print(f"--- Запуск Бенчмарка: {CONCURRENCY} одновременных запросов с задержкой 0.5с ---")

    # 1. pyreqwest
    await run_benchmark("pyreqwest", fetch_pyreqwest, ClientBuilder, builder=True)

    # 2. httpx
    await run_benchmark("httpx", fetch_httpx, httpx.AsyncClient)

    # 3. aiohttp
    await run_benchmark("aiohttp", fetch_aiohttp, aiohttp.ClientSession)

    # 4. zapros
    await run_benchmark("zapros", fetch_zapros, ZaprosAsyncClient)


if __name__ == "__main__":
    asyncio.run(main())
