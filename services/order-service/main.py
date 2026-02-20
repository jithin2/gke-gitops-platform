# Edit services/order-service/main.py — add a comment at the top of the file describing the service's purpose and functionality.
"""Order Service — handles order creation and retrieval."""

import os
import json
import uuid
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.getenv("PORT", "8081"))
PRODUCT_SERVICE_URL = os.getenv("PRODUCT_SERVICE_URL", "http://product-service:8082")

# In-memory store (would be Cloud SQL / Firestore in production)
orders: dict = {}


class OrderHandler(BaseHTTPRequestHandler):
    def _normalize_path(self):
        """Strip trailing slash to handle both /api/orders and /api/orders/."""
        return self.path.rstrip("/") or "/"

    def do_GET(self):
        path = self._normalize_path()
        if path == "/healthz":
            self._json_response(200, {"status": "healthy", "service": "order-service"})
        elif path == "/readyz":
            self._json_response(200, {"status": "ready"})
        elif path == "/api/orders":
            self._json_response(200, {"orders": list(orders.values()), "count": len(orders)})
        elif path.startswith("/api/orders/"):
            order_id = path.split("/")[-1]
            if order_id in orders:
                self._json_response(200, orders[order_id])
            else:
                self._json_response(404, {"error": "Order not found"})
        else:
            self._json_response(404, {"error": "Not found"})

    def do_POST(self):
        path = self._normalize_path()
        if path == "/api/orders":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length > 0 else b"{}"

            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_response(400, {"error": "Invalid JSON"})
                return

            order_id = str(uuid.uuid4())[:8]
            order = {
                "id": order_id,
                "product_id": data.get("product_id", "unknown"),
                "quantity": data.get("quantity", 1),
                "status": "created",
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            orders[order_id] = order
            self._json_response(201, order)
        else:
            self._json_response(404, {"error": "Not found"})

    def _json_response(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        """Structured logging."""
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "order-service",
            "method": args[0] if args else "",
            "path": args[1] if len(args) > 1 else "",
            "status": args[2] if len(args) > 2 else "",
        }))


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), OrderHandler)
    print(f"Order service starting on port {PORT}")
    server.serve_forever()
