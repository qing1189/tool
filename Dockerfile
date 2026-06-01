FROM python:3.12-slim

WORKDIR /app

COPY toolbridge/ /app/toolbridge/

# Ensure Python output is sent straight to docker logs (no buffering)
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["python", "-m", "toolbridge"]
