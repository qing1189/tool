FROM python:3.12-slim

WORKDIR /app

COPY toolbridge/ /app/toolbridge/

# Config persistence volume
VOLUME /root/.toolbridge

EXPOSE 8080

CMD ["python", "-m", "toolbridge"]
