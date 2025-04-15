FROM python:alpine@sha256:18159b2be11db91f84b8f8f655cd860f805dbd9e49a583ddaac8ab39bf4fe1a7

WORKDIR /app

COPY node_simulator.py .
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Arguments for node configuration
ARG NODE_ID=0
ARG NODE_NAME=node-simulator
ARG CPU_CORES=4
ARG NODE_TYPE=worker
ARG API_SERVER=http://host.docker.internal:5000

ENV NODE_ID=$NODE_ID
ENV NODE_NAME=$NODE_NAME
ENV CPU_CORES=$CPU_CORES
ENV NODE_TYPE=$NODE_TYPE
ENV API_SERVER=$API_SERVER

EXPOSE 5000

CMD ["python", "node_simulator.py"]