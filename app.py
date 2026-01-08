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

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

def send_email_to_admin(client, order_no, pdf_bytes):
    # --- CONFIGURATION ---
    SENDER_EMAIL = "internal.mjp@gmail.com"
    SENDER_PASSWORD = "jxsajugwtbukgdwb" # Not your login password, a generated 'App Password'
    ADMIN_EMAIL = "tmilazi@gmail.com"
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587

    # Create Message
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = ADMIN_EMAIL
    msg['Subject'] = f"New Production Order: {order_no} - {client}"

    body = f"Attached is the Production & Picking Ticket for Order #{order_no} ({client})."
    msg.attach(MIMEText(body, 'plain'))

    # Attach PDF
    part = MIMEApplication(pdf_bytes, Name=f"Order_{order_no}.pdf")
    part['Content-Disposition'] = f'attachment; filename="Order_{order_no}.pdf"'
    msg.attach(part)

    # Send Process
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"Email failed: {e}")
        return False

# --- LOW STOCK ALERT STYLING ---
st.markdown("""
<style>
.low-stock-banner {
    background-color: #FFB74D;  /* Soft amber */
    padding: 15px;
    border-radius: 8px;
    border-left: 6px solid #FF8F00;
    margin-bottom: 20px;
}
.low-stock-text {
    color: #000000;  /* Bold black */
    font-weight: bold;
    font-size: 18px;
}
.low-stock-item {
    color: #000000;
    font-weight: bold;
}
.low-stock-row {
    background-color: #FFF9C4 !important;  /* Light yellow */
    font-weight: bold;
    color: #000000 !important;
}
</style>
""", unsafe_allow_html=True)
# --- PAGE CONFIG ---
st.set_page_config(page_title="MJP Floors Pulse", layout="wide")
st.title("🏭 MJP Floors Pulse - Production & Inventory")

# --- SIZE MAP ---
SIZE_DISPLAY = {
    "1#": 12.0,
    "#2": 13.5,
    "#3": 14.75,
    "#4": 16.25,
    "#5": 18.0,
    "#6": 20.0,
    "#7": 23.0,
    "#8": 26.0,
    "#9": 29.5,
    "#10": 32.5,
    "#11": 36.0,
    "#12": 39.25,
    "#13": 42.25,
    "#14": 46.5,
    "#15": 49.5,
    "#16": 52.75,
    "#17": 57,
    "#18": 60.25,
    "#19": 63.25,
    "#20": 66.5,
    "#21": 69.75,
    "#22": 72.75,
    "#23": 76,
    "#24": 79.25,
    "#25": 82.5,
    "#26": 85.5,
    "#27": 88.5,
    "#28": 92,
    "#29": 95,
    "#30": 98.25,
    "#31": 101.5,
    "#32": 104.5,
    "#33": 107.75,
}
SIZE_MAP = {k.replace("#", "Size "): v for k, v in SIZE_DISPLAY.items()}

# --- MATERIALS FOR COILS ---
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

# --- MATERIALS FOR ROLLS ---
ROLL_MATERIALS = [
    "RPR .016 Smooth Aluminum",
    "RPR .016 Stucco Aluminum",
    "RPR .020 Smooth Aluminum",
    "RPR .020 Stucco Aluminum",
    "RPR .024 Smooth Aluminum",
    "RPR .024 Stucco Aluminum",
    "RPR .032 Smooth Aluminum",
    "RPR .032 Stucco Aluminum",
    ".010 Smooth Stainless Steel",
    ".010 Stucco Stainless Steel",
    ".016 Smooth Stainless Steel",
    ".016 Stucco Stainless Steel",
    ".020 Smooth Stainless Steel",
    ".020 Stucco Stainless Steel",
    ".016 Smooth Aluminum",
    ".016 Stucco Aluminum",
    ".020 Smooth Aluminum",
    ".020 Stucco Aluminum",
    ".024 Smooth Aluminum",
    ".024 Stucco Aluminum",
    ".032 Smooth Aluminum",
    ".032 Stucco Aluminum"
]

