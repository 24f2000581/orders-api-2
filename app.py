from fastapi import FastAPI, Header, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import time
import uuid
import base64

app = FastAPI()

# --------------------------------------------------
# CORS
# --------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# Assignment Values
# --------------------------------------------------
TOTAL_ORDERS = 53
RATE_LIMIT = 19
WINDOW = 10  # seconds

# --------------------------------------------------
# In-memory Storage
# --------------------------------------------------
idempotency_store = {}
client_requests = {}

# --------------------------------------------------
# Rate Limiting Middleware
# --------------------------------------------------
@app.middleware("http")
async def rate_limit(request: Request, call_next):

    # Skip CORS preflight
    if request.method == "OPTIONS":
        return await call_next(request)

    if request.url.path == "/orders":
        client = request.headers.get("X-Client-Id", "anonymous")

        now = time.time()

        history = client_requests.get(client, [])

        # Remove expired requests
        history = [t for t in history if now - t < WINDOW]

        if len(history) >= RATE_LIMIT:
            retry = max(1, int(WINDOW - (now - history[0])))

            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry)}
            )

        history.append(now)
        client_requests[client] = history

    response = await call_next(request)
    return response

# --------------------------------------------------
# CORS Preflight
# --------------------------------------------------
@app.options("/orders")
def options_orders():
    return Response(status_code=200)

# --------------------------------------------------
# Cursor Helpers
# --------------------------------------------------
def encode_cursor(position: int):
    return base64.b64encode(str(position).encode()).decode()


def decode_cursor(cursor: str):
    try:
        return int(base64.b64decode(cursor).decode())
    except Exception:
        return 0

# --------------------------------------------------
# POST /orders
# --------------------------------------------------
@app.post("/orders", status_code=201)
def create_order(
    idempotency_key: str = Header(..., alias="Idempotency-Key")
):

    if idempotency_key in idempotency_store:
        return idempotency_store[idempotency_key]

    order = {
        "id": str(uuid.uuid4()),
        "status": "created"
    }

    idempotency_store[idempotency_key] = order

    return order

# --------------------------------------------------
# GET /orders
# --------------------------------------------------
@app.get("/orders")
def get_orders(limit: int = 10, cursor: str | None = None):

    if limit < 1:
        limit = 1

    start = 0

    if cursor:
        start = decode_cursor(cursor)

    end = min(start + limit, TOTAL_ORDERS)

    items = []

    for i in range(start + 1, end + 1):
        items.append({
            "id": i,
            "status": "ready"
        })

    next_cursor = None

    if end < TOTAL_ORDERS:
        next_cursor = encode_cursor(end)

    return {
        "items": items,
        "next_cursor": next_cursor
    }

# --------------------------------------------------
# Root
# --------------------------------------------------
@app.get("/")
def root():
    return {
        "message": "Orders API running"
    }

# --------------------------------------------------
# Health Check (optional)
# --------------------------------------------------
@app.get("/health")
def health():
    return {
        "status": "ok"
    }
