FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HALLENTINDER_PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY hallentinder ./hallentinder

RUN useradd --create-home --uid 10001 hallentinder
USER hallentinder

EXPOSE 8080
CMD ["python", "-m", "hallentinder.main"]
