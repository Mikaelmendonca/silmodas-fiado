.PHONY: install run seed test lint fmt alerts

install:  ## cria o venv e instala tudo
	python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"

run:  ## painel + alertas diários em http://localhost:8000
	python -m fiado

seed:  ## dados de exemplo
	python -m fiado seed

alerts:  ## envia os alertas de hoje e sai (bom para cron)
	python -m fiado alerts

test:  ## testes + cobertura (falha abaixo de 95%)
	pytest

lint:  ## lint, formatação e tipos, o mesmo que o CI roda
	ruff check . && ruff format --check . && mypy

fmt:  ## corrige formatação e imports
	ruff check . --fix && ruff format .
