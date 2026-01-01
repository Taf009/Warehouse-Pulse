import streamlit as st
import pandas as pd
import gspread
from datetime import datetime
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import io

# --- CONFIG ---
st.set_page_config(page_title="Warehouse Pulse", layout="wide")
st.title("🏭 Warehouse Pulse Check")

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

SIZE_MAP = {"Size 7": 23.0, "Size 5": 18.0, "Size 10": 30.0, "Size 3": 12.0}

# --- GOOGLE SHEETS ---
gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
sh = gc.open_by_url(st.secrets["SHEET_URL"])
inv_ws = sh.worksheet("Inventory")
log_ws = sh.worksheet("Log")

# Load data
try:
    df = pd.DataFrame(inv_ws.get_all_records())
    if df.empty or 'Coil_ID' not in df.columns:
        df = pd.DataFrame(columns=["Coil_ID", "Material", "Footage", "Location", "Status"])
except:
    df = pd.DataFrame(columns=["Coil_ID", "Material", "Footage", "Location", "Status"])

try:
    log_df = pd.DataFrame(log_ws.get_all_records())
    if "Timestamp" in log_df.columns:
        log_df["Timestamp"] = pd.to_datetime(log_df["Timestamp"])
except:
    log_df = pd.DataFrame(columns=["Timestamp", "Action", "Coil_ID", "Material", "Value", "Waste_FT", "Location", "Client_Name", "Order_Number"])

def save_inventory():
    inv_ws.clear()
    inv_ws.update([df.columns.tolist()] + df.values.tolist())

def save_log():
    log_ws.clear()
    log_ws.update([log_df.columns.tolist()] + log_df.values.tolist())

def record_action(action, coil_id="", material="", value=0, waste=0, loc="", client="", order=""):
    new_row = {
        "Timestamp": datetime.now(),
        "Action": action,
        "Coil_ID": coil_id,
        "Material": material,
        "Value": value,
        "Waste_FT": waste,
        "Location": loc,
        "Client_Name": client,
        "Order_Number": order
    }
    global log_df
    log_df = pd.concat([log_df, pd.DataFrame([new_row])], ignore_index=True)
    save_log()

# --- PDF & EMAIL (same as before) ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Production Order Complete', 0, 1, 'C')
        self.ln(10)

def generate_pdf(order_number, client_name, material, coil_id, size, pieces, used_ft, waste_ft, remaining_ft):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f"Order: {order_number} | Client: {client_name}", 0, 1)
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1)
    pdf.ln(5)
    pdf.cell(0, 10, f"Material: {material} | Coil: {coil_id}", 0, 1)
    pdf.cell(0, 10, f"Size: {size} | Pieces: {pieces}", 0, 1)
    pdf.cell(0, 10, f"Used: {used_ft:.2f} ft (waste {waste_ft:.2f} ft)", 0, 1)
    pdf.cell(0, 10, f"Remaining: {remaining_ft:.2f} ft", 0, 1)
    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer

def send_pdf_email(pdf_buffer, order_number, client_name):
    try:
        msg = MIMEMultipart()
        msg['From'] = st.secrets["SMTP_EMAIL"]
        msg['To'] = st.secrets["ADMIN_EMAIL"]
        msg['Subject'] = f"Order {order_number} Complete - {client_name}"
        msg.attach(MIMEText(f"Order {order_number} completed. See attached PDF.", 'plain'))

        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_buffer.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename=Order_{order_number}.pdf")
        msg.attach(part)

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(st.secrets["SMTP_EMAIL"], st.secrets["SMTP_PASSWORD"])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Email error: {e}")
        return False

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Production Log", "Warehouse Management", "Daily Summary"])

with tab1:
    st.subheader("Current Inventory")
    if df.empty:
        st.info("No coils yet — add some in Warehouse Management")
    else:
        st.dataframe(df[['Coil_ID', 'Material', 'Footage', 'Location']])

with tab2:
    st.subheader("Log Production Cut")
    available = df[df['Footage'] > 0]
    if available.empty:
        st.info("No coils with footage")
    else:
        with st.form("production"):
            coil_options = [f"{r.Coil_ID} - {r.Material} ({r.Footage:.0f}ft @ {r.Location})" for _, r in available.iterrows()]
            selected = st.selectbox("Select Coil", coil_options)
            coil_id = selected.split(" - ")[0]
            size = st.selectbox("Size Produced", list(SIZE_MAP.keys()))
            pieces = st.number_input("Pieces", min_value=1)
            waste = st.number_input("Waste (ft)", min_value=0.0)
            client = st.text_input("Client Name")
            order_num = st.text_input("Internal Order Number")

            if st.form_submit_button("Complete Order & Send PDF"):
                used_ft = (pieces * SIZE_MAP[size] / 12) + waste
                current = df.loc[df['Coil_ID'] == coil_id, 'Footage'].values[0]
                if used_ft > current:
                    st.error("Not enough footage")
                else:
                    remaining = current - used_ft
                    df.loc[df['Coil_ID'] == coil_id, 'Footage'] = remaining
                    material = df.loc[df['Coil_ID'] == coil_id, 'Material'].values[0]
                    location = df.loc[df['Coil_ID'] == coil_id, 'Location'].values[0]
                    record_action("Cut", coil_id, material, used_ft - waste, waste, location, client, order_num)
                    save_inventory()
                    pdf = generate_pdf(order_num, client, material, coil_id, size, pieces, used_ft, waste, remaining)
                    if send_pdf_email(pdf, order_num, client):
                        st.success(f"Order {order_num} complete! PDF sent.")
                    st.rerun()

with tab3:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Receive New Coils")
        with st.form("receive"):
            material = st.selectbox("Material", COIL_MATERIALS)
            count = st.number_input("Number of Coils", min_value=1, value=1)
            footage = st.number_input("Footage per Coil", value=3000.0)
            location = st.selectbox("Location", LOCATIONS)
            submitted = st.form_submit_button("Add Coils")
            if submitted:
                new_coils = []
                for i in range(count):
                    coil_id = f"{material[:3].upper()}-{datetime.now().strftime('%m%d')}-{i+1:03d}"
                    new_coils.append({"Coil_ID": coil_id, "Material": material, "Footage": footage, "Location": location, "Status": "Active"})
                global df
                df = pd.concat([df, pd.DataFrame(new_coils)], ignore_index=True)
                save_inventory()
                record_action("Receive", material=material, value=count*footage, loc=location)
                st.success(f"Added {count} coil(s)!")
                st.rerun()

    with col2:
        st.subheader("Move Coil")
        if not df.empty:
            with st.form("move"):
                coil = st.selectbox("Coil ID", df['Coil_ID'])
                new_loc = st.selectbox("New Location", LOCATIONS)
                if st.form_submit_button("Move"):
                    old_loc = df.loc[df['Coil_ID'] == coil, 'Location'].values[0]
                    df.loc[df['Coil_ID'] == coil, 'Location'] = new_loc
                    material = df.loc[df['Coil_ID'] == coil, 'Material'].values[0]
                    save_inventory()
                    record_action("Move", coil, material, loc=f"{old_loc} → {new_loc}")
                    st.success("Moved!")
                    st.rerun()

with tab4:
    st.subheader("Daily Summary")
    st.info("Coming soon — total used, waste, efficiency")
