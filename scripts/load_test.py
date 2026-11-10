"""Run a small asynchronous load probe against a deployed endpoint."""

import argparse
import asyncio
import math
import statistics
import time

import httpx


def positive_int(value: str) -> int:
    """Parse a strictly positive command-line integer."""
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


async def send(client: httpx.AsyncClient, url: str, prompt: str) -> tuple[int, float]:
    """Send one request and return status plus elapsed milliseconds."""
    started = time.perf_counter()
    try:
        response = await client.post(
            f"{url.rstrip('/')}/generate", json={"prompt": prompt}
        )
        status = response.status_code
    except httpx.RequestError:
        status = 0  # A transport failure is still a failed load-test request.
    return status, (time.perf_counter() - started) * 1000


async def run(url: str, requests: int, concurrency: int) -> None:
    """Execute bounded requests and print throughput and latency percentiles."""
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(index: int, client: httpx.AsyncClient) -> tuple[int, float]:
        async with semaphore:
            return await send(client, url, f"Explain deployment check {index % 3}.")

    started = time.perf_counter()
    async with httpx.AsyncClient(timeout=60) as client:
        results = await asyncio.gather(*(bounded(i, client) for i in range(requests)))
    elapsed = time.perf_counter() - started
    latencies = sorted(latency for _, latency in results)
    p95_index = math.ceil(len(latencies) * 0.95) - 1
    errors = sum(not 200 <= status < 300 for status, _ in results)
    print(f"requests={requests} concurrency={concurrency}")
    print(f"throughput_rps={requests / elapsed:.2f}")
    print(f"successful_requests={requests - errors}")
    print(f"successful_throughput_rps={(requests - errors) / elapsed:.2f}")
    print(f"mean_latency_ms={statistics.mean(latencies):.2f}")
    print(f"p95_latency_ms={latencies[p95_index]:.2f}")
    print(f"error_rate={errors / requests:.2%}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe an LLM service endpoint.")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--requests", type=positive_int, default=20)
    parser.add_argument("--concurrency", type=positive_int, default=4)
    args = parser.parse_args()
    asyncio.run(run(args.url, args.requests, args.concurrency))


if __name__ == "__main__":
    main()
