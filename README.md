# Kube-9: A Distributed Systems Cluster Simulation Framework (Kubernetes Clone)

Kube-9 is a lightweight Kubernetes-like system designed to simulate container orchestration, node management, and pod scheduling. It provides APIs for managing nodes, pods, and their associated resources, with Docker integration for container management.

---

## Features

1. **Node Management**: Add, update, and monitor worker and master nodes, each running as a Docker container to simulate physical nodes.
2. **Pod Management**: Create, delete, and monitor pods with containers, volumes, and configurations.
3. **Docker Integration**: Automatically manage Docker containers, networks, and volumes for both nodes and pods.
4. **Pod Tracking**: Each node maintains an array of pod IDs it hosts to simulate pod deployment.
5. **Health Monitoring**: Monitor node and pod health with heartbeat mechanisms sent from node containers.
6. **Node Recovery**: Attempt recovery of failed nodes by restarting their containers.
7. **Pod Rescheduling**: Automatically reschedule pods from failed nodes to healthy ones.

---

## Architecture Overview

Kube-9 simulates a Kubernetes-like cluster with these components:

1. **API Server**: Central management point for the cluster (runs in the main application)
2. **Node Manager**: Handles node registration, health monitoring, and management
3. **Pod Scheduler**: Places pods on appropriate nodes based on resource requirements
4. **Health Monitor**: Tracks node health through heartbeats and detects failures
5. **Node Containers**: Docker containers that simulate physical nodes in the cluster
6. **Pods**: Represented as entries in node pod arrays and as Docker containers

Each node in the cluster is represented by a Docker container running the node simulator, which:

- Maintains its own array of pod IDs
- Periodically sends heartbeats to the API server
- Reports its resource usage and status
- Receives instructions to add/remove pods

---

## Pod Scheduling Algorithms

Kube-9 uses the Best-Fit scheduling algorithm which places pods on nodes with the least available resources that still meet the pod's requirements. This maximizes cluster utilization by filling nodes more efficiently.

When creating pods, the system will:

1. Find all eligible nodes that have sufficient CPU resources and are healthy
2. Select the node with the minimum available CPU resources (Best-Fit)
3. If no eligible node is found, the pod creation will fail

---

## Prerequisites

- Python 3.12
- Docker installed and running
- PostgreSQL or MySQL database
- Required Python libraries (see `requirements.txt`)

---

## Installation

1. Clone the repository:

   ```bash
   git clone https://github.com/Achlys2004/PES2UG22CS011_PES2UG22CS003_PES2UG22CS042_PES2UG22CS027_Kubernetes_Mimic.git

   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Configure the database in `config.py`.

4. Create the database:

   ```sql
   CREATE DATABASE cluster_db;
   ```

5. Initialize and apply database migrations:
   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

#### Note: To redo the flask-migrate

```
# Remove the migrations folder
rm -r migrations

# Reset the database tracking table
mysql -u <user> -p cluster_db -e "DROP TABLE IF EXISTS alembic_version;"

# Reinitialize migrations
flask db init

# Create a new baseline migration
flask db migrate -m "Reset migration baseline"

# Apply the migration
flask db upgrade
```

---

## Running the Application

1. Start the application:

   ```bash
   python app.py
   open a new terminal and run:
   streamlit run dashboard.py
   ```

2. Access the API at:
   ```
   http://localhost:5000/
   ```

---

## Testing the Application

### Using Postman

#### Node Operations

1. **Create a Worker Node**

   - **Method**: POST
   - **URL**: `http://localhost:5000/nodes/`
   - **Body**:
     ```json
     {
       "name": "worker-1",
       "cpu_cores_avail": 4,
       "node_type": "worker"
     }
     ```

2. **Create a Master Node**

   - **Method**: POST
   - **URL**: `http://localhost:5000/nodes/`
   - **Body**:
     ```json
     {
       "name": "master-1",
       "cpu_cores_avail": 8,
       "node_type": "master"
     }
     ```

3. **List All Nodes**

   - **Method**: GET
   - **URL**: `http://localhost:5000/nodes/`

4. **Get Node Details**

   - **Method**: GET
   - **URL**: `http://localhost:5000/nodes/1`
     _(Replace `1` with actual node ID)_

5. **Check Node Health**

   - **Method**: GET
   - **URL**: `http://localhost:5000/nodes/health`

6. **Delete Node**

   - **Method**: DELETE
   - **URL**: `http://localhost:5000/nodes/1`
     _(Replace `1` with actual node ID)_

7. **Simulate Node Failure**

   - **Method**: POST
   - **URL**: `http://localhost:5000/nodes/1/simulate/failure`
     _(Replace `1` with actual node ID)_

