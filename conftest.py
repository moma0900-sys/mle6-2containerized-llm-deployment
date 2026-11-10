"""Keep unit tests independent of live-service settings before app imports."""

import os

os.environ.update(
    {
        "PYTHON_DOTENV_DISABLED": "1",
        "MODEL_PROVIDER": "dry",
        "GROQ_API_KEY": "",
        "GROQ_MODEL": "openai/gpt-oss-20b",
        "CACHE_TTL_SECONDS": "300",
        "MAX_CONCURRENT_REQUESTS": "4",
        "REQUEST_TIMEOUT_SECONDS": "30",
        "INPUT_USD_PER_MILLION_TOKENS": "0",
        "OUTPUT_USD_PER_MILLION_TOKENS": "0",
    }
)
