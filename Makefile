.PHONY: eval eval-update-baseline eval-abtest lint test feedback-report gap-report

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

# spec_047: render last-7d feedback activity as evaluation/feedback_reports/YYYY-WW.md
feedback-report:
	python -c "from backend.src.feedback import SqliteFeedbackStore; from evaluation.feedback_report import save_report_to_file; s = SqliteFeedbackStore(); print(save_report_to_file(s, days=7))"

# spec_048: render last-7d knowledge-gap events as evaluation/gap_reports/YYYY-WW.md
gap-report:
	python -c "from backend.src.gap_detection import SqliteGapStore; from evaluation.gap_report import save_report_to_file; s = SqliteGapStore(); print(save_report_to_file(s, days=7))"
