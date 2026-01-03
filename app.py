import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import io

# --- PAGE CONFIG ---
st.set_page_config(page_title="Warehouse Pulse Check", layout="wide")
st.title("🏭 Warehouse Pulse Check - Production & Inventory")

# --- PREDEFINED ---
COIL_MATERIALS = [
    ".010 Smooth Stainless Steel No Polythene",
    ".010 Stainless Steel Polythene",
    ".016 Stainless Steel No Polythene",
    ".016 Stainless Polythene",
    ".020 Stainless Steel Polythene",
    ".010 Stainless Steel RPR",
    ".016 Smooth Aluminum",
    ".016 Stucco Aluminum",
    ".020 Smooth Aluminum",
    ".020 Stucco Aluminum",
    ".024 Smooth Aluminum",
    ".024 Stucco Aluminum",
    ".032 Smooth Aluminum",
    ".032 Stucco Aluminum"
]

SIZE_MAP = {
    "Size 2": 13.0,
    "Size 3": 14.5,
    "Size 4": 16.0,
    "Size 5": 18.0,
    "Size 6": 20.0,
    "Size 7": 23.0,
    "Size 8": 26.0,
    "Size 9": 29.5,
    "Size 10": 32.5,
    "Size 11": 36.0,
    "Size 12": 39.5,
}

# --- LOGIN SYSTEM ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.username = ""

if not st.session_state.logged_in:
    st.subheader("🔐 Login Required")
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Log In"):
        users = st.secrets["users"]
        if username in users and users[username] == password:
            st.session_state.logged_in = True
            st.session_state.username = username
            st.success(f"Welcome, {username}!")
            st.rerun()
        else:
            st.error("Invalid username or password")
    st.stop()

st.sidebar.success(f"Logged in as: **{st.session_state.username}**")
if st.sidebar.button("Log Out"):
    st.session_state.logged_in = False
    st.session_state.username = ""
    st.rerun()

operator_name = st.session_state.username  # Auto-filled from login

# --- LOAD INVENTORY ---
if 'df' not in st.session_state:
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        inv_ws = sh.worksheet("Inventory")
        records = inv_ws.get_all_records()
        if records:
            st.session_state.df = pd.DataFrame(records)
        else:
            st.session_state.df = pd.DataFrame(columns=["Coil_ID", "Material", "Footage", "Location", "Status"])
    except Exception as e:
        st.error(f"Connection error: {e}")
        st.session_state.df = pd.DataFrame(columns=["Coil_ID", "Material", "Footage", "Location", "Status"])

df = st.session_state.df

def save_inventory():
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        inv_ws = sh.worksheet("Inventory")
        inv_ws.clear()
        inv_ws.update([df.columns.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"Save failed: {e}")

# --- AUDIT LOG FUNCTION ---
def log_action(action, details=""):
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        log_ws = sh.worksheet("Audit_Log")
        log_ws.append_row([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            st.session_state.username,
            action,
            details
        ])
    except:
        pass  # Silent fail if log tab missing

# --- TABS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Dashboard", "Production Log", "Warehouse Management", "Daily Summary", "Audit Trail"])

with tab1:
    st.subheader("Current Inventory Summary")
    if df.empty:
        st.info("No coils yet.")
    else:
        summary = df.groupby('Material').agg(
            Coil_Count=('Coil_ID', 'count'),
            Total_Footage=('Footage', 'sum')
        ).reset_index()
        summary['Total_Footage'] = summary['Total_Footage'].round(1)
        st.dataframe(summary)
        st.markdown("### Individual Coils")
        st.dataframe(df[['Coil_ID', 'Material', 'Footage', 'Location']])

# --- Production Log (tab2) and other tabs remain as before, with operator_name auto-filled ---

# --- Audit Trail Tab ---
with tab5:
    st.subheader("Audit Trail - All Actions")
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        log_ws = sh.worksheet("Audit_Log")
        records = log_ws.get_all_records()
        if records:
            audit_df = pd.DataFrame(records)
            audit_df = audit_df.sort_values('Timestamp', ascending=False)
            st.dataframe(audit_df, use_container_width=True)
        else:
            st.info("No actions logged yet.")
    except:
        st.info("Create an 'Audit_Log' tab in your sheet with headers: Timestamp, User, Action, Details")

# Add log_action() calls in all actions (receive, production, move, admin)

# Example in receive submit:
log_action("Receive Coils", f"{count} x {material} to {generated_location}")

# Example in production submit:
log_action("Production Order", f"{order_number} by {client_name}")

# Example in admin delete:
log_action("Delete Coil", coil_to_manage)

# Example in move:
log_action("Move Coil", f"{coil_to_move} to {new_location}")
