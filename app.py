import streamlit as st
import pandas as pd
import gspread
from datetime import datetime

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

# Load inventory into session state
if 'df' not in st.session_state:
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        inv_ws = sh.worksheet("Inventory")
        records = inv_ws.get_all_records()
        st.session_state.df = pd.DataFrame(records) if records else pd.DataFrame(columns=["Coil_ID", "Material", "Footage", "Location", "Status"])
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

tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Production Log", "Warehouse Management", "Daily Summary"])

with tab1:
    st.subheader("Current Inventory")
    if df.empty:
        st.info("No coils yet — add some in Warehouse Management")
    else:
        st.dataframe(df)

with tab3:
    st.subheader("Receive New Coils")
    with st.form("receive_form"):
        material = st.selectbox("Material", COIL_MATERIALS)
        count = st.number_input("Number of Coils", min_value=1, value=1)
        footage = st.number_input("Footage per Coil", value=3000.0)
        location = st.selectbox("Location", LOCATIONS)
        if st.form_submit_button("Add Coils"):
            new_rows = []
            base = material.split()[0][1:]
            for i in range(count):
                coil_id = f"{base}-{datetime.now().strftime('%m%d')}-{str(i+1).zfill(3)}"
                new_rows.append([coil_id, material, footage, location, "Active"])
            new_df = pd.DataFrame(new_rows, columns=df.columns)
            st.session_state.df = pd.concat([df, new_df], ignore_index=True)
            save_inventory()
            st.success(f"Added {count} coil(s)!")
            st.rerun()

    st.divider()
    st.dataframe(df if not df.empty else "No coils yet")

with tab2:
    st.info("Production log coming next")

with tab4:
    st.info("Summary coming soon")
