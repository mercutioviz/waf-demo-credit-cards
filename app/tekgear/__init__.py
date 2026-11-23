import json
import os
from pathlib import Path

from flask import Flask

from . import config
from .issuer import Issuer
from .telemetry import Telemetry

BRAND_DIR = Path(__file__).parent / "static" / "brand"


def create_app():
    app = Flask(__name__)

    # Regenerated every start: session cookies only exist so the dashboard can
    # show cards-per-session, and nothing is worth carrying across a restart.
    app.secret_key = os.urandom(32)

    with (BRAND_DIR / "products.json").open() as handle:
        app.config["PRODUCTS"] = json.load(handle)

    app.config["INSTANCE_NAME"] = config.INSTANCE_NAME
    app.config["ISSUER"] = Issuer(config.LAB_SECRET, config.LIVE_RATE)
    app.config["TELEMETRY"] = Telemetry()

    from .views_ops import bp as ops_bp
    from .views_shop import bp as shop_bp

    app.register_blueprint(shop_bp)
    app.register_blueprint(ops_bp)

    return app
