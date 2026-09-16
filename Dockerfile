FROM python:3.12-slim
WORKDIR /app
COPY server.py index.html xlsx.full.min.js ./
COPY db/ ./db/
COPY cache/valuation/ ./cache/valuation/
ENV APP_DATA_DIR=/data DIVIDEND_QUOTE_CACHE=/data/quotes.json BIND=0.0.0.0
EXPOSE 8000
CMD ["python3", "server.py", "--port", "8000", "--no-open"]
