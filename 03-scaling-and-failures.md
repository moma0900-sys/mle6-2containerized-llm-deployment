# Scaling And Failure Diagnosis

A deployed service has to cope with many requests at once. When one instance is
not enough, you can **scale** the service: give it a bigger instance with more
CPU and memory (*vertical* scaling), or run more instances of the same
container behind one URL (*horizontal* scaling). **Autoscaling** adds or
removes instances automatically, based on a metric such as CPU usage.

In this lesson you read how the service could autoscale on Render and put the
local container under load. Then you cause two kinds of failure and learn to
tell them apart quickly: an outage where nothing answers, and a provider that
rejects every request while the service still looks healthy.

## Read The Autoscaling Example

Your service from lesson 02 runs on one Free instance, which keeps the exercise
predictable.
[`deployment/render.autoscaling.example.yaml`](deployment/render.autoscaling.example.yaml)
shows the paid autoscaling fields without enabling them accidentally. Render
autoscaling requires a Pro workspace and bills every active instance, so you do
not deploy it; no scaling change is needed for this lesson.

```yaml
services:
  - type: web
    name: mle-containerized-llm-service
    runtime: docker
    plan: pro
    healthCheckPath: /health
    scaling:
      minInstances: 1
      maxInstances: 3
      targetCPUPercent: 60
      targetMemoryPercent: 70
```

Compared with [`render.yaml`](render.yaml), autoscaling changes `plan: free` to
a paid instance plan and adds the `scaling` block, while the provider settings
stay the same:

- **`plan: pro`** sets the size of each instance. The workspace subscription
  and the service's `plan` are separate choices: autoscaling needs a Pro
  workspace, and `plan` decides how much CPU and memory every instance gets.
- **`minInstances: 1`** keeps at least one instance running at all times. There
  is no scale-to-zero, so the cold starts from lesson 02 disappear, and you pay
  for that instance even when nobody uses the service.
- **`maxInstances: 3`** caps how far Render scales out, and with it the cost.
- **`targetCPUPercent`** and **`targetMemoryPercent`** are the metrics Render
  watches. It adds instances when the average usage stays above these targets
  and removes them when it drops well below.

Consider what this service spends its time on. In live mode, each `/generate`
request mostly waits for the provider's answer, and the container does almost
no computing while it waits. Under heavy load, requests pile up and response
times rise while CPU stays low, so a CPU target may never trigger a new instance.
More instances also do not lift limits outside the container: every replica
calls the same provider with the same API key and quota, and each replica has
its own in-memory cache, so the cache hit rate drops as you add replicas.
Separate queue time from upstream time before you propose more replicas.

## Establish A Baseline

A **baseline** is a measurement of the healthy service that later runs are
compared against. In this lesson, you compare it with the outage and the
failing provider below. The load probe in [`scripts/load_test.py`](scripts/load_test.py) sends many
`/generate` requests at once and summarizes how the service coped. Use the
healthy dry-run container from lesson 01:

```bash
uv run python scripts/load_test.py --requests 30 --concurrency 6
```

- `--requests 30` sends 30 requests in total.
- `--concurrency 6` keeps at most six of them in flight **at the client**. That
  is separate from the API's own limit on concurrent upstream calls:
  `MAX_CONCURRENT_REQUESTS=4` lets at most four requests call the provider at
  once, so with six in flight, up to two wait in the service's queue.

Example output (timings vary by machine):

```text
requests=30 concurrency=6
throughput_rps=259.61
successful_requests=30
successful_throughput_rps=259.61
mean_latency_ms=6.40
p95_latency_ms=11.23
error_rate=0.00%
```

| Metric | What it measures |
|---|---|
| `throughput_rps` | All completed attempts per second, including failures. |
| `successful_requests` | Requests that received a 2xx response. |
| `successful_throughput_rps` | Only the 2xx responses per second. |
| `mean_latency_ms` | The average time per request. |
| `p95_latency_ms` | The time that 95% of requests stayed under. Unlike the mean, it shows how the slowest requests behave. With 30 attempts, it is the 29th latency in ascending order (the nearest-rank definition). |
| `error_rate` | The share of requests without a 2xx response. Connection failures count as errors rather than aborting the run. |

Expect `successful_requests=30` and `error_rate=0.00%`. Timings and request
rates depend on the machine. Both latency values include failed requests and
exclude time spent waiting for the probe's own concurrency limit.

This baseline is a reference point for your own machine, not a benchmark of
the model. The probe reuses three prompts, so after the first few requests
almost every answer comes from the cache. It measures a cache-heavy workload,
not raw model capacity, and dry-run timings are not live inference benchmarks.

## Reproduce An Outage

An **outage** means the service is completely unavailable: no request gets an
answer. Simulate one by stopping only the Compose service started for this
course and repeating the same probe, then restore the baseline:

```bash
docker compose stop api
uv run python scripts/load_test.py --requests 30 --concurrency 6
MODEL_PROVIDER=dry docker compose up --wait
```

When nothing is listening on port 8000, expect `successful_requests=0` and
`error_rate=100.00%`. The probe counts connection failures even though there
is no HTTP response. For example:

| API state | Successful requests | Error rate | p95 | Throughput |
|---|---:|---:|---:|---:|
| Running | 30 | 0% | 11.23 ms | 259.61 rps |
| Stopped | 0 | 100% | 1.35 ms | 823.75 rps |

