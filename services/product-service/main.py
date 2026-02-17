"""Product Service — handles product catalog."""

import os
import json
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler

PORT = int(os.getenv("PORT", "8082"))

# Sample product catalog (would be Cloud Firestore / Cloud SQL in production)
PRODUCTS = {
    "prod-001": {"id": "prod-001", "name": "Kubernetes Handbook", "price": 49.99, "category": "books"},
    "prod-002": {"id": "prod-002", "name": "Cloud Sticker Pack", "price": 9.99, "category": "merch"},
    "prod-003": {"id": "prod-003", "name": "DevOps Toolkit", "price": 149.99, "category": "tools"},
    "prod-004": {"id": "prod-004", "name": "GitOps Workshop", "price": 299.99, "category": "training"},
}


class ProductHandler(BaseHTTPRequestHandler):
    def _normalize_path(self):
        """Strip trailing slash to handle both /api/products and /api/products/."""
        return self.path.rstrip("/") or "/"

    def do_GET(self):
        path = self._normalize_path()
        if path == "/healthz":
            self._json_response(200, {"status": "healthy", "service": "product-service"})
        elif path == "/readyz":
            self._json_response(200, {"status": "ready"})
        elif path == "/api/products":
            self._json_response(200, {
                "products": list(PRODUCTS.values()),
                "count": len(PRODUCTS),
            })
        elif path.startswith("/api/products/"):
            product_id = path.split("/")[-1]
            if product_id in PRODUCTS:
                self._json_response(200, PRODUCTS[product_id])
            else:
                self._json_response(404, {"error": "Product not found"})
        else:
            self._json_response(404, {"error": "Not found"})

    def _json_response(self, status_code: int, data: dict):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        print(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "service": "product-service",
            "method": args[0] if args else "",
            "path": args[1] if len(args) > 1 else "",
            "status": args[2] if len(args) > 2 else "",
        }))


if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), ProductHandler)
    print(f"Product service starting on port {PORT}")
    server.serve_forever()
