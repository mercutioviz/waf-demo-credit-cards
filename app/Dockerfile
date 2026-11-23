FROM python:3.12-slim

WORKDIR /srv

COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/tekgear/ ./tekgear/
COPY brand/ ./tekgear/static/brand/

EXPOSE 5000

# One worker, many threads. Telemetry lives in process memory, so a second
# worker would split the counters and silently desync the /ops dashboard
# halfway through a demo.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "32", \
     "--access-logfile", "-", "tekgear:create_app()"]
