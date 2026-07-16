FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY app/backend/requirements.txt /tmp/lab-builder-requirements.txt
RUN pip install --no-cache-dir -r /tmp/lab-builder-requirements.txt

COPY . /workspace
RUN mkdir -p /workspace/.local /workspace/artifacts/codex-runs

WORKDIR /workspace/app/backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