# --- LOW STOCK THRESHOLDS ---
LOW_STOCK_THRESHOLDS = {
    ".016 Smooth Aluminum": 6000.0,
    ".020 Stucco Aluminum": 6000.0,
    ".020 Smooth Aluminum": 3500.0,
    ".016 Stucco Aluminum": 2500.0,
    ".010 Stainless Steel Polythene": 2500.0,
    # Add roll thresholds if different
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

operator_name = st.session_state.username

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
            st.session_state.df = pd.DataFrame(columns=["Item_ID", "Material", "Footage", "Location", "Status", "Category"])
    except Exception as e:
        st.error(f"Could not connect to Google Sheet: {e}")
        st.session_state.df = pd.DataFrame(columns=["Item_ID", "Material", "Footage", "Location", "Status", "Category"])

df = st.session_state.df

# --- SAVE FUNCTION ---
def save_inventory():
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        inv_ws = sh.worksheet("Inventory")

        # Get current data first (for safety)
        current_data = inv_ws.get_all_values()

        # Prepare new data
        new_data = [df.columns.tolist()] + df.values.tolist()

        # Only clear and write if new data is valid
        if new_data and len(new_data) > 0:
            inv_ws.clear()  # Only clear if we have good data
            inv_ws.update('A1', new_data)
        else:
            st.error("No data to save — aborting to prevent wipe")
            # Restore from current_data if possible
            if len(current_data) > 1:
                inv_ws.update('A1', current_data)

    except Exception as e:
        st.error(f"Failed to save inventory: {e}")
        st.info("Your data was NOT cleared — safety mode prevented wipe")
# --- LOW STOCK CHECK & EMAIL ---
def check_low_stock_and_alert():
    low_materials = []
    for material in df['Material'].unique():
        total_footage = df[df['Material'] == material]['Footage'].sum()
        threshold = LOW_STOCK_THRESHOLDS.get(material, 1000.0)
        if total_footage < threshold:
            low_materials.append(f"{material}: {total_footage:.1f} ft (below {threshold} ft)")

    if low_materials:
        subject = "URGENT: Low Stock Alert - Reorder Required"
        body = "The following materials have fallen below minimum stock levels:\n\n" + \
               "\n".join(low_materials) + \
               "\n\nPlease place a reorder as soon as possible.\n\n" + \
               f"Generated automatically on {datetime.now().strftime('%Y-%m-%d %H:%M')}"

        try:
            msg = MIMEMultipart()
            msg['From'] = st.secrets["SMTP_EMAIL"]
            msg['To'] = st.secrets["ADMIN_EMAIL"]
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
            server.login(st.secrets["SMTP_EMAIL"], st.secrets["SMTP_PASSWORD"])
            server.send_message(msg)
            server.quit()
            st.success("⚠️ Low stock detected — reorder email sent to admin!")
        except Exception as e:
            st.error(f"Low stock detected but email failed: {e}")

# --- PRODUCTION LOG SAVE ---
def save_production_log(order_number, client_name, operator_name, deduction_details, box_usage):
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        log_ws = sh.worksheet("Production_Log")

        rows = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        boxes_str = "; ".join([f"{k}: {v}" for k, v in box_usage.items() if v > 0]) or "None"

        for line in deduction_details:
            rows.append([
                timestamp,
                operator_name,
                client_name,
                order_number,
                line["material"],
                line["display_size"],
                line["pieces"],
                line["waste"],
                line["items"],
                boxes_str,
                line["total_used"]
            ])

        log_ws.append_rows(rows)
    except Exception as e:
        st.warning(f"Could not save to production log: {e}")

# --- AUDIT LOG ---
def log_action(action, details=""):
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        log_ws = sh.worksheet("Audit_Log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_ws.append_row([timestamp, st.session_state.username, action, details])
    except Exception as e:
        st.warning(f"Could not log action: {e}")

# --- PDF GENERATION ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Production Order Complete', 0, 1, 'C')
        self.ln(10)

def generate_production_pdf(order_number, client_name, operator_name, deduction_details, box_usage, extra_inch):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)
    
    pdf.cell(0, 10, f"Internal Order Number: {order_number}", 0, 1)
    pdf.cell(0, 10, f"Client: {client_name}", 0, 1)
    pdf.cell(0, 10, f"Completed by: {operator_name}", 0, 1)
    pdf.cell(0, 10, f"Extra Inch Allowance: {extra_inch} inch per piece", 0, 1)
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1)
    pdf.ln(10)
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Production Lines", 0, 1)
    pdf.set_font('Arial', '', 12)
    total_used = 0
    for line in deduction_details:
        pdf.cell(0, 10, f"Material: {line['material']}", 0, 1)
        pdf.cell(0, 10, f"Size: {line['display_size']} | Pieces: {line['pieces']} | Waste: {line['waste']:.1f} ft", 0, 1)
        pdf.cell(0, 10, f"Items Used: {line['items']}", 0, 1)
        pdf.cell(0, 10, f"Footage Used: {line['total_used']:.2f} ft", 0, 1)
        total_used += line['total_used']
        pdf.ln(5)
    
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Box Usage", 0, 1)
    pdf.set_font('Arial', '', 12)
    used_boxes = [f"{k}: {v}" for k, v in box_usage.items() if v > 0]
    if used_boxes:
        pdf.multi_cell(0, 10, "\n".join(used_boxes))
    else:
        pdf.cell(0, 10, "No boxes used", 0, 1)
    
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f"Total Footage Used: {total_used:.2f} ft", 0, 1)
    
    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer

