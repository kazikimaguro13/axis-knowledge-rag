.PHONY: eval eval-update-baseline lint test

eval:
	python -m evaluation.run_ragas \
		--dataset evaluation/datasets/qa_v1.json \
		--baseline evaluation/baseline.json \
		--output evaluation/runs/local-$$(date +%Y%m%d-%H%M).json

eval-update-baseline:
	python -m evaluation.run_ragas \
		--dataset evaluation/datasets/qa_v1.json \
		--baseline evaluation/baseline.json \
		--output evaluation/runs/local-$$(date +%Y%m%d-%H%M).json \
		--update-baseline

lint:
	ruff check .

test:
	pytest
