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

# --- VIVID LOW STOCK ALERT STYLING ---
st.markdown("""
<style>
.vivid-low-stock-banner {
    background-color: #FF4500;  /* Bright orange-red */
    padding: 15px;
    border-radius: 8px;
    border-left: 8px solid #FF0000;
    margin-bottom: 25px;
    box-shadow: 0 4px 8px rgba(0,0,0,0.2);
}
.vivid-low-stock-text {
    color: #FF0000;  /* Bright red */
    font-weight: bold;
    font-size: 20px;
}
.vivid-low-stock-item {
    color: #D00000;
    font-weight: bold;
    font-size: 16px;
}
.vivid-low-stock-row {
    background-color: #FFFF00 !important;  /* Bright yellow */
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
    "#2": 13.0,
    "#3": 14.5,
    "#4": 16.0,
    "#5": 18.0,
    "#6": 20.0,
    "#7": 23.0,
    "#8": 26.0,
    "#9": 29.5,
    "#10": 32.5,
    "#11": 36.0,
    "#12": 39.5,
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
        inv_ws.clear()
        inv_ws.update([df.columns.tolist()] + df.values.tolist())
    except Exception as e:
        st.error(f"Failed to save inventory: {e}")

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
    st.subheader("Current Inventory Summary")

        # --- Category Selector ---
    st.markdown("#### View by Category")
    if df.empty:
        all_categories = ["All Categories"]
    else:
        unique_categories = df['Category'].dropna().unique().tolist()
        all_categories = ["All Categories"] + sorted([str(cat) for cat in unique_categories])  # Force string for safety

    selected_category = st.selectbox("Select Category", all_categories, key="dashboard_category")

    # Filter data
    if selected_category == "All Categories" or df.empty:
        display_df = df
    else:
        display_df = df[df['Category'] == selected_category]

    if display_df.empty:
        st.info(f"No items in {selected_category} yet.")
    else:
        # Summary Metrics for selected category
        st.markdown(f"### {selected_category} Summary")
        col1, col2 = st.columns(2)
        col1.metric("Number of Items", len(display_df))
        if 'Footage' in display_df.columns:
            total_footage = display_df['Footage'].sum()
            col2.metric("Total Footage (ft)", f"{total_footage:.1f}")
        elif 'Quantity' in display_df.columns:
            total_qty = display_df['Quantity'].sum()
            col2.metric("Total Quantity", int(total_qty))

        # Per-Material Summary (if applicable)
        if 'Material' in display_df.columns:
            st.markdown("### Breakdown by Material")
            material_summary = display_df.groupby('Material').agg(
                Item_Count=('Item_ID', 'count'),
                Total_Footage=('Footage', 'sum') if 'Footage' in display_df.columns else ('Quantity', 'sum')
            ).reset_index()
            material_summary = material_summary.sort_values(material_summary.columns[-1], ascending=False)
            material_summary[material_summary.columns[-1]] = material_summary[material_summary.columns[-1]].round(1)
            st.dataframe(material_summary, use_container_width=True, hide_index=True)

        # Individual Items Table
        st.markdown("### Individual Items")
        show_columns = ['Item_ID', 'Material' if 'Material' in display_df.columns else 'Description', 
                        'Footage' if 'Footage' in display_df.columns else 'Quantity', 'Location']
        item_df = display_df[show_columns].copy()
        if 'Footage' in item_df.columns:
            item_df['Footage'] = item_df['Footage'].round(1)
        st.dataframe(item_df.sort_values(show_columns[1]), use_container_width=True)

    # --- Low Stock Alerts (across all categories) ---
        st.divider()
    st.markdown("### Low Stock Alerts")

    low_items = []
    for _, row in df.iterrows():
        if row['Category'] in ["Coil", "Roll"]:
            threshold = LOW_STOCK_THRESHOLDS.get(row['Material'], 1000.0)
            if row['Footage'] < threshold:
                low_items.append({
                    "item_id": row['Item_ID'],
                    "material": row['Material'],
                    "footage": row['Footage'],
                    "threshold": threshold
                })

    if low_items:
        st.markdown("<div class='vivid-low-stock-banner'>"
                    "<p class='vivid-low-stock-text'>⚠️ URGENT: LOW STOCK ALERT ⚠️</p>"
                    "<p>These items are below threshold — reorder ASAP:</p>", 
                    unsafe_allow_html=True)
        for item in low_items:
            st.markdown(f"<p class='vivid-low-stock-item'>• <strong>{item['item_id']}</strong> — {item['material']}: "
                        f"{item['footage']:.1f} ft (threshold: {item['threshold']} ft)</p>", 
                        unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.success("✅ All coils and rolls are above low stock thresholds!")
with tab2:
    st.subheader("Production Log - Multi-Size Orders (Coils & Rolls)")

    available_coils = df[(df['Category'] == "Coil") & (df['Footage'] > 0)]
    available_rolls = df[(df['Category'] == "Roll") & (df['Footage'] > 0)]

    if available_coils.empty and available_rolls.empty:
        st.info("No coils or rolls with footage available for production.")
    else:
        # Initialize lines
        if 'coil_lines' not in st.session_state:
            st.session_state.coil_lines = []
        if 'roll_lines' not in st.session_state:
            st.session_state.roll_lines = []

        # --- COILS SECTION ---
        st.markdown("### Coils Production")
        if available_coils.empty:
            st.info("No coils available")
        else:
            for i in range(len(st.session_state.coil_lines)):
                line = st.session_state.coil_lines[i]
                with st.container():
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        line["display_size"] = st.selectbox(f"Coil Size {i+1}", list(SIZE_DISPLAY.keys()), index=list(SIZE_DISPLAY.keys()).index(line.get("display_size", "#2")), key=f"coil_size_{i}")
                    with col2:
                        line["pieces"] = st.number_input(f"Coil Pieces {i+1}", min_value=0, value=line.get("pieces", 0), key=f"coil_pieces_{i}")
                    with col3:
                        line["waste"] = st.number_input(f"Coil Waste ft {i+1}", min_value=0.0, value=line.get("waste", 0.0), key=f"coil_waste_{i}")
                    with col4:
                        if st.button("Remove", key=f"remove_coil_line_{i}"):
                            st.session_state.coil_lines.pop(i)
                            st.rerun()

                    coil_options = [f"{row['Item_ID']} - {row['Material']} ({row['Footage']:.1f} ft @ {row['Location']})" 
                                    for _, row in available_coils.iterrows()]
                    line["items"] = st.multiselect(f"Coils for size {i+1}", coil_options, default=line.get("items", []), key=f"coil_items_{i}")

            if st.button("➕ Add Coil Size Line"):
                st.session_state.coil_lines.append({"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []})
                st.rerun()

        # --- ROLLS SECTION ---
        st.markdown("### Rolls Production")
        if available_rolls.empty:
            st.info("No rolls available")
        else:
            for i in range(len(st.session_state.roll_lines)):
                line = st.session_state.roll_lines[i]
                with st.container():
                    col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                    with col1:
                        line["display_size"] = st.selectbox(f"Roll Size {i+1}", list(SIZE_DISPLAY.keys()), index=list(SIZE_DISPLAY.keys()).index(line.get("display_size", "#2")), key=f"roll_size_{i}")
                    with col2:
                        line["pieces"] = st.number_input(f"Roll Pieces {i+1}", min_value=0, value=line.get("pieces", 0), key=f"roll_pieces_{i}")
                    with col3:
                        line["waste"] = st.number_input(f"Roll Waste ft {i+1}", min_value=0.0, value=line.get("waste", 0.0), key=f"roll_waste_{i}")
                    with col4:
                        if st.button("Remove", key=f"remove_roll_line_{i}"):
                            st.session_state.roll_lines.pop(i)
                            st.rerun()

                    roll_options = [f"{row['Item_ID']} - {row['Material']} ({row['Footage']:.1f} ft @ {row['Location']})" 
                                    for _, row in available_rolls.iterrows()]
                    line["items"] = st.multiselect(f"Rolls for size {i+1}", roll_options, default=line.get("items", []), key=f"roll_items_{i}")

            if st.button("➕ Add Roll Size Line"):
                st.session_state.roll_lines.append({"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []})
                st.rerun()

        extra_inch = st.number_input("Extra Inch Allowance per Piece (for machine room)", min_value=0.0, value=0.5, step=0.1)

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

                    # Collect coil lines with pieces > 0
                    for line in st.session_state.coil_lines:
                        if line["pieces"] > 0:
                            has_production = True
                            if not line["items"]:
                                st.error(f"Select coils for coil size {line['display_size']}")
                                st.stop()
                            all_lines.append({"type": "Coil", **line})

                    # Collect roll lines with pieces > 0
                    for line in st.session_state.roll_lines:
                        if line["pieces"] > 0:
                            has_production = True
                            if not line["items"]:
                                st.error(f"Select rolls for roll size {line['display_size']}")
                                st.stop()
                            all_lines.append({"type": "Roll", **line})

                    if not has_production:
                        st.error("Enter pieces for at least one size line (coils or rolls)")
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

                        st.session_state.coil_lines = []
                        st.session_state.roll_lines = []
                        st.balloons()
                        st.rerun()
                            
with tab3:
    st.subheader("Manage")

    # --- Receive New Items (Separate for Coils and Rolls) ---
    st.markdown("### Receive New Items")

    item_type = st.radio("What are you receiving?", ["Coils", "Rolls"], horizontal=True)

    with st.form("receive_form", clear_on_submit=True):
        if item_type == "Coils":
            st.markdown("#### Receiving Coils")
            material = st.selectbox("Material Type", COIL_MATERIALS, key="coil_material")
            prefix = "COIL"
            default_footage = 3000.0
        else:
            st.markdown("#### Receiving Rolls")
            material = st.selectbox("Material Type", ROLL_MATERIALS, key="roll_material")
            prefix = "ROLL"
            default_footage = 100.0

                # --- Unlimited Rack Location Generator (with Floor support) ---
        st.markdown("#### LOCATION")
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            bay = st.number_input("Bay Number", min_value=1, value=1, step=1)
        with col2:
            floor = st.checkbox("On Floor?")
        with col3:
            if floor:
                floor_section = st.number_input("Floor Section", min_value=1, value=1, step=1)
                section_letter = ""
            else:
                section_letter = st.selectbox("Section Letter", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
                floor_section = 0
        with col4:
            level = st.number_input("Level", min_value=1, value=1, step=1)

        if floor:
            generated_location = f"Bay {bay} Floor Section {floor_section} Level {level}"
        else:
            generated_location = f"{bay}{section_letter}{level}"

        st.info(f"**Generated Location Code:** {generated_location}")
        footage = st.number_input(f"Footage per {item_type[:-1]} (ft)", min_value=0.1, value=default_footage)

        # Manual Item ID Input
        st.markdown("#### Manual Item ID Input")
        st.write("Enter the **full starting Item ID** (including number), e.g., `COIL-016-AL-SM-3000-01` or `ROLL-RPR-016-AL-SM-100`")

        default_start = f"{prefix}-016-AL-SM-3000-01" if item_type == "Coils" else f"{prefix}-RPR-016-AL-SM-100"
        starting_id = st.text_input("Starting Item ID", value=default_start)

        count = st.number_input("Number of Items to Add", min_value=1, value=1, step=1)

        # Live preview
        if starting_id.strip() and count > 0:
            try:
                parts = starting_id.strip().upper().split("-")
                base_part = "-".join(parts[:-1])
                start_num = int(parts[-1])
                preview = [f"{base_part}-{str(start_num + i).zfill(2)}" for i in range(count)]
                st.markdown("**Generated Item IDs:**")
                st.code("\n".join(preview), language="text")
            except:
                st.warning("Invalid format — last part must be a number")

        operator_name = st.text_input("Your Name (who is receiving these items)")

        submitted = st.form_submit_button("🚀 Add Items to Inventory")

        if submitted:
            if not operator_name:
                st.error("Your name is required")
            else:
                try:
                    parts = starting_id.strip().upper().split("-")
                    base_part = "-".join(parts[:-1])
                    start_num = int(parts[-1])

                    new_items = []
                    for i in range(count):
                        current_num = start_num + i
                        item_id = f"{base_part}-{str(current_num).zfill(2)}"
                        if item_id in df['Item_ID'].values:
                            st.error(f"Duplicate: {item_id}")
                            st.stop()
                        new_items.append({
                            "Item_ID": item_id,
                            "Material": material,
                            "Footage": footage,
                            "Location": generated_location,
                            "Status": "Active"
                        })

                    # Fix NaN before saving
                    st.session_state.df = st.session_state.df.fillna(0)

                    new_df = pd.concat([df, pd.DataFrame(new_items)], ignore_index=True)
                    st.session_state.df = new_df
                    save_inventory()
                    st.success(f"Added {count} {item_type.lower()} to {generated_location} by {operator_name}!")
                    st.balloons()
                    st.rerun()
                except:
                    st.error("Invalid Item ID format")
    st.divider()

    # --- Move Item ---
    st.markdown("### Move Existing Item")
    if df.empty:
        st.info("No items to move yet.")
    else:
        item_to_move = st.selectbox("Select Item to Move", df['Item_ID'])

        st.markdown("#### New Location Generator")
        col1, col2, col3 = st.columns(3)
        with col1:
            new_bay = st.number_input("New Bay", min_value=1, value=1)
        with col2:
            new_section = st.selectbox("New Section", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
        with col3:
            new_level = st.number_input("New Level", min_value=1, value=1)

        new_location = f"{new_bay}{new_section}{new_level}"
        st.info(f"**New Location:** {new_location}")

        if st.button("Move Item"):
            old_location = df.loc[df['Item_ID'] == item_to_move, 'Location'].values[0]
            df.loc[df['Item_ID'] == item_to_move, 'Location'] = new_location
            save_inventory()
            log_action("Move Item", f"{item_to_move} from {old_location} to {new_location}")
            st.success(f"Moved {item_to_move} to {new_location} by {operator_name}")
            st.rerun()

    st.divider()

    # --- Admin Panel ---
    st.markdown("### 🔧 Admin Only: Adjust Footage or Delete Item")

    admin_password = st.text_input("Admin Password", type="password")
    correct_password = "mjp@2026!"

    if admin_password == correct_password:
        st.success("Admin access granted")

        if not df.empty:
            item_to_manage = st.selectbox("Select Item", df['Item_ID'])

            current_footage = df.loc[df['Item_ID'] == item_to_manage, 'Footage'].values[0]
            new_footage = st.number_input("Adjust Footage (ft)", min_value=0.0, value=float(current_footage))

            col1, col2 = st.columns(2)
            with col1:
                if st.button("Update Footage"):
                    df.loc[df['Item_ID'] == item_to_manage, 'Footage'] = new_footage
                    save_inventory()
                    log_action("Adjust Footage", f"{item_to_manage} to {new_footage:.1f} ft")
                    st.success(f"Updated footage for {item_to_manage}")
                    st.rerun()
            with col2:
                if st.button("🗑️ Delete Item"):
                    if st.checkbox("Confirm permanent deletion"):
                        df = df[df['Item_ID'] != item_to_manage]
                        st.session_state.df = df
                        save_inventory()
                        log_action("Delete Item", item_to_manage)
                        st.success(f"Deleted {item_to_manage}")
                        st.rerun()

        else:
            st.info("No items to manage")
    elif admin_password:
        st.error("Incorrect password")
    else:
        st.info("Enter admin password to adjust footage or delete items")

    st.divider()
    st.subheader("Current Inventory")
    if df.empty:
        st.info("No items in inventory yet.")
    else:
        st.dataframe(df[['Item_ID', 'Material', 'Footage', 'Location', 'Category']], use_container_width=True)

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
