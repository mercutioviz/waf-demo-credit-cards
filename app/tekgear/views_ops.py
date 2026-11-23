import queue

from flask import (Blueprint, Response, current_app, jsonify, render_template,
                   stream_with_context)

KEEPALIVE_SECONDS = 15

bp = Blueprint("ops", __name__)


@bp.get("/ops")
def dashboard():
    return render_template("ops.html", instance=current_app.config["INSTANCE_NAME"])


@bp.get("/ops/snapshot")
def snapshot():
    return jsonify(current_app.config["TELEMETRY"].snapshot())


@bp.post("/ops/reset")
def reset():
    current_app.config["TELEMETRY"].reset()
    return jsonify({"status": "reset"})


@bp.get("/ops/stream")
def stream():
    telemetry = current_app.config["TELEMETRY"]
    channel = telemetry.subscribe()

    def events():
        try:
            while True:
                try:
                    message = channel.get(timeout=KEEPALIVE_SECONDS)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {message}\n\n"
        finally:
            telemetry.unsubscribe(channel)

    return Response(
        stream_with_context(events()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
