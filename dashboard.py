import streamlit as st
import requests

API_BASE = "http://localhost:5000"

st.set_page_config(page_title="Kube-9 Dashboard", layout="wide")
st.title("Kubernetes Mimic Dashboard")

page = st.sidebar.selectbox("Select a section", ["Home", "Nodes", "Pods", "Database Status"])

if page == "Home":
    st.header("Welcome to the Kube-9 API Dashboard")
    st.write("This dashboard interacts with your Kubernetes mimic backend.")
    try:
        res = requests.get(f"{API_BASE}/")
        st.success(res.text)
    except Exception as e:
        st.error(f"Error connecting to API: {e}")

elif page == "Nodes":
    st.header("Nodes")
    try:
        res = requests.get(f"{API_BASE}/nodes")
        if res.status_code == 200:
            nodes = res.json()
            st.json(nodes)
        else:
            st.error(f"Error fetching nodes: {res.status_code}")
    except Exception as e:
        st.error(f"API connection error: {e}")

elif page == "Pods":
    st.header("Pods")
    try:
        res = requests.get(f"{API_BASE}/pods")
        if res.status_code == 200:
            pods = res.json()
            st.json(pods)
        else:
            st.error(f"Error fetching pods: {res.status_code}")
    except Exception as e:
        st.error(f"API connection error: {e}")

elif page == "Database Status":
    st.header("Database Connection Test")
    try:
        res = requests.get(f"{API_BASE}/test_db")
        if res.status_code == 200:
            st.success(res.text)
        else:
            st.error("Failed to connect to the database.")
    except Exception as e:
        st.error(f"API connection error: {e}")
