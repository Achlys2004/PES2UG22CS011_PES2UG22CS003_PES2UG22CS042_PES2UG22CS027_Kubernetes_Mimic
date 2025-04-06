# Kube 9 - A-Distributed-Systems-Cluster-Simulation-Framework(Kubernetes_Clone)

Cloud Computing Mini Project Sem 6

## Step 1

Install the libraries:

```
pip install Flask Flask-SQLAlchemy psycopg2

pip install pymysql

pip install cryptography

pip install Flask-Migrate
```

## Step 2

Open sql and create a database called

`cluster_db`

then run

```
python setup_db.py
```

## Step 3

Initialize and apply database migrations:

```
flask db init

flask db migrate -m "Comment"

flask db upgrade
```

## Step 4

run

```
python app.py
```

#### Note: To redo the flask-migrate

```
# Remove the existing migrations directory
rm -r migrations

# Reinitialize migrations
flask db init

# Create a new migration
flask db migrate -m "Initial migration"

# Apply the migration
flask db upgrade
```

#### containers and all

```
# build the image
docker build -t kube node .

# run the simulated nodes
docker run -d --name node1 -p 5001:5000 kube-node
docker run -d --name node2 -p 5002:5000 kube-node
docker run -d --name node3 -p 5003:5000 kube-node
```
