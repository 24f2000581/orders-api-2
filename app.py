from fastapi import FastAPI, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import uuid
import base64
import math

app = FastAPI()

# ==========================================================
# CORS
# ==========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Retry-After"],
)

# ==========================================================
# Assignment Values
# ==========================================================

TOTAL_ORDERS = 53
RATE_LIMIT = 19
WINDOW = 10

# ==========================================================
# In-memory Storage
# ==========================================================

idempotency_store = {}
client_requests = {}

# ==========================================================
# Rate Limiting Middleware
# ==========================================================

@app.middleware("http")
async def rate_limit(request: Request, call_next):

    # Allow all OPTIONS requests
    if request.method == "OPTIONS":
        return await call_next(request)

    if request.url.path == "/orders":

        client = request.headers.get("X-Client-Id")

        if client:

            now = time.time()

            history = client_requests.get(client, [])

            # Keep only requests in the last WINDOW seconds
            history = [
                t for t in history
                if now - t < WINDOW
            ]

            if len(history) >= RATE_LIMIT:

                retry_after = max(
                    1,
                    math.ceil(WINDOW - (now - history[0]))
                )

                response = JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded"
                    }
                )

                response.headers["Retry-After"] = str(retry_after)

                return response

            history.append(now)
            client_requests[client] = history

    response = await call_next(request)
    return response

# ==========================================================
# Catch-all OPTIONS Handler
# ==========================================================

@app.options("/{path:path}")
async def options_handler(path: str):
    return Response(status_code=200)

# ==========================================================
# Cursor Helpers
# ==========================================================

def encode_cursor(position: int) -> str:
    return base64.b64encode(
        str(position).encode()
    ).decode()


def decode_cursor(cursor: str) -> int:
    try:
        return int(
            base64.b64decode(cursor).decode()
        )
    except Exception:
        return 0

# ==========================================================
# POST /orders
# ==========================================================

@app.post("/orders")
async def create_order(
    idempotency_key: str | None = Header(
        default=None,
        alias="Idempotency-Key"
    )
):

    # Generate a key if none supplied
    if not idempotency_key:
        idempotency_key = str(uuid.uuid4())

    # Return existing order
    if idempotency_key in idempotency_store:

        return JSONResponse(
            status_code=200,
            content=idempotency_store[idempotency_key]
        )

    # Create new order
    order = {
        "id": str(uuid.uuid4()),
        "status": "created"
    }

    idempotency_store[idempotency_key] = order

    return JSONResponse(
        status_code=201,
        content=order
    )

# ==========================================================
# GET /orders
# ==========================================================

@app.get("/orders")
async def get_orders(
    limit: int = 10,
    cursor: str | None = None
):

    if limit < 1:
        limit = 1

    start = decode_cursor(cursor) if cursor else 0

    end = min(start + limit, TOTAL_ORDERS)

    items = []

    for i in range(start + 1, end + 1):
        items.append(
            {
                "id": i,
                "status": "ready"
            }
        )

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = encode_cursor(end)

    return {
        "items": items,
        "next_cursor": next_cursor
    }

# ==========================================================
# Root
# ==========================================================

@app.get("/")
@app.head("/")
async def root():
    return {
        "message": "Orders API running"
    }

# ==========================================================
# Health
# ==========================================================

@app.get("/health")
async def health():
    return {
        "status": "ok"
    }