8. **Send Node Heartbeat**

   - **Method**: POST
   - **URL**: `http://localhost:5000/nodes/1/heartbeat`
   - **Body**:
     ```json
     {
       "pod_ids": [1, 2],
       "cpu_cores_avail": 2,
       "health_status": "healthy",
       "components": {
         "kubelet": "running",
         "container_runtime": "running",
         "kube_proxy": "running",
         "node_agent": "running"
       }
     }
     ```

#### Pod Operations

1. **Create a Simple Pod**

   - **Method**: POST
   - **URL**: `http://localhost:5000/pods/`
   - **Body**:
     ```json
     {
       "name": "nginx-pod",
       "cpu_cores_req": 1,
       "containers": [
         {
           "name": "nginx",
           "image": "nginx:latest",
           "cpu_req": 0.5,
           "memory_req": 256
         }
       ]
     }
     ```

2. **Create a Multi-Container Pod**

   - **Method**: POST
   - **URL**: `http://localhost:5000/pods/`
   - **Body**:
     ```json
     {
       "name": "web-app",
       "cpu_cores_req": 2,
       "containers": [
         {
           "name": "web",
           "image": "nginx:latest",
           "cpu_req": 1.0,
           "memory_req": 256
         },
         {
           "name": "cache",
           "image": "redis:latest",
           "cpu_req": 0.5,
           "memory_req": 128
         }
       ]
     }
     ```

3. **Create a Pod with Volumes and Config**

   - **Method**: POST
   - **URL**: `http://localhost:5000/pods/`
   - **Body**:
     ```json
     {
       "name": "web-app-config",
       "cpu_cores_req": 2,
       "containers": [
         {
           "name": "web",
           "image": "httpd:latest",
           "cpu_req": 1.0,
           "memory_req": 512,
           "command": "/bin/sh",
           "args": "-c 'httpd-foreground'"
         }
       ],
       "volumes": [
         {
           "name": "data-volume",
           "type": "emptyDir",
           "size": 1,
           "path": "/data"
         }
       ],
       "config": [
         {
           "name": "env-config",
           "type": "env",
           "key": "ENV_TYPE",
           "value": "production"
         },
         {
           "name": "secret-config",
           "type": "secret",
           "key": "API_KEY",
           "value": "secret123"
         }
       ]
     }
     ```

4. **List All Pods**

   - **Method**: GET
   - **URL**: `http://localhost:5000/pods/`

5. **Get Pod Details**

   - **Method**: GET
   - **URL**: `http://localhost:5000/pods/1`
     _(Replace `1` with actual pod ID)_

6. **Check Pod Health**

   - **Method**: GET
   - **URL**: `http://localhost:5000/pods/1/health`
     _(Replace `1` with actual pod ID)_

7. **Delete a Pod**

   - **Method**: DELETE
   - **URL**: `http://localhost:5000/pods/1`
     _(Replace `1` with actual pod ID)_

---

## Docker Integration

1. **Build the Node Simulator Image**:

   ```bash
   cd node_simulation
   docker build -t kube-node .
   ```

2. **Run Simulated Nodes**:

   ```bash
   docker run -d --name node1 -p 5001:5000 kube-node
   docker run -d --name node2 -p 5002:5000 kube-node
   docker run -d --name node3 -p 5003:5000 kube-node
   ```

3. **Verify Docker Resources**:

   - **Check Initial Health Status**:

     - **Method**: GET  
       **URL**: `http://localhost:5000/nodes/health`

   - **Send Test Heartbeat**:

     - **Method**: POST  
       **URL**: `http://localhost:5000/nodes/1/heartbeat`

   - **Check Node Details**:

     - **Method**: GET  
       **URL**: `http://localhost:5000/nodes/1`

   - **Check Running Containers**:

     ```bash
     docker ps
     ```

   - **Check Docker Networks**:

     ```bash
     docker network ls | grep pod-network
     ```

   - **Check Docker Volumes**:
     ```bash
     docker volume ls | grep pod
     ```

---

## Troubleshooting

1. **Database Connection Issues**:

   - Ensure the database is running and the credentials in `config.py` are correct.
   - Test the connection using:
     ```
     python app.py
     ```

2. **Docker Issues**:

   - Ensure Docker is running:
     ```bash
     docker info
     ```
   - Verify Python has permissions to access Docker:
     ```bash
     docker ps
     ```

3. **API Response Issues**:
   - Check the application logs for detailed error information.
   - Verify the JSON payload matches the expected format.

---

## Future Enhancements

1. **Services and Load Balancing**: Expose pods to other pods or external users through stable IPs or DNS names.
2. **Deployments for Scaling**: Add support for running multiple replicas of pods and scaling them up/down.
3. **Rolling Updates**: Enable application updates without downtime by gradually replacing pods.
4. **Dashboard UI**: Provide a visual interface to monitor and manage resources.
5. **Monitoring and Logging**: Add comprehensive metrics collection and log aggregation.
6. **Storage Classes**: Implement dynamic persistent volume provisioning with different storage options.

---

## License

This project is for educational purposes and is not intended for production use.
