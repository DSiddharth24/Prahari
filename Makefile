.PHONY: dev test demo-data lint

dev:
	@echo "Starting Prahari Backend on http://localhost:8000 ..."
	@echo "Note: Frontend is hosted separately on http://localhost:5173 by teammate 3."
	uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest backend/api backend/reporting backend/demo_data -q

lint:
	ruff check backend

demo-data:
	python -m backend.demo_data.generate --seed 42 --out demo.json
