.PHONY: setup audit preprocess pfdi zones features graph train-deep train-ranker predict recommend precompute-summaries db api web full test ci clean

setup:
	python -m pip install -r requirements.txt -r requirements-ml.txt

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

precompute-summaries:
	python scripts/precompute_zone_summaries.py

db:
	python scripts/seed_demo_db.py --rebuild
	python scripts/precompute_zone_summaries.py

api:
	python -m uvicorn apps.api.main:app --reload --port 8000

web:
	cd apps/web && npm run dev -- --port 3000

full:
	python scripts/run_full_pipeline.py

test:
	python -m pytest -q

ci:
	python -m pytest -q
	python scripts/run_full_pipeline.py --fast-demo --skip-deep

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf apps/web/.next || true
	find apps/web/.next -depth -mindepth 1 -exec rm -rf {} + 2>/dev/null || true
	rmdir apps/web/.next 2>/dev/null || true
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f -name ".DS_Store" -delete
