.PHONY: eval eval-update-baseline eval-abtest lint test

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

eval-abtest:
	python -m evaluation.run_abtest \
		--dataset evaluation/datasets/qa_v1.json \
		--flag time_decay.enabled \
		--output evaluation/runs/abtest-$$(date +%Y%m%d-%H%M).json

lint:
	ruff check .

test:
	pytest
