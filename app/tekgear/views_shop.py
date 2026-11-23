import uuid

from flask import (Blueprint, abort, current_app, render_template, request,
                   session)

from .issuer import MESSAGES, digits_only, mask_pan

bp = Blueprint("shop", __name__)


def client_ip():
    """Leftmost X-Forwarded-For entry when present, else the peer address.

    Display only. XFF is attacker-controllable, and whether to trust it is
    precisely the question the WAF in front of this app exists to answer.
    """
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def products():
    return current_app.config["PRODUCTS"]


@bp.get("/healthz")
def healthz():
    return {"status": "ok", "instance": current_app.config["INSTANCE_NAME"]}


@bp.get("/")
def index():
    return render_template("index.html", products=products())


@bp.get("/product/<sku>")
def product(sku):
    for item in products():
        if item["sku"] == sku:
            return render_template("product.html", product=item)
    abort(404)


@bp.get("/checkout")
def checkout_form():
    session.setdefault("sid", uuid.uuid4().hex)
    sku = request.args.get("sku")
    selected = next((p for p in products() if p["sku"] == sku), products()[0])
    return render_template("checkout.html", product=selected)


@bp.post("/checkout")
def checkout_submit():
    issuer = current_app.config["ISSUER"]
    telemetry = current_app.config["TELEMETRY"]

    pan = digits_only(request.form.get("card_number"))
    approved, code = issuer.authorize(
        pan,
        request.form.get("exp_month", ""),
        request.form.get("exp_year", ""),
        request.form.get("cvv", ""),
    )

    telemetry.record(
        pan=pan,
        masked=mask_pan(pan),
        approved=approved,
        code=code,
        client_ip=client_ip(),
        user_agent=request.headers.get("User-Agent", ""),
        session_id=session.get("sid"),
    )

    # Both outcomes return 200. Real payment pages do, and differentiating by
    # status code would hand defenders an easy mitigation that sidesteps the
    # bot-detection story this lab exists to tell.
    return render_template(
        "result.html",
        approved=approved,
        code=code,
        message=MESSAGES.get(code, "Declined"),
        masked=mask_pan(pan),
        order_ref=uuid.uuid4().hex[:10].upper() if approved else None,
    )
