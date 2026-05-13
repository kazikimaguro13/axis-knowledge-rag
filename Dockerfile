FROM python:3.11-slim

# System deps (chromadb wants libstdc++, sqlite3)
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libstdc++6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
COPY backend ./backend
COPY scripts ./scripts
COPY examples ./examples
COPY config.yml ./
COPY streamlit_app.py ./

RUN pip install --no-cache-dir -e .

EXPOSE 8501

# 起動時に index をビルドしてから streamlit 起動
CMD ["sh", "-c", "python -m scripts.build_index ./examples/knowledge && streamlit run streamlit_app.py --server.address=0.0.0.0 --server.port=8501"]
