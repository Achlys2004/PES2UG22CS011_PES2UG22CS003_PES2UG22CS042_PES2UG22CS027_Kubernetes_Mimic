import sys
import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import time
import datetime


API_BASE = "http://localhost:5000"
REFRESH_INTERVAL = 30
VERSION = "1.0.0"


COLORS = {
    "primary": "#0066cc",
    "secondary": "#6c757d",
    "success": "#28a745",
    "warning": "#ffc107",
    "danger": "#dc3545",
    "info": "#17a2b8",
    "light": "#f8f9fa",
    "dark": "#343a40",
    "white": "#ffffff",
    "transparent": "rgba(255, 255, 255, 0)",
    "node": {"master": "#ff9900", "worker": "#0066cc"},
    "status": {
        "healthy": "#28a745",
        "failed": "#dc3545",
        "recovering": "#ffc107",
        "initializing": "#17a2b8",
        "permanently_failed": "#6c757d",
        "pending": "#6c757d",
        "running": "#28a745",
    },
}


st.set_page_config(
    page_title="Kube-9 Dashboard",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
<style>
    .main-header {
        font-size: 2.5rem;
        color: #0066cc;
        font-weight: 700;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.8rem;
        color: #343a40;
        font-weight: 600;
        margin-top: 1rem;
        margin-bottom: 0.5rem;
    }
    .card {
        padding: 1.5rem;
        border-radius: 0.5rem;
        background-color: white;
        box-shadow: 0 0.15rem 1.75rem 0 rgba(58, 59, 69, 0.15);
        margin-bottom: 1.5rem;
    }
    .metric-value {
        font-size: 2.5rem;
        font-weight: 700;
        line-height: 1;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #6c757d;
        margin-top: 0.5rem;
    }
    .status-badge {
        display: inline-block;
        padding: 0.35rem 0.65rem;
        font-size: 0.85rem;
        font-weight: 600;
        line-height: 1;
        text-align: center;
        white-space: nowrap;
        vertical-align: baseline;
        border-radius: 0.375rem;
    }
    .section-divider {
        height: 0;
        margin: 1.5rem 0;
        overflow: hidden;
        border-top: 1px solid #e9ecef;
    }
    .sidebar-header {
        font-size: 1.2rem;
        font-weight: 600;
        margin-top: 1rem;
    }
    .resource-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: #0066cc;
        margin-bottom: 0.5rem;
    }
    .info-text {
        color: #6c757d;
        font-size: 0.9rem;
    }
    div[data-testid="stSidebarNav"] {
        background-image: url('data:image/png;base64,iVBORw0KGgo...');
        background-repeat: no-repeat;
        padding-top: 80px;
        background-position: 20px 20px;
    }
    
    .stButton button {
        width: 100%;
        border-radius: 0.25rem;
        height: 2.5rem;
        font-weight: 600;
    }
    .api-badge {
        background-color: #17a2b8;
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-size: 0.75rem;
        margin-right: 0.5rem;
    }
    .chart-container {
        background-color: white;
        border-radius: 0.5rem;
        padding: 1rem;
        box-shadow: 0 0.15rem 1.75rem 0 rgba(58, 59, 69, 0.1);
    }
    .component-badge {
        display: inline-block;
        padding: 0.2rem 0.5rem;
        margin-right: 0.3rem;
        font-size: 0.75rem;
        font-weight: 600;
        border-radius: 0.2rem;
    }
    .kubernetes-header {
        background-color: #326de6;
        color: white;
        padding: 1rem;
        border-radius: 0.5rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
    }
    .kubernetes-header img {
        height: 2.5rem;
        margin-right: 1rem;
    }
    .kubernetes-title {
        font-size: 1.5rem;
        font-weight: 700;
    }
