import os

INSTANCE_NAME = os.environ.get("INSTANCE_NAME", "local")
LAB_SECRET = os.environ.get("LAB_SECRET", "dev-only-insecure-default")
LIVE_RATE = float(os.environ.get("LIVE_RATE", "2"))
