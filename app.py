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
import os

# --- PAGE CONFIG ---
st.set_page_config(page_title="Coil & Inventory Pulse", layout="wide")
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

ROLLED_METAL_MATERIALS = [m for m in COIL_MATERIALS if "Aluminum" in m]  # Same as aluminum coils

MINERAL_WOOL_SIZES = [f"Mineral Wool Size {i}" for i in range(1, 61)]

LOCATIONS = ["Rack A1", "Rack A2", "Rack B1", "Rack B2", "Floor Zone C", "Receiving Dock"]

SIZE_MAP = {
    "Size 7": 23.0, "Size 5": 18.0, "Size 10": 30.0, "Size 3": 12.0
    # Add more as needed
}

LOW_STOCK_FT = 500

# --- GOOGLE SHEETS CONNECTION ---
SHEET_URL = st.secrets["SHEET_URL"]
gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
sh = gc.open_by_url(SHEET_URL)
inv_ws = sh.worksheet("Inventory")
log_ws = sh.worksheet("Log")

# Load data
try:
    df = pd.DataFrame(inv_ws.get_all_records())
    if df.empty:
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

# --- PDF GENERATION ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Production Order Complete', 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def generate_pdf(order_number, client_name, material, coil_id, size, pieces, used_ft, waste_ft, remaining_ft, timestamp):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)
    
    pdf.cell(0, 10, f"Order Number: {order_number}", 0, 1)
    pdf.cell(0, 10, f"Client: {client_name}", 0, 1)
    pdf.cell(0, 10, f"Date: {timestamp.strftime('%Y-%m-%d %H:%M')}", 0, 1)
    pdf.ln(5)
    
    pdf.cell(0, 10, f"Material: {material}", 0, 1)
    pdf.cell(0, 10, f"Coil ID: {coil_id}", 0, 1)
    pdf.cell(0, 10, f"Size Produced: {size}", 0, 1)
    pdf.cell(0, 10, f"Pieces: {pieces}", 0, 1)
    pdf.cell(0, 10, f"Footage Used: {used_ft:.2f} ft (incl. {waste_ft:.2f} ft waste)", 0, 1)
    pdf.cell(0, 10, f"Remaining on Coil: {remaining_ft:.2f} ft", 0, 1)
    
    pdf_output = io.BytesIO()
    pdf.output(pdf_output)
    pdf_output.seek(0)
    return pdf_output

# --- EMAIL SENDING ---
def send_pdf_email(pdf_bytes, order_number, client_name):
    try:
        msg = MIMEMultipart()
        msg['From'] = st.secrets["SMTP_EMAIL"]
        msg['To'] = st.secrets["ADMIN_EMAIL"]
        msg['Subject'] = f"Production Order {order_number} Complete - {client_name}"

        body = f"Production order {order_number} for {client_name} has been completed.\nSee attached PDF for details."
        msg.attach(MIMEText(body, 'plain'))

        filename = f"Order_{order_number}_{datetime.now().strftime('%Y%m%d')}.pdf"
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_bytes.read())
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f"attachment; filename= {filename}")
        msg.attach(part)

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(st.secrets["SMTP_EMAIL"], st.secrets["SMTP_PASSWORD"])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

# --- TABS ---
tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Production Log", "Warehouse Management", "Daily Summary"])

with tab1:
    st.subheader("Live Inventory")
    if df.empty:
        st.info("No items yet – add in Warehouse Management")
    else:
        st.dataframe(df[df['Footage'] > 0][['Coil_ID', 'Material', 'Footage', 'Location']])

with tab2:
    st.subheader("Log Production (Coils Only for Now)")
    available = df[(df['Material'].isin(COIL_MATERIALS)) & (df['Footage'] > 0)]
    if available.empty:
        st.info("No coils available")
    else:
        with st.form("production_form"):
            coil_options = [f"{r['Coil_ID']} - {r['Material']} ({r['Footage']:.0f}ft @ {r['Location']})" for _, r in available.iterrows()]
            selected = st.selectbox("Select Coil", coil_options)
            coil_id = selected.split(" - ")[0]
            
            size = st.selectbox("Size Produced", list(SIZE_MAP.keys()))
            pieces = st.number_input("Pieces", min_value=1)
            waste = st.number_input("Waste (ft)", min_value=0.0)
            client = st.text_input("Client Name")
            order_num = st.text_input("Internal Order Number")
            
            if st.form_submit_button("Complete Order & Send PDF to Admin"):
                ft_used = (pieces * SIZE_MAP[size] / 12) + waste
                current_ft = df.loc[df['Coil_ID'] == coil_id, 'Footage'].values[0]
                if ft_used > current_ft:
                    st.error("Not enough footage!")
                else:
                    remaining = current_ft - ft_used
                    df.loc[df['Coil_ID'] == coil_id, 'Footage'] = remaining
                    material = df.loc[df['Coil_ID'] == coil_id, 'Material'].values[0]
                    location = df.loc[df['Coil_ID'] == coil_id, 'Location'].values[0]
                    
                    record_action("Cut", coil_id, material, pieces * (SIZE_MAP[size] / 12), waste, location, client, order_num)
                    save_inventory()
                    
                    pdf_bytes = generate_pdf(order_num, client, material, coil_id, size, pieces, ft_used, waste, remaining, datetime.now())
                    
                    if send_pdf_email(pdf_bytes, order_num, client):
                        st.success(f"Order {order_num} completed! PDF sent to {st.secrets['ADMIN_EMAIL']}")
                    st.rerun()

# Add other tabs (Warehouse Management for receiving/moving, Daily Summary) similar to before...
# For brevity, I'll add basic versions – let me know if you need them expanded

with tab3:
    st.subheader("Receive New Coils (Example)")
    # Add receive form here – similar to previous versions

with tab4:
    st.subheader("Daily Summary")
    # Add summary logic here
