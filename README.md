# Kube-9: A Distributed Systems Cluster Simulation Framework (Kubernetes Clone)

Kube-9 is a lightweight Kubernetes-like system designed to simulate container orchestration, node management, and pod scheduling. It provides APIs for managing nodes, pods, and their associated resources, with Docker integration for container management.

---

## Features

1. **Node Management**: Add, update, and monitor worker and master nodes.
2. **Pod Management**: Create, delete, and monitor pods with containers, volumes, and configurations.
3. **Docker Integration**: Automatically manage Docker containers, networks, and volumes.
4. **Health Monitoring**: Monitor node and pod health with heartbeat mechanisms.
5. **Node Recovery**: Attempt recovery of failed nodes.
6. **Pod Rescheduling**: Reschedule pods from failed nodes to healthy ones.

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

4. **Check Node Health**
   - **Method**: GET
   - **URL**: `http://localhost:5000/nodes/health`

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

2. **Create a Pod with Volume and Config**

   - **Method**: POST
   - **URL**: `http://localhost:5000/pods/`
   - **Body**:
     ```json
     {
       "name": "web_app_1",
       "cpu_cores_req": 2,
       "containers": [
         {
           "name": "web",
           "image": "httpd:latest",
           "cpu_req": 1.0,
           "memory_req": 512
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
         }
       ]
     }
     ```

3. **List All Pods**

   - **Method**: GET
   - **URL**: `http://localhost:5000/pods/`

4. **Check Pod Health**

   - **Method**: GET  
     **URL**: `http://localhost:5000/pods/1/health`  
     _(Replace `1` with the actual pod ID.)_

5. **Delete a Pod**:

   - **Method**: DELETE  
     **URL**: `http://localhost:5000/pods/1`  
     _(Replace `1` with the actual pod ID.)_

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
