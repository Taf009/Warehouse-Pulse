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
    "Size 13": 42.3,
    "Size 14": 46,
    "Size 15": 49.5,
}
    # Add more sizes as needed
}

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

        st.dataframe(summary)

        # Individual Coils
        st.markdown("### Individual Coils")
        st.dataframe(df[['Coil_ID', 'Material', 'Footage', 'Location']].sort_values('Material'))

with tab2:
    st.subheader("Production Log - Multi-Size & Multi-Coil Orders")

    available_coils = df[df['Footage'] > 0]
    if available_coils.empty:
        st.info("No coils with footage available for production.")
    else:
        with st.form("production_form", clear_on_submit=True):
            st.markdown("#### Global Order Details")
            client_name = st.text_input("Client Name")
            order_number = st.text_input("Internal Order Number")
            operator_name = st.text_input("Your Name (who is completing this order)")

            st.markdown("#### Global Coils for This Order (used for all sizes unless overridden)")
            coil_options = [f"{row['Coil_ID']} - {row['Material']} ({row['Footage']:.1f} ft @ {row['Location']})" 
                            for _, row in available_coils.iterrows()]
            global_coils = st.multiselect("Select Coils (for entire order)", coil_options)

            st.markdown("#### Machine Allowance")
            extra_inch = st.number_input("Extra Inch Allowance per Piece (for machine room)", min_value=0.0, value=0.5, step=0.1)

            st.markdown("#### Production Lines (Add multiple sizes)")
            # Session state for lines
            if 'production_lines' not in st.session_state:
                st.session_state.production_lines = []

            for i, line in enumerate(st.session_state.production_lines):
                with st.container():
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        line["size"] = st.selectbox(f"Size {i+1}", list(SIZE_MAP.keys()), key=f"size_{i}")
                    with col2:
                        line["pieces"] = st.number_input(f"Pieces {i+1}", min_value=1, value=line["pieces"], key=f"pieces_{i}")
                    with col3:
                        line["waste"] = st.number_input(f"Waste ft {i+1}", min_value=0.0, value=line["waste"], key=f"waste_{i}")

                    # Optional override for coils
                    with st.expander(f"Override Coils for Size Line {i+1} (optional)"):
                        line["override_coils"] = st.multiselect(f"Coils for this line (overrides global)", coil_options, default=line.get("override_coils", []), key=f"override_coils_{i}")

            if st.button("➕ Add Size Line"):
                st.session_state.production_lines.append({"size": list(SIZE_MAP.keys())[0], "pieces": 1, "waste": 0.0, "override_coils": []})
                st.rerun()

            st.markdown("#### Box Usage")
            box_types = ["Small Metal Box", "Big Metal Box", "Small Elbow Box", "Medium Elbow Box", "Large Elbow Box"]
            box_usage = {}
            for box in box_types:
                box_usage[box] = st.number_input(box, min_value=0, value=0, step=1, key=f"box_{box}")

            submitted = st.form_submit_button("Complete Order & Send PDF")

            if submitted:
                if not client_name or not order_number or not operator_name:
                    st.error("Client Name, Order Number, and Your Name are required")
                else:
                    total_used = 0
                    deduction_details = []

                    for line in st.session_state.production_lines:
                        if line["pieces"] > 0:
                            coils_to_use = line["override_coils"] if line["override_coils"] else global_coils
                            if not coils_to_use:
                                st.error(f"Select coils for size line (global or override)")
                                st.stop()

                            inches_per_piece = SIZE_MAP[line["size"]] + extra_inch
                            used_without_waste = line["pieces"] * inches_per_piece / 12
                            line_total = used_without_waste + line["waste"]
                            total_used += line_total

                            selected_coil_ids = [c.split(" - ")[0] for c in coils_to_use]
                            deduction_details.append({
                                "size": line["size"],
                                "pieces": line["pieces"],
                                "waste": line["waste"],
                                "total_used": line_total,
                                "coils": ", ".join(selected_coil_ids)
                            })

                            # Even split deduction
                            per_coil = line_total / len(selected_coil_ids)
                            for coil_id in selected_coil_ids:
                                current = df.loc[df['Coil_ID'] == coil_id, 'Footage'].values[0]
                                if per_coil > current:
                                    st.error(f"Not enough footage on {coil_id}")
                                    st.stop()
                                df.loc[df['Coil_ID'] == coil_id, 'Footage'] -= per_coil

                    save_inventory()

                    pdf_buffer = generate_production_pdf(order_number, client_name, operator_name, deduction_details, box_usage)

                    if send_production_pdf(pdf_buffer, order_number, client_name):
                        st.success(f"Order {order_number} completed by {operator_name}! PDF sent.")
                    else:
                        st.warning("Logged but email failed.")

                    st.session_state.production_lines = []
                    st.balloons()
                    st.rerun()
