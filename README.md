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
