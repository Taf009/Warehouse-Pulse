import streamlit as st
import pandas as pd
import gspread
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="Warehouse Pulse Check", layout="wide")
st.title("🏭 Warehouse Pulse Check - Production & Inventory")

# --- PREDEFINED MATERIALS & LOCATIONS ---
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

# --- LOAD INVENTORY FROM GOOGLE SHEETS INTO SESSION STATE ---
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
        st.error(f"Could not connect to Google Sheet: {e}")
        st.session_state.df = pd.DataFrame(columns=["Coil_ID", "Material", "Footage", "Location", "Status"])

df = st.session_state.df

# --- SAVE FUNCTION ---
def save_inventory():
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        inv_ws = sh.worksheet("Inventory")
        inv_ws.clear()
        inv_ws.update([df.columns.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"Failed to save: {e}")

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Production Log", "Warehouse Management", "Daily Summary"])

with tab1:
    st.subheader("Current Inventory")
    if df.empty:
        st.info("No coils in inventory yet. Go to Warehouse Management to add some.")
    else:
        st.dataframe(df[['Coil_ID', 'Material', 'Footage', 'Location', 'Status']], use_container_width=True)

with tab3:
    st.subheader("Receive New Coils")
    with st.form("receive_coils_form", clear_on_submit=True):
        st.markdown("#### Add New Coil Shipment")
        material = st.selectbox("Material Type", COIL_MATERIALS)
        count = st.number_input("Number of Coils", min_value=1, value=1, step=1)
        footage = st.number_input("Footage per Coil (ft)", min_value=0.1, value=3000.0)
        location = st.selectbox("Initial Location", LOCATIONS)

        submitted = st.form_submit_button("🚀 Add Coils to Inventory")

        if submitted:
            new_coils = []
            base_code = material.split()[0][1:]  # e.g., "010" or "016"
            for i in range(count):
                coil_id = f"{base_code}-{datetime.now().strftime('%m%d')}-{str(i+1).zfill(3)}"
                new_coils.append({
                    "Coil_ID": coil_id,
                    "Material": material,
                    "Footage": footage,
                    "Location": location,
                    "Status": "Active"
                })
            # Update session state
            new_df = pd.concat([df, pd.DataFrame(new_coils)], ignore_index=True)
            st.session_state.df = new_df
            save_inventory()
            st.success(f"✅ Successfully added {count} new coil(s) of {material}!")
            st.balloons()
            st.rerun()

    st.divider()
    st.subheader("Current Inventory Preview")
    if df.empty:
        st.info("No coils added yet")
    else:
        st.dataframe(df[['Coil_ID', 'Material', 'Footage', 'Location']], use_container_width=True)

with tab2:
    st.subheader("Production Log")
    st.info("Full production logging with automatic PDF email is coming in the next update — add some coils first!")

with tab4:
    st.subheader("Daily Summary")
    st.info("Daily usage, waste, and efficiency stats will appear once production starts.")

# --- END OF CODE ---
