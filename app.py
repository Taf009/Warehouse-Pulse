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
import time

# --- PAGE CONFIG ---
st.set_page_config(page_title="Warehouse Pulse Check", layout="wide")
st.title("🏭 Warehouse Pulse Check - Production & Inventory")

# --- SIZE MAP with # prefix ---
SIZE_DISPLAY = {f"#{k.split()[1]}": v for k, v in {
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
}.items()}

# Reverse map for calculations
SIZE_MAP = {k.replace("#", "Size "): v for k, v in SIZE_DISPLAY.items()}

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

# --- PDF GENERATION (updated to use # format) ---
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
        pdf.cell(0, 10, f"Size: {line['display_size']} | Pieces: {line['pieces']} | Waste: {line['waste']:.1f} ft", 0, 1)
        pdf.cell(0, 10, f"Coils Used: {line['coils']}", 0, 1)
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

        body = f"Production order {order_number} for {client_name} has been completed.\n\nSee attached PDF for full details."
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
tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Production Log", "Warehouse Management", "Daily Summary"])

with tab1:
    st.subheader("Current Inventory Summary")

    if df.empty:
        st.info("No coils in inventory yet. Go to Warehouse Management to add some.")
    else:
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

        st.markdown("### Individual Coils")
        display_df = df[['Coil_ID', 'Material', 'Footage', 'Location']].copy()
        display_df['Footage'] = display_df['Footage'].round(1)
        st.dataframe(display_df.sort_values(['Material', 'Location']), use_container_width=True)

with tab2:
    st.subheader("Production Log - Multi-Size & Multi-Coil Orders")

    available_coils = df[df['Footage'] > 0]
    if available_coils.empty:
        st.info("No coils with footage available for production.")
    else:
        if 'production_lines' not in st.session_state:
            st.session_state.production_lines = [{"size": "#2", "pieces": 1, "waste": 0.0, "override_coils": []}]

        st.markdown("#### Production Lines")
        for i in range(len(st.session_state.production_lines)):
            line = st.session_state.production_lines[i]
            with st.container():
                col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
                with col1:
                    line["size"] = st.selectbox(
                        f"Size {i+1}",
                        list(SIZE_DISPLAY.keys()),
                        index=list(SIZE_DISPLAY.keys()).index(line["size"]),
                        key=f"size_{i}"
                    )
                with col2:
                    line["pieces"] = st.number_input(f"Pieces {i+1}", min_value=1, value=line["pieces"], key=f"pieces_{i}")
                with col3:
                    line["waste"] = st.number_input(f"Waste ft {i+1}", min_value=0.0, value=line["waste"], key=f"waste_{i}")
                with col4:
                    if st.button("Remove Line", key=f"remove_line_{i}"):
                        st.session_state.production_lines.pop(i)
                        st.rerun()

                with st.expander(f"Override Coils for {line['size']} (optional)"):
                    coil_options = [f"{row['Coil_ID']} - {row['Material']} ({row['Footage']:.1f} ft @ {row['Location']})" 
                                    for _, row in available_coils.iterrows()]
                    line["override_coils"] = st.multiselect("Coils for this line", coil_options, default=line["override_coils"], key=f"override_coils_{i}")

        if st.button("➕ Add Another Size Line"):
            st.session_state.production_lines.append({"size": "#2", "pieces": 1, "waste": 0.0, "override_coils": []})
            st.rerun()

        st.markdown("#### Global Coils (used for all lines unless overridden)")
        coil_options = [f"{row['Coil_ID']} - {row['Material']} ({row['Footage']:.1f} ft @ {row['Location']})" 
                        for _, row in available_coils.iterrows()]
        global_coils = st.multiselect("Select Global Coils", coil_options)

        extra_inch = st.number_input("Extra Inch Allowance per Piece (for machine room)", min_value=0.0, value=0.5, step=0.1)

        with st.form("production_submit_form"):
            st.markdown("#### Order Details")
            client_name = st.text_input("Client Name")
            order_number = st.text_input("Internal Order Number")
            operator_name = st.text_input("Your Name (who is completing this order)")

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
                    with st.spinner("Processing your order... 🌀"):
                        time.sleep(2)  # Simulate processing

                    total_used = 0
                    deduction_details = []

                    for line in st.session_state.production_lines:
                        coils_to_use = line["override_coils"] if line["override_coils"] else global_coils
                        if not coils_to_use:
                            st.error("Select coils (global or override) for all lines")
                            st.stop()

                        selected_coil_ids = [c.split(" - ")[0] for c in coils_to_use]
                        inches_per_piece = SIZE_MAP[line["size"].replace("#", "Size ")] + extra_inch
                        used_without_waste = line["pieces"] * inches_per_piece / 12
                        line_total = used_without_waste + line["waste"]
                        total_used += line_total

                        deduction_details.append({
                            "display_size": line["size"],
                            "size": line["size"].replace("#", "Size "),
                            "pieces": line["pieces"],
                            "waste": line["waste"],
                            "total_used": line_total,
                            "coils": ", ".join(selected_coil_ids)
                        })

                        per_coil = line_total / len(selected_coil_ids)
                        for coil_id in selected_coil_ids:
                            current = df.loc[df['Coil_ID'] == coil_id, 'Footage'].values[0]
                            if per_coil > current:
                                st.error(f"Not enough footage on {coil_id}")
                                st.stop()
                            df.loc[df['Coil_ID'] == coil_id, 'Footage'] -= per_coil

                    save_inventory()

                    pdf_buffer = generate_production_pdf(order_number, client_name, operator_name, deduction_details, box_usage, extra_inch)

                    if send_production_pdf(pdf_buffer, order_number, client_name):
                        st.success("Submitted!")
                        st.balloons()
                        st.markdown("<h1 style='text-align: center; color: green;'>✓</h1>", unsafe_allow_html=True)
                        st.markdown("<h2 style='text-align: center;'>Danke, Seahorse! 🐴</h2>", unsafe_allow_html=True)
                    else:
                        st.warning("Order logged but email failed.")

                    st.session_state.production_lines = [{"size": "#2", "pieces": 1, "waste": 0.0, "override_coils": []}]
                    st.rerun()

# --- REST OF THE CODE (Warehouse Management, Admin, etc.) remains the same as previous full version ---
# (Include your full tab3 and tab4 from the last working version)
