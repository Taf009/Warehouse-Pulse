import streamlit as st
import pandas as pd
import gspread
from datetime import datetime

# --- PAGE CONFIG ---
st.set_page_config(page_title="Warehouse Pulse Check", layout="wide")
st.title("🏭 Warehouse Pulse Check - Production & Inventory")

# --- PREDEFINED MATERIALS ---
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
        st.error(f"Failed to save inventory: {e}")

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Production Log", "Warehouse Management", "Daily Summary"])

with tab1:
    st.subheader("Current Inventory Summary")

    if df.empty:
        st.info("No coils in inventory yet. Go to Warehouse Management to add some.")
    else:
        # Material Summary Table
        st.markdown("### 📊 Stock Summary by Material")
        summary = df.groupby('Material').agg(
            Coil_Count=('Coil_ID', 'count'),
            Total_Footage=('Footage', 'sum')
        ).reset_index()
        summary = summary.sort_values('Total_Footage', ascending=False)
        summary['Total_Footage'] = summary['Total_Footage'].round(1)

        st.dataframe(
            summary,
            column_config={
                "Material": "Material",
                "Coil_Count": st.column_config.NumberColumn("Number of Coils", format="%d"),
                "Total_Footage": st.column_config.NumberColumn("Total Footage (ft)", format="%.1f ft")
            },
            use_container_width=True,
            hide_index=True
        )

        # Individual Coils
        st.markdown("### Individual Coils")
        display_df = df[['Coil_ID', 'Material', 'Footage', 'Location']].copy()
        display_df['Footage'] = display_df['Footage'].round(1)
        st.dataframe(display_df.sort_values(['Material', 'Location']), use_container_width=True)

with tab3:
    st.subheader("Receive New Coils")
    with st.form("receive_coils_form", clear_on_submit=True):
        st.markdown("#### Add New Coil Shipment")

        material = st.selectbox("Material Type", COIL_MATERIALS)

        # Smart Location Generator
        st.markdown("#### Rack Location Generator (Unlimited)")
        col1, col2, col3 = st.columns(3)
        with col1:
            bay = st.number_input("Bay Number", min_value=1, value=1, step=1)
        with col2:
            section = st.selectbox("Section Letter", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        with col3:
            level = st.number_input("Level", min_value=1, value=1, step=1)

        generated_location = f"{bay}{section}{level}"
        st.info(f"**Generated Location Code:** {generated_location}")

        footage = st.number_input("Footage per Coil (ft)", min_value=0.1, value=3000.0)

        # Manual Coil ID Input with Sequencing
        st.markdown("#### Manual Coil ID Input")
        st.write("Enter the **full starting Coil ID** (including the number), e.g., `COIL-016-AL-SM-3000-01`")

        starting_id = st.text_input(
            "Starting Coil ID",
            value="COIL-016-AL-SM-3000-01",
            help="The app will increment only the last number (01 → 02 → 03 etc.)"
        )

        count = st.number_input("Number of Coils to Add", min_value=1, value=1, step=1)

        # Live preview of generated IDs
        if starting_id.strip() and count > 0:
            try:
                parts = starting_id.strip().upper().split("-")
                if len(parts) < 2 or not parts[-1].isdigit():
                    st.warning("Last part must be a number (e.g., -01)")
                else:
                    base_part = "-".join(parts[:-1])
                    start_num = int(parts[-1])

                    preview_ids = []
                    for i in range(count):
                        current_num = start_num + i
                        preview_ids.append(f"{base_part}-{str(current_num).zfill(2)}")

                    st.markdown("**Generated Coil IDs:**")
                    st.code("\n".join(preview_ids), language="text")
            except:
                st.warning("Invalid format — make sure the last part is a number")

        submitted = st.form_submit_button("🚀 Add Coils to Inventory")

        if submitted:
            if not starting_id.strip():
                st.error("Please enter a starting Coil ID")
                st.stop()

            try:
                parts = starting_id.strip().upper().split("-")
                base_part = "-".join(parts[:-1])
                start_num = int(parts[-1])

                new_coils = []
                for i in range(count):
                    current_num = start_num + i
                    coil_id = f"{base_part}-{str(current_num).zfill(2)}"

                    if coil_id in df['Coil_ID'].values:
                        st.error(f"Coil ID {coil_id} already exists!")
                        st.stop()

                    new_coils.append({
                        "Coil_ID": coil_id,
                        "Material": material,
                        "Footage": footage,
                        "Location": generated_location,
                        "Status": "Active"
                    })

                new_df = pd.concat([df, pd.DataFrame(new_coils)], ignore_index=True)
                st.session_state.df = new_df
                save_inventory()
                st.success(f"✅ Successfully added {count} coil(s) starting from {starting_id}!")
                st.balloons()
                st.rerun()

            except ValueError:
                st.error("The last part of the Coil ID must be a number (e.g., -01)")
            except Exception as e:
                st.error(f"Error: {e}")

    st.divider()
    st.subheader("Current Inventory Preview")
    if df.empty:
        st.info("No coils added yet")
    else:
        st.dataframe(df[['Coil_ID', 'Material', 'Footage', 'Location']], use_container_width=True)

with tab2:
    st.subheader("Production Log")
    st.info("Full production logging with automatic PDF email coming soon — add coils first!")

with tab4:
    st.subheader("Daily Summary")
    st.info("Daily usage, waste, and efficiency stats will appear once production starts.")
