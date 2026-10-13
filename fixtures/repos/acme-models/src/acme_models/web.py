"""HTTP helpers. Needs the `web` extra (Flask); consumers that do not use it never import this module."""
from flask import Flask, jsonify

from .customer import CustomerRequest, to_payload


def make_app() -> Flask:
    app = Flask(__name__)

    @app.get("/customers/<int:customer_id>")
    def show(customer_id: int):
        req = CustomerRequest(customer_id=customer_id, email=f"user{customer_id}@example.com")
        return jsonify(to_payload(req))

    return app
