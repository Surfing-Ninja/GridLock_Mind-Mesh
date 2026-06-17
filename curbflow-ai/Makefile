.PHONY: setup audit preprocess pfdi zones features graph train-deep train-ranker predict recommend db api web full test clean

setup:
	pip install -r requirements.txt -r requirements-ml.txt

audit:
	python scripts/run_data_audit.py

preprocess:
	python scripts/run_preprocess.py

pfdi:
	python scripts/run_pfdi_scoring.py

zones:
	python scripts/run_zone_build.py

features:
	python scripts/run_feature_build.py

graph:
	python scripts/run_graph_build.py

train-deep:
	python scripts/run_train_deep.py

train-ranker:
	python scripts/run_train_ranker.py

predict:
	python scripts/run_predict.py

recommend:
	python scripts/run_recommendations.py

db:
	python scripts/seed_demo_db.py

api:
	uvicorn apps.api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev

full:
	python scripts/run_full_pipeline.py

test:
	pytest

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache
