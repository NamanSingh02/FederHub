FROM python:3.11-slim

WORKDIR /app

COPY client/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY client/ml /app/ml
COPY client/grpc_weight_sender.py /app/grpc_weight_sender.py
COPY federated-engine /app/federated-engine

ENTRYPOINT ["python", "/app/ml/train.py"]