</style>
""",
    unsafe_allow_html=True,
)


def get_logo_base64():

    from PIL import Image, ImageDraw, ImageFont
    import io
    import base64

    img = Image.new("RGBA", (200, 100), color=(255, 255, 255, 0))
    d = ImageDraw.Draw(img)

    d.ellipse((10, 10, 90, 90), fill=(50, 109, 230))
    d.polygon([(50, 20), (80, 50), (50, 80), (20, 50)], fill=(255, 255, 255))

    d.text((100, 35), "Kube-9", fill=(50, 109, 230), font=None)

    buffered = io.BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()


if "auto_refresh" not in st.session_state:
    st.session_state.auto_refresh = False
    st.session_state.refresh_interval = REFRESH_INTERVAL
    st.session_state.last_refresh = None
    st.session_state.nodes_data = None
    st.session_state.pods_data = None
    st.session_state.show_add_node_form = False
    st.session_state.show_add_pod_form = False
    st.session_state.api_connected = False
    st.session_state.selected_node = None
    st.session_state.selected_pod = None
    st.session_state.node_filter = "all"
    st.session_state.pod_filter = "all"


def format_status_badge(status):
    """Format status with colored badge"""
    color = COLORS["status"].get(status.lower(), COLORS["secondary"])
    return f'<span class="status-badge" style="background-color: {color}; color: white;">{status}</span>'


def format_component_badge(status):
    """Format component status with colored badge"""
    if status is None:
        status = "unknown"
    color = "#28a745" if status.lower() == "running" else "#dc3545"
    return f'<span class="component-badge" style="background-color: {color}; color: white;">{status}</span>'

def format_datetime(dt_str):
    """Format datetime string to readable format"""
    if not dt_str:
        return "Never"
    try:
        dt = datetime.datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return dt_str


def get_api_data(endpoint, default=None):
    """Get data from API with error handling"""
    try:
        response = requests.get(f"{API_BASE}/{endpoint}", timeout=5)
        if response.status_code == 200:
            st.session_state.api_connected = True
            return response.json()
        else:
            st.error(f"API Error: {response.status_code} - {response.text}")
            return default
    except Exception as e:
        st.session_state.api_connected = False
        st.error(f"Connection Error: {str(e)}")
        return default


def refresh_data():
    """Refresh all data from the API"""
    with st.spinner("Refreshing data..."):

        try:
            response = requests.get(f"{API_BASE}/", timeout=2)
            st.session_state.api_connected = response.status_code == 200
        except:
            st.session_state.api_connected = False

        if st.session_state.api_connected:

            st.session_state.nodes_data = get_api_data("nodes", [])

            st.session_state.pods_data = get_api_data("pods", [])

            st.session_state.last_refresh = datetime.datetime.now()


def check_auto_refresh():
    if st.session_state.auto_refresh and st.session_state.last_refresh:
        time_since_refresh = (
            datetime.datetime.now() - st.session_state.last_refresh
        ).total_seconds()
        if time_since_refresh >= st.session_state.refresh_interval:
            refresh_data()


with st.sidebar:
    st.markdown(
        '<div class="sidebar-header">KUBE-9 DASHBOARD</div>', unsafe_allow_html=True
    )

    page = st.radio(
        "Navigation",
        ["Overview", "Nodes", "Pods", "Create Resources", "Settings", "Help"],
        key="page_selection",
    )

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="sidebar-header">DASHBOARD SETTINGS</div>', unsafe_allow_html=True
    )

    auto_refresh = st.checkbox(
        "Auto-refresh", value=st.session_state.auto_refresh, key="auto_refresh_toggle"
    )

    if st.session_state.auto_refresh != auto_refresh:
        st.session_state.auto_refresh = auto_refresh

    if st.session_state.auto_refresh:
        refresh_interval = st.slider(
            "Refresh interval (seconds)",
            min_value=5,
            max_value=120,
            value=st.session_state.refresh_interval,
            step=5,
        )
        st.session_state.refresh_interval = refresh_interval

    if st.button("Refresh Now"):
        refresh_data()

    if st.session_state.api_connected:
        st.success("✅ API Connected")
    else:
        st.error("❌ API Disconnected")

    if st.session_state.last_refresh:
        st.info(f"Last refresh: {st.session_state.last_refresh.strftime('%H:%M:%S')}")

    st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
    st.markdown(
        f"<div class='info-text'>Kube-9 Dashboard v{VERSION}</div>",
        unsafe_allow_html=True,
    )


check_auto_refresh()


if st.session_state.nodes_data is None:
    refresh_data()


if page != "Help":
    st.markdown(
        f"""
        <div class="kubernetes-header">
            <div class="kubernetes-title">Kube-9 {page} Dashboard</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


