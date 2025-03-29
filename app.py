from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import text

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://Aathil:orchid123@localhost/cluster_db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

data = SQLAlchemy(app)

@app.route('/')
def home():
    return "Kube_9 API is running!"

@app.route('/test_db')
def test_db():
    try:
        data.session.execute(text('SELECT 1'))
        return "Database Connected!"
    except Exception as e:
        return f"Database Connection failed: {str(e)}"

if __name__ == '__main__':
    app.run(debug=True)