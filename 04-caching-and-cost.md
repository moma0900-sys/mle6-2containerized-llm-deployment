# Caching And Cost

Each request that reaches an LLM provider takes time, counts toward usage
limits, and can incur token charges. A cache stores answers the service has
already generated and returns them when the same request arrives again. In this
lesson you watch the service's cache at work, see how it reports token usage
and estimated cost, and work through a monthly cost estimate.

When the service finds a stored answer, that is a **cache hit**; when it has to
call the provider, that is a **cache miss**. This service uses an
**exact-match** cache: only a request with exactly the same parameters counts
as a hit. Each answer stays in the cache for a limited time, its **TTL** (time
to live), which is 300 seconds by default (`CACHE_TTL_SECONDS` in `.env`).

## Follow A Cache Miss And Hit

Use the dry-run service from lesson 01. Pick a prompt you have not used during
this run, and send it twice within the TTL:

```bash
for attempt in 1 2; do
  curl -sS http://127.0.0.1:8000/generate \
    -H "Content-Type: application/json" \
    -d '{"prompt":"Describe the cache experiment.","temperature":0.2}'
  printf '\n'
done
```

Expected output (your `latency_ms` values will differ):

```json
{"text":"Dry response: Describe the cache experiment.","model":"dry:openai/gpt-oss-20b","usage":{"input_tokens":4,"output_tokens":6},"cache_hit":false,"latency_ms":0.81,"estimated_cost_usd":0.0}
{"text":"Dry response: Describe the cache experiment.","model":"dry:openai/gpt-oss-20b","usage":{"input_tokens":4,"output_tokens":6},"cache_hit":true,"latency_ms":0.03,"estimated_cost_usd":0.0}
```

The first request is a miss, and the second is a hit. The second request
returns the stored text and its original token counts, but makes no new
provider call. `estimated_cost_usd` is zero on a hit; both responses show zero
here because the default prices are not configured. A faster second response is
useful evidence, but the `cache_hit` flag is the direct check.

The [cache key](src/deployment_service/cache.py) decides what counts as "the
same request". It hashes every parameter that can change the answer:

```python
raw = f"{model}:{request.temperature}:{request.max_tokens}:{request.prompt}"
return hashlib.sha256(raw.encode()).hexdigest()
```

Try the same request with `"temperature":0.5`: expect a miss if you have not
sent that combination. Temperature belongs in the key because it can change the
output, so an answer generated at one temperature must not be reused for
another.

The cache has limits worth knowing before you rely on it:

- **It lives in the process's memory.** Restarting the container clears it,
  and replicas do not share it.
- **It holds at most 1,024 entries.** When it is full, the oldest entry makes
  room for the new one.
- **Simultaneous misses are not merged.** Two identical requests that arrive at
  the same moment can both miss and call the provider twice.

## Exercise: Configure Token Prices

The service estimates the cost of each generation from per-million-token
prices in `.env`. Both prices default to `0`, which means "not configured", not
"free". Set illustrative prices and watch the estimate on a miss and a hit.

1. In `.env`, set illustrative prices of \$1 per million input tokens and \$3 per
   million output tokens:

   ```text
   INPUT_USD_PER_MILLION_TOKENS=1
   OUTPUT_USD_PER_MILLION_TOKENS=3
   ```

2. Restart the service in dry-run mode, so it picks up the new values:

   ```bash
   MODEL_PROVIDER=dry docker compose up --wait
   ```

3. Send the same prompt twice again:

   ```bash
   for attempt in 1 2; do
     curl -sS http://127.0.0.1:8000/generate \
       -H "Content-Type: application/json" \
       -d '{"prompt":"Describe the cache experiment.","temperature":0.2}'
     printf '\n'
   done
   ```

   Expected output (your `latency_ms` values will differ):

   ```json
   {"text":"Dry response: Describe the cache experiment.","model":"dry:openai/gpt-oss-20b","usage":{"input_tokens":4,"output_tokens":6},"cache_hit":false,"latency_ms":0.48,"estimated_cost_usd":0.000022}
   {"text":"Dry response: Describe the cache experiment.","model":"dry:openai/gpt-oss-20b","usage":{"input_tokens":4,"output_tokens":6},"cache_hit":true,"latency_ms":0.06,"estimated_cost_usd":0.0}
   ```

4. Set both prices back to `0` in `.env` and restart the service in dry-run
   mode again.

The first request is a miss again, even though you sent this prompt before:
the restart replaced the container and cleared its in-memory cache. Its
estimate follows directly from the token counts and the prices:

$$
\frac{4 \times 1 + 6 \times 3}{1{,}000{,}000} = \$0.000022
$$

The hit still reports the original token counts, because those tokens were
spent once to create the answer, but its incremental cost is zero. Keep in mind
that dry-run token counts are word counts, not measurements from a model's
tokenizer, and that the estimate is only as good as the prices you configure.
Provider prices change, so copy current rates from the provider's pricing page
before making a cost claim.

## Work Through A Cost Estimate

Separate fixed instance cost from variable provider cost. The instance cost is
what you pay to keep the service running: zero on the Free plan from lesson 02,
or a monthly price for every instance that stays up on a paid plan, such as
the `minInstances: 1` in lesson 03's autoscaling example.

Suppose a service handles 2,000 successful requests per month and 80% are cache
hits. That leaves 400 generations under this simplified assumption. With 100
input and 50 output tokens per generation, and **illustrative** prices of \$1
and \$3 per million tokens respectively:

$$
\text{provider cost} = 400 \times \frac{100 \times 1 + 50 \times 3}{1{,}000{,}000} = \$0.10
$$

$$
\text{total estimate} = \text{instance cost} + \text{provider cost}
$$

This is not a quote or bill. Measure real provider usage on a defined workload
and look up the relevant prices before using the estimate for a decision, and
always state the cache-hit rate you assumed.

## Clean Up

Once you have finished the lessons, stop the local service:

```bash
docker compose down
```

This stops and removes the Compose containers and network. The image remains
available for reuse. If your Render service from lesson 02 still exists,
delete it as described in its [Clean Up](02-render-deployment.md#clean-up)
section.

## Check Your Understanding

1. Does a cache hit imply that no tokens were used to create the answer?
2. Does a zero token-price setting make a live provider free?
3. Your provider bill is too high. Would adding a second replica or improving
   the cache-hit rate help more, and why?

<details>
<summary>Show Reference Answers</summary>

1. No. It avoids a new provider call; the original generation still used
   tokens.
2. No. Zero means no price is configured in the estimator, not that billing is
   disabled.
3. Improving the cache-hit rate. Every extra hit removes a provider call and
   its cost. A second replica adds instance cost, does not reduce provider
   usage, and splits the cache, so each replica misses more often.

</details>

## Further Reading

- [Render Pricing](https://render.com/pricing)
