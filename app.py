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
    "Size 7": 23.0,
    "Size 5": 18.0,
    "Size 10": 30.0,
    "Size 3": 12.0,
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

# --- PDF GENERATION ---
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Production Order Complete', 0, 1, 'C')
        self.ln(10)

def generate_production_pdf(order_number, client_name, material, coil_id, size, pieces, used_ft, waste_ft, remaining_ft):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)
    
    pdf.cell(0, 10, f"Internal Order Number: {order_number}", 0, 1)
    pdf.cell(0, 10, f"Client: {client_name}", 0, 1)
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1)
    pdf.ln(10)
    
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Production Details", 0, 1)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f"Material: {material}", 0, 1)
    pdf.cell(0, 10, f"Coil ID: {coil_id}", 0, 1)
    pdf.cell(0, 10, f"Size Produced: {size}", 0, 1)
    pdf.cell(0, 10, f"Pieces Produced: {pieces}", 0, 1)
    pdf.cell(0, 10, f"Total Footage Used: {used_ft:.2f} ft (including {waste_ft:.2f} ft waste)", 0, 1)
    pdf.cell(0, 10, f"Remaining Footage on Coil: {remaining_ft:.2f} ft", 0, 1)
    
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
        # Material Summary
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

with tab2:
    st.subheader("Production Log - Cut from Coil")

    available_coils = df[df['Footage'] > 0]
    if available_coils.empty:
        st.info("No coils with footage available for production. Add coils first.")
    else:
        with st.form("production_form"):
            st.markdown("#### Select Coil and Production Details")
            coil_options = [f"{row['Coil_ID']} - {row['Material']} ({row['Footage']:.1f} ft @ {row['Location']})" 
                            for _, row in available_coils.iterrows()]
            selected_coil_str = st.selectbox("Select Coil to Cut From", coil_options)
            coil_id = selected_coil_str.split(" - ")[0]

            size = st.selectbox("Size Being Produced", list(SIZE_MAP.keys()))
            pieces = st.number_input("Number of Pieces Produced", min_value=1, step=1)
            waste = st.number_input("Waste Footage (ft)", min_value=0.0, step=0.1, value=0.0)

            client_name = st.text_input("Client Name")
            order_number = st.text_input("Internal Order Number")

            submitted = st.form_submit_button("Complete Production Order & Send PDF")

            if submitted:
                if not client_name or not order_number:
                    st.error("Client Name and Order Number are required")
                else:
                    inches_per_piece = SIZE_MAP[size]
                    used_without_waste = pieces * inches_per_piece / 12
                    total_used = used_without_waste + waste

                    current_footage = df.loc[df['Coil_ID'] == coil_id, 'Footage'].values[0]
                    if total_used > current_footage:
                        st.error(f"Not enough footage! Only {current_footage:.1f} ft available.")
                    else:
                        remaining = current_footage - total_used
                        df.loc[df['Coil_ID'] == coil_id, 'Footage'] = remaining
                        material = df.loc[df['Coil_ID'] == coil_id, 'Material'].values[0]

                        save_inventory()

                        pdf_buffer = generate_production_pdf(
                            order_number, client_name, material, coil_id, size, pieces,
                            total_used, waste, remaining
                        )

                        if send_production_pdf(pdf_buffer, order_number, client_name):
                            st.success(f"Production order {order_number} completed! PDF sent to admin.")
                        else:
                            st.warning("Production logged but email failed.")

                        st.balloons()
                        st.rerun()

with tab3:
    st.subheader("Receive New Coils")
    with st.form("receive_coils_form", clear_on_submit=True):
        st.markdown("#### Add New Coil Shipment")

        material = st.selectbox("Material Type", COIL_MATERIALS, key="recv_material")

        # Location Generator
        st.markdown("#### Rack Location Generator (Unlimited)")
        col1, col2, col3 = st.columns(3)
        with col1:
            bay = st.number_input("Bay Number", min_value=1, value=1, step=1, key="bay")
        with col2:
            section = st.selectbox("Section Letter", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), key="section")
        with col3:
            level = st.number_input("Level", min_value=1, value=1, step=1, key="level")

        generated_location = f"{bay}{section}{level}"
        st.info(f"**Generated Location Code:** {generated_location}")

        footage = st.number_input("Footage per Coil (ft)", min_value=0.1, value=3000.0, key="recv_footage")

        # Manual Coil ID
        st.markdown("#### Manual Coil ID Input")
        st.write("Enter the **full starting Coil ID** (including number), e.g., `COIL-016-AL-SM-3000-01`")

        starting_id = st.text_input("Starting Coil ID", value="COIL-016-AL-SM-3000-01", key="starting_id")
        count = st.number_input("Number of Coils to Add", min_value=1, value=1, step=1, key="count")

        # Preview
        if starting_id.strip() and count > 0:
            try:
                parts = starting_id.strip().upper().split("-")
                base_part = "-".join(parts[:-1])
                start_num = int(parts[-1])
                preview = [f"{base_part}-{str(start_num + i).zfill(2)}" for i in range(count)]
                st.markdown("**Generated Coil IDs:**")
                st.code("\n".join(preview), language="text")
            except:
                st.warning("Invalid format")

        submitted = st.form_submit_button("🚀 Add Coils to Inventory")

        if submitted:
            try:
                parts = starting_id.strip().upper().split("-")
                base_part = "-".join(parts[:-1])
                start_num = int(parts[-1])

                new_coils = []
                for i in range(count):
                    current_num = start_num + i
                    coil_id = f"{base_part}-{str(current_num).zfill(2)}"
                    if coil_id in df['Coil_ID'].values:
                        st.error(f"Duplicate: {coil_id}")
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
                st.success(f"Added {count} coil(s) to {generated_location}!")
                st.balloons()
                st.rerun()
            except:
                st.error("Invalid Coil ID format")

    st.divider()
    st
