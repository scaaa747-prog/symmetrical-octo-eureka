FROM python:3.10-slim

WORKDIR /app

COPY . /app

EXPOSE 3000

CMD ["python3", "server.py"]
