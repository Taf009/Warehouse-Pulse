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

        # 4. THE PULSE GRID
        cols = st.columns(2)
        for idx, row in summary_df.iterrows():
            with cols[idx % 2]:
                mat = row['Material']
                ft = row['Total_Footage']
                units = row['Unit_Count']
                
                # Fetch threshold (defaults to 1000 if not found)
                limit = LOW_STOCK_THRESHOLDS.get(mat, 1000.0)
                
                # Health Logic
                if ft < limit:
                    status_color, status_text = "#FF4B4B", "🚨 REORDER REQUIRED"
                elif ft < (limit * 1.5):
                    status_color, status_text = "#FFA500", "⚠️ MONITOR CLOSELY"
                else:
                    status_color, status_text = "#00C853", "✅ STOCK HEALTHY"

                st.markdown(f"""
                <div style="background-color: #f9f9f9; padding: 20px; border-radius: 12px; 
                            border-left: 12px solid {status_color}; margin-bottom: 15px;">
                    <p style="color: #666; font-size: 12px; margin: 0; font-weight: bold;">{row['Type'].upper()}</p>
                    <h3 style="margin: 5px 0;">{mat}</h3>
                    <h1 style="margin: 10px 0; color: {status_color};">{ft:,.1f} <span style="font-size: 18px;">FT</span></h1>
                    <div style="display: flex; justify-content: space-between;">
                        <span style="font-weight: bold; color: {status_color};">{status_text}</span>
                        <span style="color: #888; font-size: 12px;">{units} units</span>
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
    st.subheader("Production Log - Multi-Size Orders")
    
    # Correctly filter available stock by Category
    available_coils = df[(df['Category'] == "Coil") & (df['Footage'] > 0)]
    available_rolls = df[(df['Category'] == "Roll") & (df['Footage'] > 0)]

    if available_coils.empty and available_rolls.empty:
        st.info("No coils or rolls with footage available for production. Add some in Warehouse Management.")
    else:
        # Initialize session state lines
        if 'coil_lines' not in st.session_state:
            st.session_state.coil_lines = [{"display_size": "#2", "pieces": 1, "waste": 0.0, "items": []}]
        if 'roll_lines' not in st.session_state:
            st.session_state.roll_lines = [{"display_size": "#2", "pieces": 1, "waste": 0.0, "items": []}]
        
        # --- COILS SECTION ---
        st.markdown("### Coils Production")
        if not available_coils.empty:
            # Create the list of options specifically for coils
            coil_options = [f"{row['Item_ID']} - {row['Material']} ({row['Footage']:.1f} ft @ {row['Location']})" 
                            for _, row in available_coils.iterrows()]
            
            for i in range(len(st.session_state.coil_lines)):
                line = st.session_state.coil_lines[i]
                with st.container():
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        line["display_size"] = st.selectbox(f"Coil Size {i+1}", list(SIZE_DISPLAY.keys()), index=list(SIZE_DISPLAY.keys()).index(line["display_size"]), key=f"coil_size_{i}")
                    with col2:
                        line["pieces"] = st.number_input(f"Coil Pieces {i+1}", min_value=0, value=line["pieces"], key=f"coil_pieces_{i}")
                    with col3:
                        line["waste"] = st.number_input(f"Coil Waste ft {i+1}", min_value=0.0, value=line["waste"], key=f"coil_waste_{i}")
                    with col4:
                        if st.button("Remove", key=f"remove_coil_line_{i}"):
                            st.session_state.coil_lines.pop(i)
                            st.rerun()

                    line["items"] = st.multiselect(f"Coils for size {i+1}", coil_options, default=line["items"], key=f"coil_items_select_{i}")

            if st.button("➕ Add Coil Size Line"):
                st.session_state.coil_lines.append({"display_size": "#2", "pieces": 1, "waste": 0.0, "items": []})
                st.rerun()
        else:
            st.info("No coils available in inventory.")

        # --- ROLLS SECTION ---
        st.markdown("### Rolls Production")
        if not available_rolls.empty:
            # Create the list of options specifically for rolls
            roll_options = [f"{row['Item_ID']} - {row['Material']} ({row['Footage']:.1f} ft @ {row['Location']})" 
                            for _, row in available_rolls.iterrows()]
            
            for i in range(len(st.session_state.roll_lines)):
                line = st.session_state.roll_lines[i]
                with st.container():
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        line["display_size"] = st.selectbox(f"Roll Size {i+1}", list(SIZE_DISPLAY.keys()), index=list(SIZE_DISPLAY.keys()).index(line["display_size"]), key=f"roll_size_{i}")
                    with col2:
                        line["pieces"] = st.number_input(f"Roll Pieces {i+1}", min_value=0, value=line["pieces"], key=f"roll_pieces_{i}")
                    with col3:
                        line["waste"] = st.number_input(f"Roll Waste ft {i+1}", min_value=0.0, value=line["waste"], key=f"roll_waste_{i}")
                    with col4:
                        if st.button("Remove", key=f"remove_roll_line_{i}"):
                            st.session_state.roll_lines.pop(i)
                            st.rerun()

                    line["items"] = st.multiselect(f"Rolls for size {i+1}", roll_options, default=line["items"], key=f"roll_items_select_{i}")

            if st.button("➕ Add Roll Size Line"):
                st.session_state.roll_lines.append({"display_size": "#2", "pieces": 1, "waste": 0.0, "items": []})
                st.rerun()
        else:
            st.info("No rolls available in inventory.")
            
        # ... (The rest of your form logic for Client Name, Order Number, and Submit remains the same)
        extra_inch = st.number_input("Extra Inch Allowance per Piece", min_value=0.0, value=0.5, step=0.1)

        with st.form("production_submit_form"):
            st.markdown("#### Order Details")
            client_name = st.text_input("Client Name")
            order_number = st.text_input("Internal Order Number")

            st.markdown("#### Box Usage")
            box_types = ["Small Metal Box", "Big Metal Box", "Small Elbow Box", "Medium Elbow Box", "Large Elbow Box"]
            box_usage = {}
            for box in box_types:
                box_usage[box] = st.number_input(box, min_value=0, value=0, step=1, key=f"box_{box}")

            submitted = st.form_submit_button("Complete Order & Send PDF")

            if submitted:
                if not client_name or not order_number:
                    st.error("Client Name and Order Number are required")
                else:
                    all_lines = []
                    has_production = False

                    # Coils
                    for line in st.session_state.coil_lines:
                        if line["pieces"] > 0:
                            has_production = True
                            if not line["items"]:
                                st.error(f"Select coils for coil size {line['display_size']}")
                                st.stop()
                            all_lines.append({"type": "Coil", **line})

                    # Rolls
                    for line in st.session_state.roll_lines:
                        if line["pieces"] > 0:
                            has_production = True
                            if not line["items"]:
                                st.error(f"Select rolls for roll size {line['display_size']}")
                                st.stop()
                            all_lines.append({"type": "Roll", **line})

                    if not has_production:
                        st.error("Enter pieces for at least one size line")
                    else:
                        total_used = 0
                        deduction_details = []

                        for line in all_lines:
                            selected_item_ids = [c.split(" - ")[0] for c in line["items"]]
                            inches_per_piece = SIZE_MAP[line["display_size"].replace("#", "Size ")] + extra_inch
                            used_without_waste = line["pieces"] * inches_per_piece / 12
                            line_total = used_without_waste + line["waste"]
                            total_used += line_total

                            materials = df[df['Item_ID'].isin(selected_item_ids)]['Material'].unique()
                            material_str = materials[0] if len(materials) == 1 else "Mixed"

                            deduction_details.append({
                                "display_size": line["display_size"],
                                "material_type": line["type"],
                                "material": material_str,
                                "pieces": line["pieces"],
                                "waste": line["waste"],
                                "total_used": line_total,
                                "items": ", ".join(selected_item_ids)
                            })

                            per_item = line_total / len(selected_item_ids)
                            for item_id in selected_item_ids:
                                current = df.loc[df['Item_ID'] == item_id, 'Footage'].values[0]
                                if per_item > current:
                                    st.error(f"Not enough footage on {item_id}")
                                    st.stop()
                                df.loc[df['Item_ID'] == item_id, 'Footage'] -= per_item

                        save_inventory()
                        check_low_stock_and_alert()
                        save_production_log(order_number, client_name, operator_name, deduction_details, box_usage)

                        pdf_buffer = generate_production_pdf(order_number, client_name, operator_name, deduction_details, box_usage, extra_inch)

                        if send_production_pdf(pdf_buffer, order_number, client_name):
                            st.success(f"Order {order_number} completed by {operator_name}! PDF sent.")
                        else:
                            st.warning("Logged but email failed.")

                        st.session_state.coil_lines = [{"display_size": "#2", "pieces": 1, "waste": 0.0, "items": []}]
                        st.session_state.roll_lines = [{"display_size": "#2", "pieces": 1, "waste": 0.0, "items": []}]
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
            unit_label = "Pcs"
            default_qty = 1.0

        elif cat_choice == "Fab Straps":
            col1, col2 = st.columns(2)
            with col1:
                gauge = st.selectbox("Gauge", [".015", ".020"])
            with col2:
                size = st.number_input("Size (1-50)", min_value=1, max_value=50, value=1)
            material = f"Fab Strap {gauge} - Size {size}"
            unit_label = "Bundles (1 bundle = 15 straps)"
            default_qty = 1.0 # Set to 1.0 because you count by bundle

        elif cat_choice == "Mineral Wool":
            col1, col2 = st.columns(2)
            with col1:
                p_size = st.text_input("Pipe Size", placeholder="e.g. 2-inch")
            with col2:
                thick = st.text_input("Thickness", placeholder="e.g. 1.5-inch")
            material = f"Min Wool: {p_size} x {thick}"
            unit_label = "Sections"
            default_qty = 1.0

        elif cat_choice == "Other":
            category_name = st.text_input("New Category Name", placeholder="e.g. Insulation")
            material = st.text_input("Material Description", placeholder="e.g. Fiberglass Roll")
            unit_label = "Qty/Footage"
            default_qty = 1.0
        
        else: # Coils and Rolls
            material = st.selectbox("Material Type", COIL_MATERIALS if cat_choice == "Coils" else ROLL_MATERIALS)
            unit_label = "Footage"
            default_qty = 3000.0 if cat_choice == "Coils" else 100.0

        st.markdown("---")
        
        # --- COMMON FIELDS ---
        col_qty, col_cnt = st.columns(2)
        with col_qty:
            # For Fab Straps, this will represent the number of bundles per ID
            qty_val = st.number_input(f"{unit_label} per Item", min_value=0.1, value=float(default_qty))
        with col_cnt:
            item_count = st.number_input("Number of physical units/items", min_value=1, value=1)

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
