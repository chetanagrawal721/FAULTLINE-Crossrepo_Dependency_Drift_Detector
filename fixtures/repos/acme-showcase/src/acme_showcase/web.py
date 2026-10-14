"""A small web app. Flask 2.2.2 imports werkzeug.urls.url_quote, which Werkzeug 3 removed."""
from flask import Flask, jsonify


def make_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app