# --- EMAIL FUNCTION ---
def send_production_pdf(pdf_buffer, order_number, client_name):
    try:
        msg = MIMEMultipart()
        msg['From'] = st.secrets["SMTP_EMAIL"]
        msg['To'] = st.secrets["ADMIN_EMAIL"]
        msg['Subject'] = f"Production Order {order_number} - {client_name}"

        body = f"Production order {order_number} for {client_name} has been completed by {st.session_state.username}.\n\nSee attached PDF for full details."
        msg.attach(MIMEText(body, 'plain'))

        filename = f"Production_Order_{order_number}_{datetime.now().strftime('%Y%m%d')}.pdf"
        part = MIMEBase('application', 'octet-stream')
        part.set_payload(pdf_buffer.read())
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
tab1, tab2, tab3, tab4, tab5 = st.tabs(["Dashboard", "Production Log", "Warehouse Management", "Daily Summary", "Audit Trail"])

with tab1:
    # 1. Dashboard Navigation
    # Dynamically get all categories present in your data (Coil, Roll, Mineral Wool, etc.)
    if not df.empty:
        available_categories = sorted(df['Category'].unique().tolist())
        # Add an "All Materials" option at the start
        view_options = ["All Materials"] + available_categories
        
        selected_view = st.radio(
            "Select Dashboard View", 
            view_options, 
            horizontal=True,
            help="Switch between Coils, Rolls, or other material categories"
        )
        
        # Filter data based on selection
        if selected_view == "All Materials":
            display_df = df
            st.subheader("📊 Global Material Pulse")
        else:
            display_df = df[df['Category'] == selected_view]
            st.subheader(f"📊 {selected_view} Inventory Pulse")

    if df.empty:
        st.info("No data available. Add inventory in the Warehouse tab.")
    else:
        # 2. DATA AGGREGATION (Filtered)
        summary_df = display_df.groupby(['Material', 'Category']).agg({
            'Footage': 'sum',
            'Item_ID': 'count'
        }).reset_index()
        summary_df.columns = ['Material', 'Type', 'Total_Footage', 'Unit_Count']

        # 3. TOP-LEVEL METRICS (Calculated based on current view)
        m1, m2, m3 = st.columns(3)
        current_total_ft = display_df['Footage'].sum()
        current_unit_count = len(display_df)
        unique_mats = len(summary_df)
        
        m1.metric("Selected Footage", f"{current_total_ft:,.1f} ft")
        m2.metric("Items in View", current_unit_count)
        m3.metric("Material Types", unique_mats)

        st.divider()

        # 4. THE PULSE GRID (with Dynamic Units)
        cols = st.columns(2)
        for idx, row in summary_df.iterrows():
            with cols[idx % 2]:
                mat = row['Material']
                ft = row['Total_Footage']
                units = row['Unit_Count']
                cat_type = row['Type'] # This is 'Coils', 'Fab Straps', etc.
                
                # Dynamic Unit Labeling
                if cat_type == "Coils" or cat_type == "Rolls":
                    unit_text = "FT"
                elif cat_type == "Fab Straps":
                    unit_text = "Bundles"
                elif cat_type == "Elbows":
                    unit_text = "Pcs"
                else:
                    unit_text = "Units"

                # Threshold/Health Logic
                limit = LOW_STOCK_THRESHOLDS.get(mat, 10.0 if cat_type == "Fab Straps" else 1000.0)
                
                if ft < limit:
                    status_color, status_text = "#FF4B4B", "🚨 REORDER REQUIRED"
                elif ft < (limit * 1.5):
                    status_color, status_text = "#FFA500", "⚠️ MONITOR CLOSELY"
                else:
                    status_color, status_text = "#00C853", "✅ STOCK HEALTHY"

                st.markdown(f"""
                <div style="background-color: #f9f9f9; padding: 20px; border-radius: 12px; 
                            border-left: 12px solid {status_color}; margin-bottom: 15px;">
                    <p style="color: #666; font-size: 12px; margin: 0; font-weight: bold;">{cat_type.upper()}</p>
                    <h3 style="margin: 5px 0;">{mat}</h3>
                    <h1 style="margin: 10px 0; color: {status_color};">{ft:,.1f} <span style="font-size: 18px;">{unit_text}</span></h1>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="font-weight: bold; color: {status_color};">{status_text}</span>
                        <span style="color: #888; font-size: 12px;">{units} separate IDs</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        # 5. INDIVIDUAL ITEM TABLE (Filtered)
        with st.expander(f"🔍 View {selected_view} Serial Numbers"):
            st.dataframe(
                display_df[['Item_ID', 'Category', 'Material', 'Footage', 'Location']].sort_values('Material'), 
                use_container_width=True, 
                hide_index=True
            )
with tab2:
    st.subheader("📋 Order Fulfillment & Production Log")
    
    # 1. Load available inventory for selection
    available_items = df[(df['Footage'] > 0) & (df['Status'] == 'Active')]

    if df.empty:
        st.info("Inventory is empty. Add materials in Warehouse Management first.")
    else:
        # Initialize session state for order lines
        if 'order_lines' not in st.session_state:
            st.session_state.order_lines = [{
                "source": "Cut from Material", 
                "size": "#2", 
                "qty": 1, 
                "sheet_length": 10.0, 
                "waste": 0.0, 
                "selected_ids": []
            }]

        # --- ORDER ENTRY SECTION ---
        for i, line in enumerate(st.session_state.order_lines):
            with st.container():
                st.markdown(f"**Item Line {i+1}**")
                c1, c2, c3, c4 = st.columns([1.5, 1.5, 1, 0.5])
                
                with c1:
                    line["source"] = st.selectbox("Source", ["Cut from Material", "Pull from Pre-made Stock"], key=f"src_{i}")
                
                with c2:
                    size_options = list(SIZE_DISPLAY.keys()) + ["Straight Sheet (ft)"]
                    line["size"] = st.selectbox("Size / Type", size_options, key=f"sz_{i}")
                
                with c3:
                    label = "Sheet Length (ft)" if line["size"] == "Straight Sheet (ft)" else "Pieces"
                    val_key = "sheet_length" if line["size"] == "Straight Sheet (ft)" else "qty"
                    line[val_key] = st.number_input(label, min_value=0.1 if "length" in label else 1.0, step=0.1 if "length" in label else 1.0, key=f"qty_len_{i}")
                
                with c4:
                    if st.button("🗑️", key=f"rm_line_{i}"):
                        st.session_state.order_lines.pop(i)
                        st.rerun()

                # Material Selection Logic
                if line["source"] == "Cut from Material":
                    # Show only Coils/Rolls for cutting
                    raw_options = available_items[available_items['Category'].isin(['Coil', 'Roll'])]
                    opt_list = [f"{r['Item_ID']} - {r['Material']} ({r['Footage']:.1f}ft @ {r['Location']})" for _, r in raw_options.iterrows()]
                    
                    line["selected_ids"] = st.multiselect("Select Material Source ID(s)", opt_list, key=f"sel_{i}")
                    line["waste"] = st.number_input("Waste (ft)", min_value=0.0, step=0.1, key=f"wst_{i}")
                    
                    # Footage Calculation Preview
                    if line["size"] == "Straight Sheet (ft)":
                        total_needed = line["sheet_length"] + line["waste"]
                    else:
                        # Standard sizes use the SIZE_DISPLAY multiplier (if available)
                        multiplier = SIZE_DISPLAY.get(line["size"], 1.0)
                        total_needed = (line["qty"] * multiplier) + line["waste"]
                    
                    st.caption(f"📏 Estimated Footage to deduct: **{total_needed:.2f} ft**")
                else:
                    st.success("✅ Pulling from finished stock. No raw material will be deducted.")
                
                st.divider()

        # Add Line Button
        if st.button("➕ Add Another Item to Order"):
            st.session_state.order_lines.append({
                "source": "Cut from Material", "size": "#2", "qty": 1, 
                "sheet_length": 10.0, "waste": 0.0, "selected_ids": []
            })
            st.rerun()

        # --- SUBMISSION ---
        st.markdown("### Finalize Order")
        col_cl, col_ord, col_op = st.columns(3)
        with col_cl: client = st.text_input("Client Name", placeholder="e.g. ABC Insulation")
        with col_ord: order_no = st.text_input("Order #", placeholder="e.g. PO-998")
        with col_op: operator = st.text_input("Operator Name")

        if st.button("🚀 Process & Log Order"):
            if not client or not order_no or not operator:
                st.error("Please fill in Client, Order #, and Operator.")
            else:
                # Logic to process deductions
                for line in st.session_state.order_lines:
                    if line["source"] == "Cut from Material" and line["selected_ids"]:
                        # 1. Calculate Footage
                        if line["size"] == "Straight Sheet (ft)":
                            deduction = line["sheet_length"] + line["waste"]
                        else:
                            deduction = (line["qty"] * SIZE_DISPLAY.get(line["size"], 1.0)) + line["waste"]
                        
                        # 2. Update the first ID selected (simplified deduction logic)
                        target_id = line["selected_ids"][0].split(" - ")[0]
                        df.loc[df['Item_ID'] == target_id, 'Footage'] -= deduction
                
                save_inventory()
                # Clear session state for next order
                st.session_state.order_lines = [{"source": "Cut from Material", "size": "#2", "qty": 1, "sheet_length": 10.0, "waste": 0.0, "selected_ids": []}]
                st.success(f"Order {order_no} for {client} processed and inventory updated!")
                st.balloons()
                st.rerun()                            
with tab3:
    st.subheader("📦 Smart Inventory Receiver")
    
    # 1. High-Level Category Selection
    cat_choice = st.radio(
        "What are you receiving?", 
        ["Coils", "Rolls", "Elbows", "Fab Straps", "Mineral Wool", "Other"],
        horizontal=True
    )

    with st.form("smart_receive_form", clear_on_submit=True):
        # --- DYNAMIC MATERIAL BUILDER ---
        if cat_choice == "Elbows":
            col1, col2 = st.columns(2)
            with col1:
                angle = st.selectbox("Angle", ["45°", "90°"])
            with col2:
                size = st.number_input("Size (1-60)", min_value=1, max_value=60, value=1)
            material = f"{angle} Elbow - Size {size}"
            qty_val = 1.0  # Each Elbow ID represents 1 piece
            unit_label = "Pieces"

        elif cat_choice == "Fab Straps":
            col1, col2 = st.columns(2)
            with col1:
                gauge = st.selectbox("Gauge", [".015", ".020"])
            with col2:
                size = st.number_input("Size (1-50)", min_value=1, max_value=50, value=1)
            material = f"Fab Strap {gauge} - Size {size}"
            qty_val = 1.0  # Each ID represents 1 bundle
            unit_label = "Bundles"

        elif cat_choice == "Mineral Wool":
            col1, col2 = st.columns(2)
            with col1:
                p_size = st.text_input("Pipe Size", placeholder="e.g. 2-inch")
            with col2:
                thick = st.text_input("Thickness", placeholder="e.g. 1.5-inch")
            material = f"Min Wool: {p_size} x {thick}"
            qty_val = 1.0 # Each ID represents 1 section
            unit_label = "Sections"

        elif cat_choice == "Other":
            category_name = st.text_input("New Category Name", placeholder="e.g. Insulation")
            material = st.text_input("Material Description", placeholder="e.g. Fiberglass Roll")
            qty_val = st.number_input("Qty/Footage per item", min_value=0.1, value=1.0)
            unit_label = "Units"
        
        else: # Coils and Rolls (Keep the footage input for these)
            material = st.selectbox("Material Type", COIL_MATERIALS if cat_choice == "Coils" else ROLL_MATERIALS)
            qty_val = st.number_input("Footage per Item", min_value=0.1, value=3000.0 if cat_choice == "Coils" else 100.0)
            unit_label = "Footage"

        st.markdown("---")
        
        # --- SIMPLIFIED COMMON FIELDS ---
        # For Straps/Elbows, this is now the ONLY number they enter.
        item_count = st.number_input(f"How many {unit_label} are you receiving?", min_value=1, value=1, step=1)
        # Location Selector (Rack vs Floor)
        st.markdown("#### Location Selector")
        loc_type = st.radio("Storage Type", ["Rack System", "Floor / Open Space"], horizontal=True, key="loc_radio")
        if loc_type == "Rack System":
            l1, l2, l3 = st.columns(3)
            with l1: bay = st.number_input("Bay", min_value=1, value=1)
            with l2: sec = st.selectbox("Section", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
            with l3: lvl = st.number_input("Level", min_value=1, value=1)
            gen_loc = f"{bay}{sec}{lvl}"
        else:
            floor_zone = st.text_input("Floor Zone Name", value="FLOOR")
            gen_loc = floor_zone.strip().upper()

        st.info(f"📍 **Assigned Location:** {gen_loc}")

        # ID Generation
        prefix = cat_choice.upper()[:4]
        starting_id = st.text_input("Starting ID", value=f"{prefix}-1001")
        operator = st.text_input("Receiving Operator")

        submitted = st.form_submit_button("📥 Add to Inventory")

    # --- SAVE LOGIC ---
    if submitted:
        if not operator:
            st.error("Operator name is required.")
        else:
            try:
                parts = starting_id.strip().upper().split("-")
                base = "-".join(parts[:-1])
                start_num = int(parts[-1])
                
                new_entries = []
                for i in range(item_count):
                    new_id = f"{base}-{start_num + i}"
                    new_entries.append({
                        "Item_ID": new_id,
                        "Material": material,
                        "Footage": qty_val, # For Straps, this stores the bundle count
                        "Location": gen_loc,
                        "Status": "Active",
                        "Category": cat_choice if cat_choice != "Other" else category_name
                    })
                
                st.session_state.df = pd.concat([df, pd.DataFrame(new_entries)], ignore_index=True)
                save_inventory()
                st.success(f"Successfully added {item_count} items to {gen_loc}!")
                st.rerun()
            except:
                st.error("ID must end with a number (e.g., STRAP-101)")

    st.divider()
    
    # --- MOVE ITEM SECTION ---
    st.markdown("### 🚚 Move Item")
    if not df.empty:
        move_id = st.selectbox("Select Item ID to Move", df['Item_ID'].unique())
        new_move_loc = st.text_input("New Location (Rack or Floor)")
        if st.button("Confirm Move"):
            df.loc[df['Item_ID'] == move_id, 'Location'] = new_move_loc.strip().upper()
            save_inventory()
            st.success(f"Item {move_id} moved to {new_move_loc}")
            st.rerun()
with tab4:
    st.subheader("📊 Production Summary & Insights")

    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        log_ws = sh.worksheet("Production_Log")
        log_records = log_ws.get_all_records()
        
        if not log_records:
            st.info("No production recorded yet — complete your first order to see stats!")
        else:
            log_df = pd.DataFrame(log_records)
            log_df['Timestamp'] = pd.to_datetime(log_df['Timestamp'])
            log_df['Date'] = log_df['Timestamp'].dt.date
            log_df['Total_Used_FT'] = pd.to_numeric(log_df['Total_Used_FT'], errors='coerce')
            log_df['Waste_FT'] = pd.to_numeric(log_df['Waste_FT'], errors='coerce')
            log_df['Pieces'] = pd.to_numeric(log_df['Pieces'], errors='coerce')

            # Time Period Selector
            st.markdown("#### Select Time Period")
            period = st.selectbox("View", ["Today", "Last 7 Days", "This Month", "This Year", "Year to Date", "All Time"], key="summary_period")

            now = datetime.now()
            if period == "Today":
                filtered = log_df[log_df['Date'] == now.date()]
                title = "Today's Production"
            elif period == "Last 7 Days":
                filtered = log_df[log_df['Timestamp'] >= now - pd.Timedelta(days=7)]
                title = "Last 7 Days"
            elif period == "This Month":
                filtered = log_df[log_df['Timestamp'].dt.month == now.month]
                title = f"{now.strftime('%B %Y')}"
            elif period == "This Year":
                filtered = log_df[log_df['Timestamp'].dt.year == now.year]
                title = str(now.year)
            elif period == "Year to Date":
                filtered = log_df[log_df['Timestamp'] >= datetime(now.year, 1, 1)]
                title = f"YTD {now.year}"
            else:
                filtered = log_df
                title = "All Time"

            if filtered.empty:
                st.info(f"No production in {period.lower()} yet.")
            else:
                st.markdown(f"### {title}")

                # Key Metrics
                col1, col2, col3, col4 = st.columns(4)
                total_footage = filtered['Total_Used_FT'].sum()
                total_waste = filtered['Waste_FT'].sum()
                total_pieces = filtered['Pieces'].sum()
                efficiency = ((total_footage - total_waste) / total_footage * 100) if total_footage > 0 else 0

                col1.metric("Total Footage Used", f"{total_footage:.1f} ft")
                col2.metric("Total Waste", f"{total_waste:.1f} ft")
                col3.metric("Total Pieces Produced", int(total_pieces))
                col4.metric("Efficiency", f"{efficiency:.1f}%")

                # Group By Selector
                st.markdown("#### Group Insights By")
                group_options = st.multiselect(
                    "Select grouping (add multiple for combined view)",
                    ["Material", "Client", "Size"],
                    default=["Material"]
                )

                if not group_options:
                    st.warning("Select at least one grouping option")
                else:
                    group_summary = filtered.groupby(group_options).agg(
                        Total_Footage=('Total_Used_FT', 'sum'),
                        Total_Waste=('Waste_FT', 'sum'),
                        Total_Pieces=('Pieces', 'sum')
                    ).round(1)
                    group_summary['Efficiency_%'] = ((group_summary['Total_Footage'] - group_summary['Total_Waste']) / group_summary['Total_Footage'] * 100).round(1)
                    group_summary = group_summary.sort_values('Total_Footage', ascending=False)

                    st.markdown(f"### Breakdown by {', '.join(group_options)}")
                    st.dataframe(group_summary, use_container_width=True)

                    # Labeled Bar Chart
                    st.markdown(f"### Top by Footage Used")
                    chart_df = group_summary['Total_Footage'].head(15).reset_index()
                    if len(group_options) == 1:
                        chart_df['Label'] = chart_df[group_options[0]].astype(str)
                    else:
                        chart_df['Label'] = chart_df[group_options].astype(str).agg(' - '.join, axis=1)
                    st.bar_chart(chart_df.set_index('Label')['Total_Footage'])

                # All Orders Table
                st.markdown("### All Orders")
                display = filtered[['Timestamp', 'Operator', 'Client', 'Order_Number', 'Material', 'Size', 'Pieces', 'Waste_FT', 'Coils_Used']].copy()
                display['Timestamp'] = display['Timestamp'].dt.strftime('%Y-%m-%d %H:%M')
                display = display.sort_values('Timestamp', ascending=False)
                st.dataframe(display, use_container_width=True)

    except Exception as e:
        st.error(f"Could not load production log: {e}")
        st.info("Make sure you have a 'Production_Log' tab with correct headers.")

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
