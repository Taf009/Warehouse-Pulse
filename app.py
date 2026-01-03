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

def save_production_log(operator_name, client_name, order_number, deduction_details, box_usage, total_used):
    try:
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        log_ws = sh.worksheet("Production_Log")  # This uses the new tab

        rows = []
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        boxes_str = "; ".join([f"{k}: {v}" for k, v in box_usage.items() if v > 0]) or "None"

        for line in deduction_details:
            rows.append([
                timestamp,
                operator_name,
                client_name,
                order_number,
                line["display_size"],  # e.g., #7
                line["pieces"],
                line["waste"],
                line["coils"],
                boxes_str,
                line["total_used"]
            ])

        log_ws.append_rows(rows)
    except Exception as e:
        st.warning(f"Could not save production log: {e}")  # Won't break the app if it fails

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
                    save_production_log(operator_name, client_name, order_number, deduction_details, box_usage, total_used)

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

with tab3:
    st.subheader("Warehouse Management")

    # --- Receive New Coils Form (keep your existing form here) ---
    # (Paste your current receive form code here — the one with location generator, manual Coil ID, operator name)

    st.divider()
    st.subheader("Current Coils - Manage Inventory")

    if df.empty:
        st.info("No coils in inventory yet.")
    else:
        # Prepare display dataframe
        display_df = df[['Coil_ID', 'Material', 'Footage', 'Location']].copy()
        display_df['Footage'] = display_df['Footage'].round(1)

        # Add action buttons for each row
        actions = []
        for idx, row in display_df.iterrows():
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                if st.button("Adjust", key=f"adjust_{row['Coil_ID']}"):
                    st.session_state.selected_coil = row['Coil_ID']
                    st.session_state.action = "adjust"
                    st.rerun()
            with col2:
                if st.button("Move", key=f"move_{row['Coil_ID']}"):
                    st.session_state.selected_coil = row['Coil_ID']
                    st.session_state.action = "move"
                    st.rerun()
            with col3:
                if st.button("🗑️ Delete", key=f"delete_{row['Coil_ID']}"):
                    st.session_state.selected_coil = row['Coil_ID']
                    st.session_state.action = "delete"
                    st.rerun()
            actions.append("")

        display_df["Actions"] = actions

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # --- Action Modal ---
        if 'action' in st.session_state:
            coil_id = st.session_state.selected_coil
            coil_row = df[df['Coil_ID'] == coil_id].iloc[0]

            st.markdown(f"### Managing Coil: **{coil_id}**")

            if st.session_state.action == "adjust":
                new_footage = st.number_input("New Footage (ft)", min_value=0.0, value=float(coil_row['Footage']))
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Save Footage"):
                        df.loc[df['Coil_ID'] == coil_id, 'Footage'] = new_footage
                        save_inventory()
                        st.success("Footage updated!")
                        del st.session_state.action
                        st.rerun()
                with col2:
                    if st.button("Cancel"):
                        del st.session_state.action
                        st.rerun()

            elif st.session_state.action == "move":
                col1, col2, col3 = st.columns(3)
                with col1:
                    bay = st.number_input("Bay", min_value=1, value=1)
                with col2:
                    section = st.selectbox("Section", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
                with col3:
                    level = st.number_input("Level", min_value=1, value=1)
                new_location = f"{bay}{section}{level}"

                st.info(f"New Location: **{new_location}**")

                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Move Coil"):
                        df.loc[df['Coil_ID'] == coil_id, 'Location'] = new_location
                        save_inventory()
                        st.success(f"Moved to {new_location}")
                        del st.session_state.action
                        st.rerun()
                with col2:
                    if st.button("Cancel"):
                        del st.session_state.action
                        st.rerun()

            elif st.session_state.action == "delete":
                st.warning(f"You are about to permanently delete {coil_id}")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Yes, Delete Permanently", type="primary"):
                        df = df[df['Coil_ID'] != coil_id]
                        st.session_state.df = df
                        save_inventory()
                        st.success("Coil deleted")
                        del st.session_state.action
                        st.rerun()
                with col2:
                    if st.button("Cancel"):
                        del st.session_state.action
                        st.rerun()
            st.divider()
    st.subheader("🔧 Admin: Adjust or Remove Coil")

    admin_password = st.text_input("Admin Password", type="password", key="admin_pass")
    correct_password = "mjp@2026!"

    if admin_password == correct_password:
        st.success("Admin access granted")

        if not df.empty:
            coil_to_adjust = st.selectbox("Select Coil to Adjust/Delete", df['Coil_ID'], key="admin_select_coil")

            current_footage = df.loc[df['Coil_ID'] == coil_to_adjust, 'Footage'].values[0]

            # --- Update Footage ---
            st.markdown("#### Update Footage")
            new_footage = st.number_input("New Footage (ft)", min_value=0.0, value=float(current_footage), key="admin_new_footage")
            if st.button("Update Footage", key="admin_update"):
                df.loc[df['Coil_ID'] == coil_to_adjust, 'Footage'] = new_footage
                save_inventory()
                st.success(f"Updated {coil_to_adjust} to {new_footage:.1f} ft")
                st.rerun()

            # --- Delete Coil ---
            st.markdown("#### Delete Coil")
            st.warning(f"Deleting {coil_to_adjust} is permanent!")
            if st.button("Delete Coil Permanently", key="admin_delete"):
                df = df[df['Coil_ID'] != coil_to_adjust]
                st.session_state.df = df
                save_inventory()
                st.success(f"Deleted {coil_to_adjust}")
                st.rerun()

        else:
            st.info("No coils to adjust")
    elif admin_password:
        st.error("Incorrect admin password")
    else:
        st.info("Enter admin password to access adjustment tools")
with tab4:
    st.subheader("📊 Daily Production Summary")

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

            today = datetime.now().date()
            today_log = log_df[log_df['Date'] == today]

            if today_log.empty:
                st.info("No production today yet — stats will appear after your first order!")
            else:
                # --- Key Metrics ---
                st.markdown("### Today's Key Metrics")
                col1, col2, col3, col4 = st.columns(4)
                total_footage = today_log['Total_Used_FT'].sum()
                total_waste = today_log['Waste_FT'].sum()
                total_pieces = today_log['Pieces'].sum()
                efficiency = ((total_footage - total_waste) / total_footage * 100) if total_footage > 0 else 0

                col1.metric("Total Footage Used", f"{total_footage:.1f} ft")
                col2.metric("Total Waste", f"{total_waste:.1f} ft", delta=f"{total_waste:.1f} ft")
                col3.metric("Total Pieces Produced", int(total_pieces))
                col4.metric("Material Efficiency", f"{efficiency:.1f}%", delta=f"{100-efficiency:.1f}% waste")

                # --- Chart 1: Footage Used vs Waste ---
                st.markdown("### Footage Breakdown")
                chart_data = pd.DataFrame({
                    "Type": ["Used (Product)", "Waste"],
                    "Footage (ft)": [total_footage - total_waste, total_waste]
                })
                st.bar_chart(chart_data.set_index("Type"))

                # --- Chart 2: Production by Size ---
                st.markdown("### Production by Size Today")
                size_summary = today_log.groupby('Size').agg({
                    'Pieces': 'sum',
                    'Total_Used_FT': 'sum'
                }).reset_index()
                size_summary = size_summary.sort_values('Total_Used_FT', ascending=False)

                st.bar_chart(size_summary.set_index('Size')['Pieces'], use_container_width=True)

                # --- Today's Orders Table ---
                st.markdown("### Today's Completed Orders")
                display_today = today_log[['Timestamp', 'Operator', 'Client', 'Order_Number', 'Size', 'Pieces', 'Waste_FT', 'Coils_Used']].copy()
                display_today['Timestamp'] = display_today['Timestamp'].dt.strftime('%H:%M')
                display_today = display_today.sort_values('Timestamp', ascending=False)
                st.dataframe(display_today, use_container_width=True)

    except Exception as e:
        st.error(f"Could not load production log: {e}")
        st.info("Make sure you have a 'Production_Log' tab with the correct headers.")
