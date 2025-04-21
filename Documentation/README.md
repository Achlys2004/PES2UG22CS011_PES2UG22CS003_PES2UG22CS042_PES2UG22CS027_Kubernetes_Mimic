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
8. **Visual Dashboard**: Interactive Streamlit dashboard for monitoring and managing your cluster.

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
- MySQL database
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

3. Configure the database in `config.py`:

   ```python
   SQLALCHEMY_DATABASE_URI = 'mysql+pymysql://username:password@localhost/cluster_db'
   SQLALCHEMY_TRACK_MODIFICATIONS = False
   ```

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

#### Note: If you need to reset the database migrations

```bash
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

1. Start the main API server:

   ```bash
   python app.py
   ```

2. Start the dashboard in a separate terminal:

   ```bash
   streamlit run dashboard.py
   ```

3. Access the API at:

   ```
   http://localhost:5000/
   ```

4. Access the dashboard at:
   ```
   http://localhost:8501/
   ```

---

## Dashboard Features

The Kube-9 dashboard provides a visual interface to manage and monitor your cluster:

- **Overview**: View cluster statistics, resource utilization, and pod distribution
- **Nodes Management**: Monitor node health, view component status, and perform operations
- **Pods Management**: Track pod status, view container details, and manage deployments
- **Resource Creation**: Create new nodes and pods through a user-friendly interface
- **Health Monitoring**: Real-time health status with visual indicators
- **Auto-refresh**: Configurable auto-refresh to keep data current

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

4. **Create a Pod with Multiple Volumes**

   - **Method**: POST
   - **URL**: `http://localhost:5000/pods/`
   - **Body**:
     ```json
     {
       "name": "data-processing-pod",
       "cpu_cores_req": 2,
       "containers": [
         {
           "name": "processor",
           "image": "python:3.9",
           "cpu_req": 1.5,
           "memory_req": 1024,
           "command": "python",
           "args": "-m http.server 8080"
         }
       ],
       "volumes": [
         {
           "name": "input-volume",
           "type": "emptyDir",
           "size": 2,
           "path": "/input"
         },
         {
           "name": "output-volume",
           "type": "emptyDir",
           "size": 5,
           "path": "/output"
         },
         {
           "name": "config-volume",
           "type": "configMap",
           "size": 1,
           "path": "/etc/config"
         }
       ],
       "config": [
         {
           "name": "processing-config",
           "type": "env",
           "key": "PROCESSING_MODE",
           "value": "batch"
         }
       ]
     }
     ```

5. **List All Pods**

   - **Method**: GET
   - **URL**: `http://localhost:5000/pods/`

6. **Get Pod Details**

   - **Method**: GET
   - **URL**: `http://localhost:5000/pods/1`
     _(Replace `1` with actual pod ID)_

7. **Check Pod Health**

   - **Method**: GET
   - **URL**: `http://localhost:5000/pods/1/health`
     _(Replace `1` with actual pod ID)_

8. **Delete a Pod**

   - **Method**: DELETE
   - **URL**: `http://localhost:5000/pods/1`
     _(Replace `1` with actual pod ID)_

---

## Docker Integration

Kube-9 uses Docker to simulate both nodes and pods:

1. **Node Containers**: Each node in the cluster is represented by a Docker container running the node simulator

2. **Pod Processes**: Within each node container, pods are simulated as processes

3. **Container Networks**: Custom Docker networks are created for pod networking

### Node Simulator Image

The Node Simulator image is built automatically when creating the first node, but you can build it manually:

```bash
cd node_simulation
docker build -t kube9-node-simulator .
```

### Viewing Docker Resources

To verify the Docker resources created by Kube-9:

- **View Running Containers**:

  ```bash
  docker ps | grep kube9-node
  ```

- **View Networks**:

  ```bash
  docker network ls | grep kube9
  ```

- **View Container Logs**:
  ```bash
  docker logs <container_id>
  ```

---

## Troubleshooting

### API Connection Issues

- **Symptom**: Cannot connect to API server
- **Solutions**:
  - Ensure the API server is running (`python app.py`)
  - Check if port 5000 is available and not in use
  - Verify firewall settings are not blocking the connection

### Database Connection Issues

- **Symptom**: API server starts but shows database connection errors
- **Solutions**:
  - Verify MySQL is running: `sudo systemctl status mysql`
  - Check database credentials in `config.py`
  - Ensure the database exists: `mysql -u root -p -e "SHOW DATABASES;"`
  - Test connection: `http://localhost:5000/test_db`

### Node Creation Failures

- **Symptom**: Cannot create nodes
- **Solutions**:
  - Ensure Docker is running: `docker info`
  - Check Docker API access: `python -c "import docker; print(docker.from_env().containers.list())"`
  - Verify the node image can be built: `cd node_simulation && docker build -t kube9-node-simulator .`
  - Check API server logs for detailed error messages

### Pod Creation Failures

- **Symptom**: Cannot create pods
- **Solutions**:
  - Ensure at least one healthy worker node exists
  - Verify the node has enough available CPU resources
  - Check if specified container images are accessible
  - Review API server logs for detailed error messages

### Node Heartbeat Issues

- **Symptom**: Nodes keep failing or showing as unhealthy
- **Solutions**:
  - Check network connectivity between node containers and API server
  - Ensure Docker host networking is properly configured
  - Verify no firewall rules are blocking communications
  - Check the node container logs: `docker logs kube9-node-<node_name>`

---

## Project Structure

- **app.py**: Main API server entry point
- **models.py**: Database models for nodes, pods, containers, etc.
- **config.py**: Configuration settings
- **dashboard.py**: Streamlit dashboard for visual management
- **routes/**: API route handlers
  - **nodes.py**: Node management endpoints
  - **pods.py**: Pod management endpoints
- **services/**: Core services
  - **docker_service.py**: Docker integration service
  - **monitor.py**: Health monitoring and recovery service
- **node_simulation/**: Node simulator code
  - **node_simulator.py**: Code that runs inside node containers
  - **Dockerfile**: Definition for node container image

---

## Future Enhancements

1. **Services and Load Balancing**: Expose pods to other pods or external users through stable IPs or DNS names.
2. **Deployments for Scaling**: Add support for running multiple replicas of pods and scaling them up/down.
3. **Rolling Updates**: Enable application updates without downtime by gradually replacing pods.
4. **Enhanced Monitoring**: Add comprehensive metrics collection and visualization.
5. **Storage Classes**: Implement dynamic persistent volume provisioning with different storage options.
6. **Network Policies**: Add support for controlling network traffic between pods.

---

## License

This project is for educational purposes and is not intended for production use.

## Contributors

- PES2UG22CS011
- PES2UG22CS003
- PES2UG22CS042
- PES2UG22CS027

