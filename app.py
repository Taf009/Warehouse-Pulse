import streamlit as st
import pandas as pd
import gspread
from datetime import datetime

# --- CONFIG ---
st.set_page_config(page_title="Warehouse Pulse", layout="wide")
st.title("🏭 Warehouse Pulse Check - Production & Inventory")

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

LOCATIONS = ["Rack A1", "Rack A2", "Rack B1", "Rack B2", "Floor Zone C", "Receiving Dock"]

# --- GOOGLE SHEETS ---
gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
sh = gc.open_by_url(st.secrets["SHEET_URL"])
inv_ws = sh.worksheet("Inventory")
log_ws = sh.worksheet("Log")

# Load Inventory
try:
    df = pd.DataFrame(inv_ws.get_all_records())
    if df.empty or 'Coil_ID' not in df.columns:
        df = pd.DataFrame(columns=["Coil_ID", "Material", "Footage", "Location", "Status"])
except:
    df = pd.DataFrame(columns=["Coil_ID", "Material", "Footage", "Location", "Status"])

# Load Log (optional for now)
try:
    log_df = pd.DataFrame(log_ws.get_all_records())
except:
    log_df = pd.DataFrame()

def save_inventory():
    inv_ws.clear()
    inv_ws.update([df.columns.tolist()] + df.values.tolist())

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Production Log", "Warehouse Management", "Daily Summary"])

with tab1:
    st.subheader("Current Coils")
    if df.empty:
        st.info("No coils in inventory yet. Go to Warehouse Management to add some.")
    else:
        st.dataframe(df[['Coil_ID', 'Material', 'Footage', 'Location', 'Status']])

with tab3:  # Warehouse Management - PRIORITY
    st.subheader("Receive New Coils")
    with st.form("receive_coils_form", clear_on_submit=True):
        st.write("#### Add New Coil Shipment")
        material = st.selectbox("Material Type", COIL_MATERIALS)
        count = st.number_input("Number of Coils", min_value=1, value=1, step=1)
        footage = st.number_input("Footage per Coil (ft)", min_value=1.0, value=3000.0)
        location = st.selectbox("Initial Location", LOCATIONS)
        
        submitted = st.form_submit_button("🚀 Add Coils to Inventory")
        
        if submitted:
            new_coils = []
            for i in range(count):
                coil_id = f"{material.split()[0][1:4].upper()}-{datetime.now().strftime('%m%d')}-{str(i+1).zfill(3)}"
                new_coils.append({
                    "Coil_ID": coil_id,
                    "Material": material,
                    "Footage": footage,
                    "Location": location,
                    "Status": "Active"
                })
            global df
            df = pd.concat([df, pd.DataFrame(new_coils)], ignore_index=True)
            save_inventory()
            st.success(f"✅ Successfully added {count} new coil(s) of {material}!")
            st.balloons()
            st.rerun()

    st.divider()
    st.subheader("Current Inventory Preview")
    st.dataframe(df[['Coil_ID', 'Material', 'Footage', 'Location']] if not df.empty else "No coils yet")

with tab2:
    st.subheader("Production Log")
    st.info("Production logging and PDF email coming in the next update — add coils first!")

with tab4:
    st.subheader("Daily Summary")
    st.info("Summary stats will appear once you start logging activity.")
