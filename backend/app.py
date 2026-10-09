import os

from flask import Flask, jsonify, send_from_directory

STATIC_DIR = os.environ.get(
    "STATIC_DIR",
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist", "frontend", "browser"),
)

app = Flask(__name__, static_folder=None)


@app.get("/api/hello")
def hello():
    return jsonify(message="Hello from Flask!")


@app.get("/", defaults={"path": ""})
@app.get("/<path:path>")
def frontend(path):
    # Serve built Angular files; fall back to index.html for client-side routes.
    if path and os.path.isfile(os.path.join(STATIC_DIR, path)):
        return send_from_directory(STATIC_DIR, path)
    return send_from_directory(STATIC_DIR, "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
