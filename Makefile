.PHONY: up down build logs ps reset

# Compose v2 plugin where available, v1 binary otherwise.
COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

INSECURE_HOST := insecure.pay.democuda.org
SECURE_HOST   := secure.pay.democuda.org

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

# Zero both dashboards between demo runs. --resolve keeps the correct SNI and
# Host header while still connecting to the local Caddy.
reset:
	@curl -fsS -k -X POST "https://$(INSECURE_HOST)/ops/reset" \
	  --resolve "$(INSECURE_HOST):443:127.0.0.1" > /dev/null && echo "insecure: reset"
	@curl -fsS -X POST "http://$(SECURE_HOST):8081/ops/reset" \
	  --resolve "$(SECURE_HOST):8081:127.0.0.1" > /dev/null && echo "secure:   reset"