The stopped service looks faster and busier because connections fail
immediately, and failed attempts still count as completed. A fast failure can
improve these timings without improving useful service, so always read the
latency and throughput next to `successful_requests` and `error_rate`. These
timings illustrate the trap; they are not performance targets. Verify
`/health` again before you continue.

## Diagnose A Failing Provider

In the outage, nothing answered. A harder case is a service that looks healthy
but cannot generate anything. Use the same image in a temporary container with
a dummy key that Groq rejects. This needs network access to Groq; the
in-process tests below reproduce the error mapping offline.

1. In one terminal, stop the Compose service and start the temporary container
   from the image it used. Plain `docker run` does not load your `.env`:

   ```bash
   docker compose stop api
   docker run --rm --pull=never -p 127.0.0.1:8000:8000 \
     -e MODEL_PROVIDER=groq -e GROQ_API_KEY=invalid-key \
     "$(docker compose images -q api)"
   ```

   Wait for Uvicorn to start. The key is not empty, so the app can start
   without checking whether the provider will accept it.

2. In a second terminal, send the checks from lesson 01:

   ```bash
   curl -i http://127.0.0.1:8000/health
   curl -i http://127.0.0.1:8000/ready
   curl -i -X POST http://127.0.0.1:8000/generate \
     -H "Content-Type: application/json" \
     -d '{"prompt":"Say hello."}'
   ```

   `/health` and `/ready` return HTTP 200, but `/generate` fails:

   ```text
   {"status":"healthy"}
   {"status":"ready","provider":"groq","model":"openai/gpt-oss-20b"}
   HTTP/1.1 502 Bad Gateway
   {"detail":"Generation provider unavailable"}
   ```

3. Run the load probe again from the second terminal:

   ```bash
   uv run python scripts/load_test.py --requests 30 --concurrency 6
   ```

   Example output (timings vary by machine and network):

   ```text
   requests=30 concurrency=6
   throughput_rps=70.41
   successful_requests=0
   successful_throughput_rps=0.00
   mean_latency_ms=70.63
   p95_latency_ms=133.58
   error_rate=100.00%
   ```

4. Look for the cause in the first terminal. Groq should reject the dummy key
   with an authentication error:

   ```text
   groq.AuthenticationError: Error code: 401 - ... Invalid API Key ...
   ```

5. Press **Ctrl+C** in the first terminal to stop and remove the temporary
   container. Start the dry-run Compose service again for the next lesson:

   ```bash
   MODEL_PROVIDER=dry docker compose up --wait
   ```

Both failures end with `error_rate=100.00%`, but the evidence differs. In the
outage, no request got an HTTP response, and each failed in about a
millisecond. Here, every request reached the API, the API reached Groq, and
Groq rejected it, which is why each failure took a network round trip. `/health`
and `/ready` passed because neither route calls the provider. The `502` body
does not expose the raw provider error to the client; only the logs show the
real cause.

## Failure Symptoms

The two failures show that the same error rate can have very different causes.
Use the symptom to decide what to inspect next:

| Symptom | What it means | Where to look |
|---|---|---|
| No HTTP response | Nothing is listening on the port. | `docker compose ps`, `docker compose logs api`, and the published port |
| `422` | The request body is invalid and was rejected before the provider. | The request body, before looking upstream |
| `502` | The provider call failed or returned no complete answer. | The service logs and the provider settings: key, model name, quota |
| `504` from the app | The deadline expired while the request waited for a slot or for the provider. | Queue time versus upstream time; `504` alone does not tell which |
| A timeout from a hosted proxy | The platform gave up, not the app. | Where the response originated |
| Instances restart repeatedly | The process crashed or ran out of memory. | The platform's exit reason and memory graph, before assuming an out-of-memory failure |

The existing in-process tests check the same `502` and `504` mapping without
Docker or provider credentials:

```bash
uv run pytest -q \
  tests/test_api.py::test_provider_errors_do_not_leak_details \
  tests/test_boundaries.py::test_deadline_covers_provider_and_queue
```

Expect four passing cases. The [API test](tests/test_api.py) replaces the
provider with one that raises an error: a generic failure becomes `502`, and a
timeout becomes `504`. The [deadline test](tests/test_boundaries.py) checks
that the service times out both while waiting for a slot and during generation.

## Check Your Understanding

1. Can a higher total request rate coexist with a complete outage?
2. A load test sends the same few prompts to an LLM API that caches
   responses. Why might its results look much better than what real users
   will experience?
3. Under load, your provider starts returning `429 Too Many Requests`. Why will
   adding more API replicas not help, and what would?

<details>
<summary>Show Reference Answers</summary>

1. Yes. Failed requests also complete; inspect successful throughput and error
   rate.
2. Most requests become cache hits that never reach the model, so the results
   reflect the cache, not inference. Real users send varied prompts, so more
   requests miss the cache, wait for the provider, and count against its rate
   limits. A realistic test uses varied prompts and the real provider.
3. Every replica calls the provider with the same API key, so they all share
   one rate limit; more replicas only send more requests and collect more
   `429`s. A higher provider limit or paid tier helps, and so does sending
   fewer upstream requests: caching repeated prompts, lowering the concurrency
   limit, or retrying with a growing delay between attempts.

</details>

## Further Reading

- [Scaling Render Services](https://render.com/docs/scaling)
