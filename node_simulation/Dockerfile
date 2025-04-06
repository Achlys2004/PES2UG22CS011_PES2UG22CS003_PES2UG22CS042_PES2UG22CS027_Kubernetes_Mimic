FROM python:3.10-slim

WORKDIR /app

COPY node_simulator.py .

RUN pip install flask requests

EXPOSE 5000

CMD ["python", "node_simulator.py"]