if page == "Overview":

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        total_nodes = (
            len(st.session_state.nodes_data) if st.session_state.nodes_data else 0
        )
        st.markdown(
            f'<div class="metric-value">{total_nodes}</div>', unsafe_allow_html=True
        )
        st.markdown(
            '<div class="metric-label">Total Nodes</div>', unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        total_pods = (
            len(st.session_state.pods_data) if st.session_state.pods_data else 0
        )
        st.markdown(
            f'<div class="metric-value">{total_pods}</div>', unsafe_allow_html=True
        )
        st.markdown(
            '<div class="metric-label">Total Pods</div>', unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with col3:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        healthy_nodes = (
            sum(
                1
                for node in st.session_state.nodes_data
                if node.get("health_status") == "healthy"
            )
            if st.session_state.nodes_data
            else 0
        )
        st.markdown(
            f'<div class="metric-value">{healthy_nodes}</div>', unsafe_allow_html=True
        )
        st.markdown(
            '<div class="metric-label">Healthy Nodes</div>', unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

    with col4:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        running_pods = (
            sum(
                1
                for pod in st.session_state.pods_data
                if pod.get("health_status") == "running"
            )
            if st.session_state.pods_data
            else 0
        )
        st.markdown(
            f'<div class="metric-value">{running_pods}</div>', unsafe_allow_html=True
        )
        st.markdown(
            '<div class="metric-label">Running Pods</div>', unsafe_allow_html=True
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="sub-header">Cluster Resource Utilization</div>',
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.markdown(
            '<div class="resource-title">CPU Allocation by Node</div>',
            unsafe_allow_html=True,
        )

        if st.session_state.nodes_data:
            node_data = []
            for node in st.session_state.nodes_data:
                used_cores = node.get("cpu_cores_total", 0) - node.get(
                    "cpu_cores_avail", 0
                )
                node_data.append(
                    {
                        "name": node.get("name", "Unknown"),
                        "used_cores": used_cores,
                        "available_cores": node.get("cpu_cores_avail", 0),
                    }
                )

            if node_data:
                df = pd.DataFrame(node_data)

                fig = px.bar(
                    df,
                    x="name",
                    y=["used_cores", "available_cores"],
                    labels={"name": "Node", "value": "CPU Cores", "variable": "Status"},
                    title=None,
                    color_discrete_map={
                        "used_cores": COLORS["primary"],
                        "available_cores": COLORS["light"],
                    },
                )

                fig.update_layout(
                    legend_title_text="",
                    xaxis_title="Node",
                    yaxis_title="CPU Cores",
                    barmode="stack",
                    height=400,
                    margin=dict(t=20, r=20, b=40, l=40),
                    legend=dict(
                        orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
                    ),
                )

                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No node data available")
        else:
            st.info("No node data available")

        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.markdown(
            '<div class="resource-title">Node Health Status</div>',
            unsafe_allow_html=True,
        )

        if st.session_state.nodes_data:
            status_counts = {}
            for node in st.session_state.nodes_data:
                status = node.get("health_status", "unknown")
                status_counts[status] = status_counts.get(status, 0) + 1

            if status_counts:
                df = pd.DataFrame(
                    [{"status": k, "count": v} for k, v in status_counts.items()]
                )

                color_map = {
                    status: COLORS["status"].get(status.lower(), COLORS["secondary"])
                    for status in status_counts.keys()
                }

                fig = px.pie(
                    df,
                    values="count",
                    names="status",
                    color="status",
                    color_discrete_map=color_map,
                    hole=0.4,
                )

                fig.update_layout(
                    showlegend=True,
                    height=400,
                    margin=dict(t=20, r=20, b=20, l=20),
                    legend=dict(
                        orientation="h",
                        yanchor="bottom",
                        y=-0.1,
                        xanchor="center",
                        x=0.5,
                    ),
                )

                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No status data available")
        else:
            st.info("No node data available")

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="sub-header">Cluster Overview</div>', unsafe_allow_html=True
    )

    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="resource-title">Node Distribution</div>',
            unsafe_allow_html=True,
        )

        if st.session_state.nodes_data:

            node_types = {}
            for node in st.session_state.nodes_data:
                node_type = node.get("node_type", "unknown")
                node_types[node_type] = node_types.get(node_type, 0) + 1

            type_df = pd.DataFrame(
                [{"type": k, "count": v} for k, v in node_types.items()]
            )

            fig = px.bar(
                type_df,
                y="type",
                x="count",
                orientation="h",
                color="type",
                color_discrete_map={
                    "master": COLORS["node"]["master"],
                    "worker": COLORS["node"]["worker"],
                },
            )

            fig.update_layout(
                showlegend=False,
                height=150,
                margin=dict(t=20, r=20, b=20, l=100),
                xaxis_title=None,
                yaxis_title=None,
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No node data available")

        st.markdown("</div>", unsafe_allow_html=True)

    with col2:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="resource-title">Pod Distribution</div>', unsafe_allow_html=True
        )

        if st.session_state.pods_data:

            pod_types = {}
            for pod in st.session_state.pods_data:
                pod_type = pod.get("type", "unknown")
                pod_types[pod_type] = pod_types.get(pod_type, 0) + 1

            type_df = pd.DataFrame(
                [{"type": k, "count": v} for k, v in pod_types.items()]
            )

            fig = px.bar(
                type_df,
                y="type",
                x="count",
                orientation="h",
                color="type",
                color_discrete_map={
                    "single-container": COLORS["primary"],
                    "multi-container": COLORS["info"],
                },
            )

            fig.update_layout(
                showlegend=False,
                height=150,
                margin=dict(t=20, r=20, b=20, l=150),
                xaxis_title=None,
                yaxis_title=None,
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No pod data available")

        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<div class="sub-header">Pod Distribution Across Nodes</div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="chart-container">', unsafe_allow_html=True)

    if st.session_state.nodes_data and st.session_state.pods_data:

        node_map = {node["id"]: node["name"] for node in st.session_state.nodes_data}

        pods_per_node = {}
        for pod in st.session_state.pods_data:
            if "node" in pod and pod["node"]:
                node_id = pod["node"].get("id")
                if node_id in node_map:
                    node_name = node_map[node_id]
                    pods_per_node[node_name] = pods_per_node.get(node_name, 0) + 1

        if pods_per_node:

            df = pd.DataFrame(
                [{"node": k, "pods": v} for k, v in pods_per_node.items()]
            )

            fig = px.bar(
                df,
                x="node",
                y="pods",
                color="pods",
                color_continuous_scale=px.colors.sequential.Blues,
            )

            fig.update_layout(
                height=300,
                margin=dict(t=20, r=20, b=40, l=40),
                xaxis_title="Node",
                yaxis_title="Number of Pods",
                coloraxis_showscale=False,
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No pods are currently assigned to nodes")
    else:
        st.info("Node or pod data not available")

    st.markdown("</div>", unsafe_allow_html=True)


elif page == "Nodes":

    st.markdown(
        '<div class="resource-title">Nodes Filter</div>', unsafe_allow_html=True
    )
    col1, col2 = st.columns([1, 3])

    with col1:
        node_filter = st.selectbox(
            "Filter by status:",
            [
                "all",
                "healthy",
                "failed",
                "recovering",
                "initializing",
                "permanently_failed",
            ],
            key="node_status_filter",
        )

    with col2:
        node_type_filter = st.multiselect(
            "Filter by type:",
            ["master", "worker"],
            default=["master", "worker"],
            key="node_type_filter",
        )

    st.markdown('<div class="sub-header">Nodes</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        if not st.session_state.nodes_data:
            st.info("No nodes found. Add a node using the 'Create Resources' tab.")

    if not st.session_state.nodes_data:
        st.info("No nodes found. Add a node using the 'Create Resources' tab.")
    else:

        filtered_nodes = st.session_state.nodes_data
        if node_filter != "all":
            filtered_nodes = [
                n
                for n in filtered_nodes
                if n.get("health_status", "").lower() == node_filter.lower()
            ]

        if node_type_filter:
            filtered_nodes = [
                n
                for n in filtered_nodes
                if n.get("node_type", "").lower() in node_type_filter
            ]

        if not filtered_nodes:
            st.info("No nodes match the selected filters.")
        else:

            node_data = []
            for node in filtered_nodes:
                node_data.append(
                    {
                        "ID": node.get("id"),
                        "Name": node.get("name", "Unknown"),
                        "Type": node.get("node_type", "Unknown"),
                        "Status": format_status_badge(
                            node.get("health_status", "Unknown")
                        ),
                        "CPU Total": node.get("cpu_cores_total", 0),
                        "CPU Available": node.get("cpu_cores_avail", 0),
                        "Pods": node.get("hosted_pods", 0),
                        "Actions": f"<button onclick=\"alert('View node {node.get('id')}');\">View</button>",
                    }
                )

            df = pd.DataFrame(node_data)

            st.write("Click on a row to view node details:")

            selected_indices = []
            if not df.empty:

                def make_clickable(val):
                    return f'<div style="text-align: center;">{val}</div>'

                formatted_df = df.copy()

                formatted_df["Status"] = formatted_df["Status"].apply(lambda x: x)
                formatted_df = formatted_df.drop(columns=["Actions"])

                st.markdown(
                    formatted_df.to_html(escape=False, index=False),
                    unsafe_allow_html=True,
                )

                selected_node_id = st.selectbox(
                    "Select a node to view details:",
                    [f"{node['id']} - {node['name']}" for node in filtered_nodes],
                    key="node_selection",
                )

                if selected_node_id:
                    node_id = int(selected_node_id.split(" - ")[0])
                    st.session_state.selected_node = next(
                        (n for n in filtered_nodes if n.get("id") == node_id), None
                    )

    if st.session_state.selected_node:
        node = st.session_state.selected_node
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="sub-header">Node: {node.get("name")}</div>',
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)

        with col1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(
                '<div class="resource-title">Node Information</div>',
                unsafe_allow_html=True,
            )

            node_info = f"""
            - **ID**: {node.get('id')}
            - **Name**: {node.get('name')}
            - **Type**: {node.get('node_type', 'Unknown')}
            - **Status**: {node.get('health_status', 'Unknown')}
            - **CPU Cores (Total)**: {node.get('cpu_cores_total', 0)}
            - **CPU Cores (Available)**: {node.get('cpu_cores_avail', 0)}
            - **Hosted Pods**: {node.get('hosted_pods', 0)}
            """

            recovery_attempts = node.get("recovery_attempts")
            max_recovery_attempts = node.get("max_recovery_attempts")

            if recovery_attempts is not None and max_recovery_attempts is not None:
                node_info += f"- **Recovery Attempts**: {recovery_attempts}/{max_recovery_attempts}"

                if (
                    node.get("health_status") == "failed"
                    and recovery_attempts >= max_recovery_attempts - 1
                ):
                    node_info += " ⚠️"

            st.markdown(node_info)

            last_heartbeat = node.get("last_heartbeat", None)
            if last_heartbeat:
                st.markdown(f"- **Last Heartbeat**: {format_datetime(last_heartbeat)}")

            container = node.get("container", {})
            if container:
                st.markdown(
                    f"""
                - **Container ID**: {container.get('id', 'N/A')[:12] if container.get('id') else 'N/A'}
                - **Container Status**: {container.get('status', 'Unknown')}
                - **IP Address**: {container.get('ip', 'N/A')}
                - **Port**: {container.get('port', 'N/A')}
                """
                )

            if node.get("health_status") == "permanently_failed":
                st.markdown(
                    """
                    ⚠️ **This node has permanently failed**
                    
                    - The system will not attempt to recover this node
                    - All pods have been or will be rescheduled to healthy nodes
                    - Container resources for this node have been released
                    """,
                    unsafe_allow_html=True,
                )

                st.markdown(
                    '<div class="section-divider"></div>', unsafe_allow_html=True
                )
                st.markdown("### Container Cleanup Status")

                container_id = node.get("docker_container_id")
                if container_id:
                    st.warning(
                        f"⚠️ Container cleanup pending for node {node.get('name')}"
                    )

                    if st.button("Force Cleanup Container"):
                        try:
                            response = requests.post(
                                f"{API_BASE}/nodes/{node.get('id')}/force_cleanup"
                            )
                            if response.status_code == 200:
                                st.success("Container cleanup triggered")
                                time.sleep(2)
                                st.experimental_rerun()
                            else:
                                st.error(f"Failed to trigger cleanup: {response.text}")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
                else:
                    st.success("✅ Container resources have been cleaned up")

            st.markdown("</div>", unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(
                '<div class="resource-title">Component Status</div>',
                unsafe_allow_html=True,
            )

            components = node.get("components", {})

            common_components = {
                "kubelet": components.get("kubelet", "Unknown"),
                "container_runtime": components.get("container_runtime", "Unknown"),
                "kube_proxy": components.get("kube_proxy", "Unknown"),
                "node_agent": components.get("node_agent", "Unknown"),
            }

            for name, status in common_components.items():
                st.markdown(
                    f"- **{name.replace('_', ' ').title()}**: {format_component_badge(status)}",
                    unsafe_allow_html=True,
                )

            if node.get("node_type") == "master":
                master_components = {
                    "api_server": components.get("api_server", "Unknown"),
                    "scheduler": components.get("scheduler", "Unknown"),
                    "controller": components.get("controller", "Unknown"),
                    "etcd": components.get("etcd", "Unknown"),
                }

                st.markdown(
                    '<div class="section-divider"></div>', unsafe_allow_html=True
                )
                st.markdown("**Master Components**", unsafe_allow_html=True)

                for name, status in master_components.items():
                    st.markdown(
                        f"- **{name.replace('_', ' ').title()}**: {format_component_badge(status)}",
                        unsafe_allow_html=True,
                    )

            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.markdown(
            '<div class="resource-title">Node Actions</div>', unsafe_allow_html=True
        )

        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button("Refresh Node"):

                try:
                    response = requests.get(f"{API_BASE}/nodes/{node.get('id')}")
                    if response.status_code == 200:
                        fresh_node = response.json()
                        st.session_state.selected_node = fresh_node
                        st.success("Node data refreshed!")
                    else:
                        st.error(f"Failed to refresh node: {response.status_code}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

        with col2:
            if st.button("Simulate Failure"):

                try:
                    response = requests.post(
                        f"{API_BASE}/nodes/{node.get('id')}/simulate/failure"
                    )
                    if response.status_code == 200:
                        st.warning(
                            "Node failure simulated. The system will attempt recovery."
                        )

                        response = requests.get(f"{API_BASE}/nodes/{node.get('id')}")
                        if response.status_code == 200:
                            st.session_state.selected_node = response.json()
                    else:
                        st.error(f"Failed to simulate failure: {response.status_code}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

        with col3:
            if st.button("Delete Node"):

                if node.get("pod_ids", []):
                    st.error(
                        "Cannot delete node with pods. Delete or reschedule pods first."
                    )
                else:

                    try:
                        response = requests.delete(f"{API_BASE}/nodes/{node.get('id')}")
                        if response.status_code == 200:
                            st.success("Node deleted successfully!")
                            st.session_state.selected_node = None

                            time.sleep(2)  # 2-second delay
                            refresh_data()
                            st.rerun()
                        else:
                            st.error(f"Failed to delete node: {response.text}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.markdown(
            '<div class="resource-title">CPU Utilization</div>', unsafe_allow_html=True
        )

        cpu_used = node.get("cpu_cores_total", 0) - node.get("cpu_cores_avail", 0)
        cpu_total = node.get("cpu_cores_total", 0)

        if cpu_total > 0:

            fig = go.Figure(
                go.Indicator(
                    mode="gauge+number",
                    value=cpu_used,
                    domain={"x": [0, 1], "y": [0, 1]},
                    title={"text": "CPU Cores Used"},
                    gauge={
                        "axis": {"range": [0, cpu_total], "tickwidth": 1},
                        "bar": {"color": COLORS["primary"]},
                        "steps": [
                            {"range": [0, cpu_total * 0.7], "color": "lightgray"},
                            {
                                "range": [cpu_total * 0.7, cpu_total * 0.9],
                                "color": "orange",
                            },
                            {"range": [cpu_total * 0.9, cpu_total], "color": "red"},
                        ],
                        "threshold": {
                            "line": {"color": "red", "width": 4},
                            "thickness": 0.75,
                            "value": cpu_total * 0.9,
                        },
                    },
                )
            )

            fig.update_layout(height=300, margin=dict(t=20, r=20, b=20, l=20))

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No CPU data available for this node")

        st.markdown("</div>", unsafe_allow_html=True)

        if st.session_state.pods_data:
            node_pods = [
                pod
                for pod in st.session_state.pods_data
                if pod.get("node", {}).get("id") == node.get("id")
            ]

            if node_pods:
                st.markdown(
                    '<div class="sub-header">Pods on this Node</div>',
                    unsafe_allow_html=True,
                )

                pod_data = []
                for pod in node_pods:
                    pod_data.append(
                        {
                            "ID": pod.get("id"),
                            "Name": pod.get("name", "Unknown"),
                            "Status": format_status_badge(
                                pod.get("health_status", "Unknown")
                            ),
                            "Type": pod.get("type", "Unknown"),
                            "CPU Req": pod.get("cpu_cores_req", 0),
                            "Containers": len(pod.get("containers", [])),
                        }
                    )

                pod_df = pd.DataFrame(pod_data)

                st.markdown(
                    pod_df.to_html(escape=False, index=False), unsafe_allow_html=True
                )


elif page == "Pods":

    st.markdown('<div class="resource-title">Pods Filter</div>', unsafe_allow_html=True)
    col1, col2 = st.columns([1, 3])

    with col1:
        pod_filter = st.selectbox(
            "Filter by status:",
            ["all", "running", "failed", "pending"],
            key="pod_status_filter",
        )

    with col2:
        pod_type_filter = st.multiselect(
            "Filter by type:",
            ["single-container", "multi-container"],
            default=["single-container", "multi-container"],
            key="pod_type_filter",
        )

    st.markdown('<div class="sub-header">Pods</div>', unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        if not st.session_state.pods_data:
            st.info("No pods found. Create a pod using the 'Create Resources' tab.")

    if not st.session_state.pods_data:
        st.info("No pods found. Create a pod using the 'Create Resources' tab.")
    else:

        filtered_pods = st.session_state.pods_data
        if pod_filter != "all":
            filtered_pods = [
                p
                for p in filtered_pods
                if p.get("health_status", "").lower() == pod_filter.lower()
            ]

        if pod_type_filter:
            filtered_pods = [
                p for p in filtered_pods if p.get("type", "").lower() in pod_type_filter
            ]

        if not filtered_pods:
            st.info("No pods match the selected filters.")
        else:

            pod_data = []
            for pod in filtered_pods:
                node_name = pod.get("node", {}).get("name", "Unknown")
                pod_data.append(
                    {
                        "ID": pod.get("id"),
                        "Name": pod.get("name", "Unknown"),
                        "Status": format_status_badge(
                            pod.get("health_status", "Unknown")
                        ),
                        "Node": node_name,
                        "Type": pod.get("type", "Unknown"),
                        "CPU Req": pod.get("cpu_cores_req", 0),
                        "IP": pod.get("ip_address", "N/A"),
                        "Containers": len(pod.get("containers", [])),
                    }
                )

            df = pd.DataFrame(pod_data)

            st.write("Click on a row to view pod details:")
            st.markdown(df.to_html(escape=False, index=False), unsafe_allow_html=True)

            selected_pod_id = st.selectbox(
                "Select a pod to view details:",
                [f"{pod['id']} - {pod['name']}" for pod in filtered_pods],
                key="pod_selection",
            )

            if selected_pod_id:
                pod_id = int(selected_pod_id.split(" - ")[0])
                st.session_state.selected_pod = next(
                    (p for p in filtered_pods if p.get("id") == pod_id), None
                )

    if st.session_state.selected_pod:
        pod = st.session_state.selected_pod
        st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
        st.markdown(
            f'<div class="sub-header">Pod: {pod.get("name")}</div>',
            unsafe_allow_html=True,
        )

        col1, col2 = st.columns(2)

        with col1:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(
                '<div class="resource-title">Pod Information</div>',
                unsafe_allow_html=True,
            )

            node_info = pod.get("node", {})
            node_name = node_info.get("name", "Unknown") if node_info else "Unknown"

            st.markdown(
                f"""
            - **ID**: {pod.get('id')}
            - **Name**: {pod.get('name')}
            - **Type**: {pod.get('type', 'Unknown')}
            - **Status**: {pod.get('health_status', 'Unknown')}
            - **CPU Request**: {pod.get('cpu_cores_req', 0)} cores
            - **IP Address**: {pod.get('ip_address', 'N/A')}
            - **Hosted on Node**: {node_name}
            - **Container Count**: {len(pod.get('containers', []))}
            """
            )

            has_volumes = pod.get("has_volumes", False)
            has_config = pod.get("has_config", False)

            features = []
            if has_volumes:
                features.append("Volumes")
            if has_config:
                features.append("Configuration")

            if features:
                st.markdown("**Features**: " + ", ".join(features))

            network_id = pod.get("docker_network_id", None)
            if network_id:
                st.markdown(
                    f"**Docker Network ID**: {network_id[:12] if network_id else 'N/A'}"
                )

            st.markdown("</div>", unsafe_allow_html=True)

        with col2:
            st.markdown('<div class="card">', unsafe_allow_html=True)
            st.markdown(
                '<div class="resource-title">Pod Actions</div>', unsafe_allow_html=True
            )

            col1, col2 = st.columns(2)

            with col1:
                if st.button("Check Health"):

                    try:
                        response = requests.get(
                            f"{API_BASE}/pods/{pod.get('id')}/health"
                        )
                        if response.status_code == 200:
                            health_data = response.json()
                            st.json(health_data)
                        else:
                            st.error(f"Failed to check health: {response.status_code}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

            with col2:
                if st.button("Delete Pod"):

                    try:
                        response = requests.delete(f"{API_BASE}/pods/{pod.get('id')}")
                        if response.status_code == 200:
                            st.success("Pod deleted successfully!")
                            st.session_state.selected_pod = None

                            refresh_data()
                            st.rerun()
                        else:
                            st.error(f"Failed to delete pod: {response.text}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="sub-header">Containers</div>', unsafe_allow_html=True)

        containers = pod.get("containers", [])
        if containers:
            for i, container in enumerate(containers):
                with st.expander(
                    f"Container: {container.get('name', f'Container {i+1}')}"
                ):
                    st.markdown(
                        f"""
                    - **ID**: {container.get('id', 'N/A')}
                    - **Name**: {container.get('name', 'Unknown')}
                    - **Image**: {container.get('image', 'Unknown')}
                    - **Status**: {container.get('status', 'Unknown')}
                    - **CPU Request**: {container.get('cpu', 0)} cores
                    - **Memory Request**: {container.get('memory', 0)} MB
                    """
                    )

                    docker_id = container.get("docker_id", None)
                    docker_status = container.get("docker_status", None)

                    if docker_id or docker_status:
                        st.markdown("**Docker Information**")
                        if docker_id:
                            st.markdown(
                                f"- **Docker Container ID**: {docker_id[:12] if docker_id else 'N/A'}"
                            )
                        if docker_status:
                            st.markdown(f"- **Docker Status**: {docker_status}")
        else:
            st.info("No container information available")

        volumes = pod.get("volumes", [])
        if volumes:
            st.markdown('<div class="sub-header">Volumes</div>', unsafe_allow_html=True)

            for volume in volumes:
                with st.expander(f"Volume: {volume.get('name', 'Unknown')}"):
                    st.markdown(
                        f"""
                    - **ID**: {volume.get('id', 'N/A')}
                    - **Name**: {volume.get('name', 'Unknown')}
                    - **Type**: {volume.get('type', 'Unknown')}
                    - **Size**: {volume.get('size', 0)} GB
                    - **Path**: {volume.get('path', 'N/A')}
                    - **Docker Volume**: {volume.get('docker_volume', 'N/A')}
                    """
                    )

        configs = pod.get("config", [])
        if configs:
            st.markdown(
                '<div class="sub-header">Configuration</div>', unsafe_allow_html=True
            )

            for config in configs:
                with st.expander(f"Config: {config.get('name', 'Unknown')}"):
                    st.markdown(
                        f"""
                    - **ID**: {config.get('id', 'N/A')}
                    - **Name**: {config.get('name', 'Unknown')}
                    - **Type**: {config.get('type', 'Unknown')}
                    - **Key**: {config.get('key', 'N/A')}
                    - **Value**: {config.get('value', 'N/A')}
                    """
                    )


elif page == "Create Resources":
    tab1, tab2 = st.tabs(["Create Node", "Create Pod"])

    with tab1:
        st.markdown(
            '<div class="sub-header">Create New Node</div>', unsafe_allow_html=True
        )

        with st.form("create_node_form"):
            node_name = st.text_input("Node Name", key="new_node_name")

            col1, col2 = st.columns(2)

            with col1:
                node_type = st.selectbox(
                    "Node Type", ["worker", "master"], key="new_node_type"
                )

            with col2:
                cpu_cores = st.slider(
                    "CPU Cores", min_value=1, max_value=16, value=4, key="new_node_cpu"
                )

            submit_button = st.form_submit_button("Create Node")

            if submit_button:
                if not node_name:
                    st.error("Node name is required.")
                else:

                    try:
                        node_data = {
                            "name": node_name,
                            "node_type": node_type,
                            "cpu_cores_avail": cpu_cores,
                        }

                        response = requests.post(f"{API_BASE}/nodes/", json=node_data)

                        if response.status_code == 201:
                            st.success(f"Node '{node_name}' created successfully!")

                            refresh_data()
                        else:
                            st.error(f"Failed to create node: {response.text}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")

    with tab2:
        st.markdown(
            '<div class="sub-header">Create New Pod</div>', unsafe_allow_html=True
        )

        with st.form("create_pod_form"):
            pod_name = st.text_input("Pod Name", key="new_pod_name")

            cpu_cores_req = st.slider(
                "CPU Cores Required",
                min_value=1,
                max_value=8,
                value=1,
                key="new_pod_cpu",
            )

            st.markdown("### Container Configuration")

            num_containers = st.number_input(
                "Number of containers",
                min_value=1,
                max_value=10,
                value=1,
                key="num_containers",
            )

            containers_data = []

            for i in range(1, num_containers + 1):
                with st.expander(f"Container {i}", expanded=(i == 1)):
                    container_name = st.text_input(
                        f"Container {i} Name",
                        key=f"container{i}_name",
                        value=f"container-{i}",
                    )

                    container_image = st.text_input(
                        f"Container {i} Image",
                        value="nginx:latest",
                        key=f"container{i}_image",
                        help="Docker image for the container (e.g., nginx:latest)",
                    )

                    col1, col2 = st.columns(2)
                    with col1:
                        container_cpu = st.number_input(
                            f"CPU Request (cores)",
                            min_value=0.1,
                            max_value=4.0,
                            value=0.5,
                            step=0.1,
                            key=f"container{i}_cpu",
                        )

                    with col2:
                        container_memory = st.number_input(
                            f"Memory Request (MB)",
                            min_value=64,
                            max_value=4096,
                            value=256,
                            step=64,
                            key=f"container{i}_memory",
                        )

                    show_advanced = st.checkbox(
                        f"Show advanced options", key=f"container{i}_advanced"
                    )

                    container_command = None
                    container_args = None

                    if show_advanced:
                        container_command = st.text_input(
                            f"Command (optional)",
                            key=f"container{i}_command",
                            help="Override container entrypoint",
                        )

                        container_args = st.text_input(
                            f"Arguments (optional)",
                            key=f"container{i}_args",
                            help="Command arguments",
                        )

                    container_data = {
                        "name": container_name,
                        "image": container_image,
                        "cpu_req": container_cpu,
                        "memory_req": container_memory,
                    }

                    if show_advanced and container_command:
                        container_data["command"] = container_command

                    if show_advanced and container_args:
                        container_data["args"] = container_args

                    containers_data.append(container_data)

            add_volumes = st.checkbox("Add volumes", key="add_volumes")
            volumes_data = []

            if add_volumes:

                num_volumes = st.number_input(
                    "Number of volumes",
                    min_value=1,
                    max_value=5,
                    value=1,
                    key="num_volumes",
                )

                for i in range(1, num_volumes + 1):
                    with st.expander(f"Volume {i}", expanded=(i == 1)):
                        volume_name = st.text_input(
                            f"Volume {i} Name",
                            key=f"volume{i}_name",
                            value=f"volume-{i}",
                        )

                        volume_type = st.selectbox(
                            f"Volume {i} Type",
                            ["emptyDir", "hostPath", "configMap", "secret"],
                            key=f"volume{i}_type",
                        )

                        volume_size = st.slider(
                            f"Volume {i} Size (GB)",
                            min_value=1,
                            max_value=10,
                            value=1,
                            key=f"volume{i}_size",
                        )

                        volume_path = st.text_input(
                            f"Mount Path",
                            value=f"/data/vol{i}",
                            key=f"volume{i}_path",
                            help="Path where volume will be mounted in containers",
                        )

                        volumes_data.append(
                            {
                                "name": volume_name,
                                "type": volume_type,
                                "size": volume_size,
                                "path": volume_path,
                            }
                        )

            add_config = st.checkbox("Add configuration", key="add_config")
            config_data = None
            if add_config:
                with st.expander("Configuration", expanded=True):
                    config_name = st.text_input("Config Name", key="config_name")
                    config_type = st.selectbox(
                        "Config Type", ["env", "secret"], key="config_type"
                    )
                    config_key = st.text_input("Key", key="config_key")
                    config_value = st.text_input("Value", key="config_value")

                config_data = {
                    "name": config_name,
                    "type": config_type,
                    "key": config_key,
                    "value": config_value,
                }

            submit_button = st.form_submit_button("Create Pod")

            if submit_button:

                if not pod_name:
                    st.error("Pod name is required")
                elif not containers_data:
                    st.error("At least one container is required")
                else:

                    pod_data = {
                        "name": pod_name,
                        "cpu_cores_req": cpu_cores_req,
                        "containers": containers_data,
                    }

                    if volumes_data:
                        pod_data["volumes"] = volumes_data

                    if config_data:
                        pod_data["config"] = [config_data]

                    try:
                        with st.spinner("Creating pod..."):
                            response = requests.post(f"{API_BASE}/pods/", json=pod_data)

                            if response.status_code == 200:
                                st.success(f"Pod '{pod_name}' created successfully!")
                                st.json(response.json())

                                refresh_data()
                            else:
                                st.error(f"Failed to create pod: {response.text}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")


elif page == "Settings":
    st.markdown(
        '<div class="sub-header">Dashboard Settings</div>', unsafe_allow_html=True
    )

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="resource-title">API Configuration</div>', unsafe_allow_html=True
    )

    api_base = st.text_input("API Base URL", value=API_BASE)
    if api_base != API_BASE:
        API_BASE = api_base
        st.success("API Base URL updated. Click 'Test Connection' to verify.")

    if st.button("Test Connection"):
        try:
            response = requests.get(f"{API_BASE}/")
            if response.status_code == 200:
                st.success(f"Connected to API successfully: {response.text}")
            else:
                st.error(f"Failed to connect to API: {response.status_code}")
        except Exception as e:
            st.error(f"Connection error: {str(e)}")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="resource-title">Display Settings</div>', unsafe_allow_html=True
    )

    refresh_interval = st.slider(
        "Auto-refresh interval (seconds)",
        min_value=5,
        max_value=120,
        value=st.session_state.refresh_interval,
        step=5,
    )

    if refresh_interval != st.session_state.refresh_interval:
        st.session_state.refresh_interval = refresh_interval
        st.success(f"Auto-refresh interval updated to {refresh_interval} seconds.")

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown(
        '<div class="resource-title">Database Connection</div>', unsafe_allow_html=True
    )

    if st.button("Test Database Connection"):
        try:
            response = requests.get(f"{API_BASE}/test_db")
            if response.status_code == 200:
                st.success(f"Database connection test: {response.text}")
            else:
                st.error(f"Database connection test failed: {response.status_code}")
        except Exception as e:
            st.error(f"Connection error: {str(e)}")

    st.markdown("</div>", unsafe_allow_html=True)


elif page == "Help":
    st.markdown(
        '<div class="main-header">Kube-9 Dashboard Help</div>', unsafe_allow_html=True
    )

    st.markdown(
        """
    Welcome to the Kube-9 dashboard help page. This dashboard allows you to manage and monitor your Kubernetes-like cluster.
    
    ## Dashboard Sections
    
    ### Overview
    The Overview page provides a high-level view of your cluster, including:
    - Total nodes and pods
    - Health status of nodes and pods
    - CPU utilization across the cluster
    - Distribution of pods across nodes
    
    ### Nodes
    The Nodes page allows you to:
    - View all nodes in the cluster
    - Filter nodes by type and status
    - View detailed information about each node
    - Monitor node health and component status
    - Simulate node failures
    - Delete nodes
    
    ### Pods
    The Pods page allows you to:
    - View all pods in the cluster
    - Filter pods by type and status
    - View detailed information about each pod
    - Monitor pod health
    - View container, volume, and configuration details
    - Delete pods
    
    ### Create Resources
    The Create Resources page allows you to:
    - Create new nodes with customizable parameters
    - Create new pods with multiple containers
    - Add volumes and configuration to pods
    
    ### Settings
    The Settings page allows you to:
    - Configure the API connection
    - Set auto-refresh interval
    - Test database connection
    
    ## Key Concepts
    
    ### Nodes
    Nodes are the physical or virtual machines that run the containers. In Kube-9, nodes can be:
    
    - **Master nodes**: Manage the cluster control plane
    - **Worker nodes**: Run the application containers
    
    Nodes have health statuses:
    - **Healthy**: Node is running normally
    - **Failed**: Node has failed but may recover
    - **Recovering**: Node is in the process of recovering
    - **Permanently Failed**: Node cannot be recovered
    
    ### Pods
    Pods are the smallest deployable units in Kubernetes. A pod may contain one or more containers.
    
    Pods can have different configurations:
    - **Single container**: Contains one application container
    - **Multi-container**: Contains multiple containers that work together
    - **With volumes**: Has attached storage
    - **With configuration**: Has environment variables or secrets
    
    ## Common Tasks
    
    ### Creating a Node
    1. Go to "Create Resources" tab
    2. Select "Create Node" tab
    3. Enter node name
    4. Select node type (worker or master)
    5. Set CPU cores
    6. Click "Create Node"
    
    ### Creating a Pod
    1. Go to "Create Resources" tab
    2. Select "Create Pod" tab
    3. Enter pod name
    4. Set CPU cores required
    5. Configure container(s)
    6. Optionally add volumes and configuration
    7. Click "Create Pod"
    
    ### Simulating Node Failure
    1. Go to "Nodes" tab
    2. Select a node
    3. Click "Simulate Failure" button
    
    ### Deleting Resources
    1. Go to the respective tab (Nodes or Pods)
    2. Select the resource
    3. Click "Delete" button
    
    ## Troubleshooting
    
    ### API Connection Issues
    - Verify API server is running at the configured URL
    - Check for network connectivity issues
    - Ensure Docker is running
    
    ### Node Creation Issues
    - Ensure Docker is running
    - Check API logs for detailed error messages
    - Verify node name is unique
    
    ### Pod Creation Issues
    - Ensure there are healthy nodes with sufficient resources
    - Check API logs for detailed error messages
    - Verify pod name is unique
    """
    )


st.markdown('<div class="section-divider"></div>', unsafe_allow_html=True)
st.markdown(
    '<div style="text-align: center; color: #6c757d; font-size: 0.8rem;">Kube-9: A Kubernetes-like Container Orchestration System</div>',
    unsafe_allow_html=True,
)
