import os
import uvicorn
from app.main import app

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="LLM Optimization Proxy")
    parser.add_argument(
        "--seed-cache",
        action="store_true",
        help="Pre-populate the semantic cache on startup",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.seed_cache:
        os.environ["SEED_CACHE"] = "true"

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=False)
