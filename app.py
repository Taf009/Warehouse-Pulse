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
from email.mime.application import MIMEApplication
from supabase import create_client, Client
from collections import defaultdict

# --- LOW STOCK THRESHOLDS
LOW_STOCK_THRESHOLDS = {
    ".016 Smooth Aluminum": 6000.0,
    ".020 Stucco Aluminum": 6000.0,
    ".020 Smooth Aluminum": 3500.0,
    ".016 Stucco Aluminum": 2500.0,
    ".010 Stainless Steel Polythene": 2500.0,
    # Add roll thresholds if different
}

# --- PDF CLASS & FUNCTION (only the good one with logo & Type column) ---
class PDF(FPDF):
    def header(self):
        # Add logo
        try:
            self.image("logo.png", x=10, y=8, w=30)
        except Exception:
            self.set_font('Arial', 'I', 10)
            self.cell(0, 10, "MJP Pulse Logo", 0, 1, 'L')
        
        self.set_font('Arial', 'B', 16)
        self.cell(0, 10, 'Production Order', 0, 1, 'C')
        self.ln(5)

def generate_production_pdf(order_number, client_name, operator_name, deduction_details, box_usage):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font('Arial', '', 12)

    # Top information
    pdf.cell(0, 10, f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}", 0, 1)
    
    pdf.set_fill_color(200, 255, 200)  # Light green
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, f"Client: {client_name}", fill=True, ln=1)
    pdf.cell(0, 10, f"Internal Order #: {order_number}", fill=True, ln=1)
    pdf.set_font('Arial', '', 12)
    pdf.cell(0, 10, f"Operator: {operator_name}", 0, 1)
    pdf.cell(0, 10, "Internal Production #: ____________________ (Admin to fill)", 0, 1)
    pdf.ln(10)

    # Table header - Type column (Coil/Roll)
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(45, 10, "Size / Pieces", border=1)
    pdf.cell(40, 10, "Type", border=1)
    pdf.cell(55, 10, "Material", border=1)
    pdf.cell(30, 10, "Footage (ft)", border=1)
    pdf.cell(30, 10, "Waste (ft)", border=1, ln=1)

    # Table rows
    pdf.set_font('Arial', '', 11)
    for line in deduction_details:
        size_pieces = f"{line['display_size']} / {line['pieces']} pcs"
        line_type = line.get('type', 'Unknown')
        
        pdf.cell(45, 10, size_pieces, border=1)
        pdf.cell(40, 10, line_type, border=1)
        pdf.cell(55, 10, line['material'], border=1)
        pdf.cell(30, 10, f"{line['total_used']:.2f}", border=1)
        pdf.cell(30, 10, f"{line['waste']:.2f}", border=1, ln=1)

    # Material totals
    pdf.ln(10)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Material Totals", ln=1)
    pdf.set_font('Arial', '', 11)

    totals = defaultdict(lambda: {"footage": 0.0, "waste": 0.0})
    for line in deduction_details:
        mat = line['material']
        totals[mat]["footage"] += line['total_used']
        totals[mat]["waste"] += line['waste']

    pdf.set_fill_color(200, 255, 200)
    grand_footage = 0.0
    grand_waste = 0.0
    for mat, t in totals.items():
        pdf.cell(0, 10, f"{mat}: {t['footage']:.2f} ft footage, {t['waste']:.2f} ft waste", fill=True, ln=1)
        grand_footage += t['footage']
        grand_waste += t['waste']

    pdf.cell(0, 10, f"**Total Footage: {grand_footage:.2f} ft**", fill=True, ln=1)
    pdf.cell(0, 10, f"**Total Waste: {grand_waste:.2f} ft**", fill=True, ln=1)

    # Boxes used
    pdf.ln(15)
    pdf.set_font('Arial', 'B', 12)
    pdf.cell(0, 10, "Boxes Used:", ln=1)
    pdf.set_font('Arial', '', 11)
    used_any = False
    for box, count in box_usage.items():
        if count > 0:
            safe_box = box.replace('–', '-').replace('—', '-')
            pdf.cell(0, 10, f"{safe_box} - {count}", ln=1)
            used_any = True
    if not used_any:
        pdf.cell(0, 10, "No boxes used", ln=1)

    buffer = io.BytesIO()
    pdf.output(buffer)
    buffer.seek(0)
    return buffer

# --- DATABASE CONNECTION ---
@st.cache_resource 
def init_connection():
    try:
        if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
            return None
        
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except:
        return None

supabase = init_connection()

# --- DATA LOADER ---
@st.cache_data(ttl=300)
def load_all_tables():
    if supabase is None:
        return pd.DataFrame(), pd.DataFrame()
    
    try:
        inv_res = supabase.table("inventory").select("*").execute()
        df_inv = pd.DataFrame(inv_res.data)
        
        audit_res = supabase.table("audit_log").select("*").execute()
        df_audit = pd.DataFrame(audit_res.data)
        
        return df_inv, df_audit
    except Exception as e:
        st.error(f"Error loading tables: {e}")
        return pd.DataFrame(), pd.DataFrame()

# Initialize data
if 'df' not in st.session_state or 'df_audit' not in st.session_state:
    st.session_state.df, st.session_state.df_audit = load_all_tables()

df = st.session_state.df
df_audit = st.session_state.df_audit

# Normalize category names - handle plurals/singular/case variations
def normalize_category(cat):
    if pd.isna(cat):
        return "Unknown"
    cat = str(cat).strip().lower()
    if "coil" in cat:
        return "Coil"
    if "roll" in cat:
        return "Roll"
    if "fab strap" in cat or "fabstraps" in cat:
        return "Fab Strap"
    if "elbow" in cat:
        return "Elbow"
    return cat.capitalize()  # fallback

# Apply normalization (NOW after df exists)
if 'Category' in df.columns:
    df['Category_normalized'] = df['Category'].apply(normalize_category)
    category_col = 'Category_normalized'
else:
    st.warning("No 'Category' column found - normalization skipped")
    category_col = 'Category'

# Debug: Show normalized categories (remove later if you want)
st.sidebar.write("DEBUG: Normalized Categories", df[category_col].unique().tolist())

# --- SAVE FUNCTION (PROTECTED VERSION) ---
def save_inventory():
    try:
        if st.session_state.df is None or st.session_state.df.empty:
            st.error("⚠️ CRITICAL: Inventory data is empty. Save aborted to prevent data loss.")
            return

        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        inv_ws = sh.worksheet("Inventory")

        new_data = [st.session_state.df.columns.tolist()] + st.session_state.df.values.tolist()

        inv_ws.clear()
        inv_ws.update('A1', new_data)
        
        st.toast("✅ Inventory synchronized with Google Sheets.")
    except Exception as e:
        st.error(f"Failed to save inventory: {e}")
        st.info("Safety mode: Your data was NOT cleared on the Google Sheet.")

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

# --- PRODUCTION LOG SAVE (Google Sheets fallback - consider migrating to Supabase) ---
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
        part.add_header('Content-Disposition', f"attachment; filename={filename}")
        msg.attach(part)

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(st.secrets["SMTP_EMAIL"], st.secrets["SMTP_PASSWORD"])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

# --- UPDATE STOCK (with better debug) ---
def update_stock(item_id, new_footage, user_name, action_type):
    try:
        update_response = supabase.table("inventory").update({"Footage": new_footage}).eq("Item_ID", item_id).execute()
        print(f"DEBUG: Updated {item_id} to {new_footage} ft - Response: {update_response}")
        st.toast(f"Inventory updated: {item_id} → {new_footage:.2f} ft", icon="✅")

        log_entry = {
            "Item_ID": item_id,
            "Action": action_type,
            "User": user_name,
            "Timestamp": datetime.now().isoformat()
        }
        supabase.table("audit_logs").insert(log_entry).execute()
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update database: {e}")
        return False

# --- PROCESS PRODUCTION LINE (with debug) ---
def process_production_line(
    line,
    extra_inches: float,
    material_type: str,
    order_number: str,
    client_name: str,
    operator_name: str,
    feedback: list,
    deduction_details: list
) -> tuple[bool, float]:
    if line["pieces"] <= 0 or not line["items"]:
        return True, 0.0

    try:
        selected = line["items"][0]
        item_id = selected.split(" - ")[0].strip()
        material = selected.split(" - ")[1].split(" (")[0].strip()

        if line.get("use_custom", False) and line.get("custom_inches", 0) > 0:
            base_inches = line["custom_inches"]
            display_size = f"Custom {base_inches:.2f}\""
        else:
            base_inches = SIZE_MAP.get(line["display_size"].replace("#", "Size "), 0)
            display_size = line["display_size"]

        if base_inches <= 0:
            raise ValueError("Invalid size/length selected")

        total_inches = base_inches + extra_inches
        ft_needed = (line["pieces"] * total_inches / 12.0) + line["waste"]

        res = supabase.table("inventory").select("Footage").eq("Item_ID", item_id).execute()
        if not res.data:
            raise ValueError(f"Item {item_id} not found in inventory")

        current_ft = float(res.data[0]["Footage"])
        if current_ft < ft_needed - 0.01:
            raise ValueError(f"Insufficient stock ({material_type}): need {ft_needed:.2f} ft, have {current_ft:.2f} ft")

        new_footage = current_ft - ft_needed

        update_response = supabase.table("inventory").update({"Footage": new_footage}).eq("Item_ID", item_id).execute()
        print(f"DEBUG: Updated {item_id} ({material_type}) to {new_footage:.2f} ft - Response: {update_response}")

        feedback.append(f"✓ {material_type} {item_id} – deducted {ft_needed:.2f} ft")
        st.toast(f"Inventory updated: {item_id} → {new_footage:.2f} ft", icon="✅")

        log_entry = {
            "order_number": order_number,
            "client_name": client_name,
            "operator_name": operator_name,
            "material": material,
            "size": display_size,
            "pieces": line["pieces"],
            "waste_ft": round(line["waste"], 2),
            "footage_used": round(ft_needed, 2),
            "source_item_ids": item_id,
            "extra_inches": extra_inches,
            "type": material_type,
            "box_usage": "pending"
        }
        supabase.table("production_log2").insert(log_entry).execute()

        deduction_details.append({
            "display_size": display_size,
            "pieces": line["pieces"],
            "material": material,
            "total_used": ft_needed,
            "waste": line["waste"],
            "type": material_type
        })

        return True, ft_needed

    except Exception as e:
        error_msg = f"✗ {material_type} line failed: {str(e)}"
        feedback.append(error_msg)
        st.error(error_msg)
        return False, 0.0

# --- TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Dashboard", "Production Log", "Stock Picking", "Manage", "Insights", "Audit Trail"])

with tab1:
    if not df.empty:
        available_categories = sorted(df[category_col].unique().tolist())
        view_options = ["All Materials"] + available_categories
        
        selected_view = st.radio(
            "Select Dashboard View", 
            view_options, 
            horizontal=True,
            help="Switch between Coils, Rolls, or other material categories"
        )
        
        if selected_view == "All Materials":
            display_df = df.copy()
            st.subheader("📊 Global Material Pulse")
        else:
            display_df = df[df[category_col] == selected_view].copy()
            st.subheader(f"📊 {selected_view} Inventory Pulse")

        summary_df = display_df.groupby(['Material', category_col]).agg({
            'Footage': 'sum',
            'Item_ID': 'count'
        }).reset_index()
        summary_df.columns = ['Material', 'Type', 'Total_Footage', 'Unit_Count']

        m1, m2, m3 = st.columns(3)
        current_total_ft = display_df['Footage'].sum()
        current_unit_count = len(display_df)
        unique_mats = len(summary_df)
        
        m1.metric("Selected Footage", f"{current_total_ft:,.1f} ft")
        m2.metric("Items in View", current_unit_count)
        m3.metric("Material Types", unique_mats)

        st.divider()

        cols = st.columns(2)
        for idx, row in summary_df.iterrows():
            with cols[idx % 2]:
                mat = row['Material']
                ft = row['Total_Footage']
                units = row['Unit_Count']
                cat_type = row['Type'] 
                
                display_value = f"{ft:,.1f}"
                unit_text = "Units"
                sub_label_text = "In Stock"

                if cat_type == "Roll":
                    divisor = 200 if "RPR" in mat.upper() else 100
                    roll_qty = ft / divisor
                    display_value = f"{roll_qty:.1f}"
                    unit_text = f"Rolls ({divisor}ft)"
                    sub_label_text = f"Total: {ft:,.1f} FT"
                
                elif cat_type == "Coil":
                    display_value = f"{ft:,.1f}"
                    unit_text = "FT"
                    sub_label_text = f"{int(units)} Separate Coils"
                
                elif cat_type == "Fab Strap":
                    display_value = f"{int(ft)}"
                    unit_text = "Bundles"
                    sub_label_text = "Standard Stock"

                elif cat_type == "Elbow":
                    display_value = f"{int(ft)}"
                    unit_text = "Pcs"
                    sub_label_text = "Standard Stock"

                limit = LOW_STOCK_THRESHOLDS.get(mat, 10.0 if cat_type in ["Fab Strap", "Elbow"] else 1000.0)
                
                if ft < limit:
                    status_color, status_text = "#FF4B4B", "🚨 REORDER REQUIRED"
                elif ft < (limit * 1.5):
                    status_color, status_text = "#FFA500", "⚠️ MONITOR CLOSELY"
                else:
                    status_color, status_text = "#00C853", "✅ STOCK HEALTHY"

                st.markdown(f"""
                <div style="background-color: #f9f9f9; padding: 20px; border-radius: 12px; 
                            border-left: 12px solid {status_color}; margin-bottom: 15px; min-height: 180px;">
                    <p style="color: #666; font-size: 11px; margin: 0; font-weight: bold;">{cat_type.upper()}</p>
                    <h3 style="margin: 5px 0; font-size: 18px;">{mat}</h3>
                    <h1 style="margin: 10px 0; color: {status_color};">{display_value} <span style="font-size: 16px;">{unit_text}</span></h1>
                    <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #eee; padding-top: 10px; margin-top: 10px;">
                        <span style="font-weight: bold; color: {status_color}; font-size: 12px;">{status_text}</span>
                        <span style="color: #888; font-size: 11px;">{sub_label_text} ({units} IDs)</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)

        with st.expander(f"🔍 View {selected_view} Serial Numbers / Detail"):
            st.dataframe(
                display_df[['Item_ID', category_col, 'Material', 'Footage', 'Location']].sort_values('Material'), 
                use_container_width=True, 
                hide_index=True
            )
    else:
        st.info("No data available. Add inventory in the Warehouse tab.")

# ── TAB 2: Production Log ────────────────────────────────────────────────────────
with tab2:
    st.subheader("📋 Production Log - Multi-Size Orders")

    if df.empty:
        st.warning("⚠️ No inventory data found. Please add items first.")
        st.stop()

    category_col = next((c for c in df.columns if c.lower() == 'category_normalized' or c.lower() == 'category'), 'Category')
    if category_col == 'Category':
        st.warning("Using original Category column - normalization may not be applied.")

    if "coil_lines" not in st.session_state:
        st.session_state.coil_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": [], "use_custom": False, "custom_inches": 12.0}]
    if "roll_lines" not in st.session_state:
        st.session_state.roll_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": [], "use_custom": False, "custom_inches": 12.0}]

    st.markdown("### 🔧 Material Type Filter")
    material_type = st.radio(
        "Select texture for sources (applies to both Coils & Rolls)",
        options=["Smooth", "Stucco"],
        horizontal=True,
        key="material_texture_toggle"
    )

    def filter_materials(df_subset):
        if material_type == "Smooth":
            return df_subset[df_subset['Material'].str.contains("Smooth", case=False) & ~df_subset['Material'].str.contains("Stucco", case=False)]
        elif material_type == "Stucco":
            return df_subset[df_subset['Material'].str.contains("Stucco", case=False)]
        return df_subset

    # Robust filter using contains
    available_coils = filter_materials(
        df[df[category_col].str.contains("coil", case=False, na=False) & (df['Footage'] > 0)]
    )
    available_rolls = filter_materials(
        df[df[category_col].str.contains("roll", case=False, na=False) & (df['Footage'] > 0)]
    )

    if available_coils.empty and available_rolls.empty:
        st.info("No available stock matching the selected texture.")
        st.stop()

    coil_options = [f"{r['Item_ID']} - {r['Material']} ({r['Footage']:.1f} ft)" for _, r in available_coils.iterrows()]
    roll_options = [f"{r['Item_ID']} - {r['Material']} ({r['Footage']:.1f} ft)" for _, r in available_rolls.iterrows()]

    # ── COILS SECTION ───────────────────────────────────────────────────────────────
    st.markdown("### 🌀 Coils Production")
    coil_extra = st.number_input(
        "Extra Inch Allowance per piece (Coils)",
        min_value=0.0, value=0.5, step=0.1,
        key="coil_extra_allowance"
    )

    last_coil_selected = None
    for i, line in enumerate(st.session_state.coil_lines):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 1.2, 1.2, 0.4])
            with c1:
                line["display_size"] = st.selectbox(
                    "Size", list(SIZE_DISPLAY.keys()),
                    key=f"c_size_{i}"
                )
            with c2:
                line["pieces"] = st.number_input(
                    "Pieces", min_value=0, step=1,
                    key=f"c_pcs_{i}"
                )
            with c3:
                line["waste"] = st.number_input(
                    "Waste (ft)", min_value=0.0, step=0.5,
                    key=f"c_waste_{i}"
                )
            with c4:
                if st.button("🗑", key=f"del_coil_{i}", help="Remove this line"):
                    st.session_state.coil_lines.pop(i)
                    st.rerun()

            line["use_custom"] = st.checkbox(
                "Use custom inches instead of standard size",
                value=line.get("use_custom", False),
                key=f"c_custom_chk_{i}"
            )

            current_custom = line.get("custom_inches")
            safe_custom_value = 12.0 if current_custom is None else max(0.1, float(current_custom))

            if line["use_custom"]:
                line["custom_inches"] = st.number_input(
                    "Custom length per piece (inches)",
                    min_value=0.1,
                    value=safe_custom_value,
                    step=0.25,
                    key=f"c_custom_in_{i}"
                )
            else:
                line["custom_inches"] = 0.0

            current_defaults = [opt for opt in line["items"] if opt in coil_options]
            if not current_defaults and last_coil_selected and last_coil_selected in coil_options:
                current_defaults = [last_coil_selected]

            line["items"] = st.multiselect(
                "Select source coil(s)",
                options=coil_options,
                default=current_defaults,
                key=f"c_source_{i}"
            )

            if line["items"]:
                last_coil_selected = line["items"][0]

    if st.button("➕ Add another coil size", use_container_width=True):
        st.session_state.coil_lines.append({
            "display_size": "#2", "pieces": 0, "waste": 0.0,
            "items": [], "use_custom": False, "custom_inches": 12.0
        })
        st.rerun()

    st.divider()

    # ── ROLLS SECTION ───────────────────────────────────────────────────────────────
    st.markdown("### 🗞️ Rolls Production")
    roll_extra = st.number_input(
        "Extra Inch Allowance per piece (Rolls)",
        min_value=0.0, value=0.5, step=0.1,
        key="roll_extra_allowance"
    )

    last_roll_selected = None
    for i, line in enumerate(st.session_state.roll_lines):
        with st.container(border=True):
            r1, r2, r3, r4 = st.columns([3, 1.2, 1.2, 0.4])
            with r1:
                line["display_size"] = st.selectbox(
                    "Size", list(SIZE_DISPLAY.keys()),
                    key=f"r_size_{i}"
                )
            with r2:
                line["pieces"] = st.number_input(
                    "Pieces", min_value=0, step=1,
                    key=f"r_pcs_{i}"
                )
            with r3:
                line["waste"] = st.number_input(
                    "Waste (ft)", min_value=0.0, step=0.5,
                    key=f"r_waste_{i}"
                )
            with r4:
                if st.button("🗑", key=f"del_roll_{i}", help="Remove this line"):
                    st.session_state.roll_lines.pop(i)
                    st.rerun()

            line["use_custom"] = st.checkbox(
                "Use custom inches instead of standard size",
                value=line.get("use_custom", False),
                key=f"r_custom_chk_{i}"
            )

            current_custom = line.get("custom_inches")
            safe_custom_value = 12.0 if current_custom is None else max(0.1, float(current_custom))

            if line["use_custom"]:
                line["custom_inches"] = st.number_input(
                    "Custom length per piece (inches)",
                    min_value=0.1,
                    value=safe_custom_value,
                    step=0.25,
                    key=f"r_custom_in_{i}"
                )
            else:
                line["custom_inches"] = 0.0

            current_defaults = [opt for opt in line["items"] if opt in roll_options]
            if not current_defaults and last_roll_selected and last_roll_selected in roll_options:
                current_defaults = [last_roll_selected]

            line["items"] = st.multiselect(
                "Select source roll(s)",
                options=roll_options,
                default=current_defaults,
                key=f"r_source_{i}"
            )

            if line["items"]:
                last_roll_selected = line["items"][0]

    if st.button("➕ Add another roll size", use_container_width=True):
        st.session_state.roll_lines.append({
            "display_size": "#2", "pieces": 0, "waste": 0.0,
            "items": [], "use_custom": False, "custom_inches": 12.0
        })
        st.rerun()

    st.divider()

    # ── SUBMISSION FORM ─────────────────────────────────────────────────────────────
    with st.form("production_order_form", clear_on_submit=True):
        st.markdown("#### 📑 Order Information")
        col1, col2, col3 = st.columns(3)
        with col1:
            client_name = st.text_input("Client Name", key="prod_client")
        with col2:
            order_number = st.text_input("Internal Order #", key="prod_order")
        with col3:
            operator_name = st.text_input(
                "Operator Name",
                value=st.session_state.get('username', ''),
                key="prod_operator"
            )

        st.markdown("#### 📦 Box Usage")
        box_types = [
            "Small Metal Box", "Big Metal Box",
            "Small Elbow Box", "Medium Elbow Box", "Large Elbow Box"
        ]
        box_usage = {box: st.number_input(box, min_value=0, step=1, key=f"box_{box.replace(' ','_')}") 
                     for box in box_types}

        submitted = st.form_submit_button("🚀 Complete Order & Deduct Stock", use_container_width=True, type="primary")

    if submitted:
        if not all([client_name.strip(), order_number.strip(), operator_name.strip()]):
            st.error("Client Name, Order Number, and Operator Name are required.")
        else:
            feedback = []
            deduction_details = []
            success = True

            # Process Coils
            for line in st.session_state.coil_lines:
                ok, ft = process_production_line(
                    line, coil_extra, "Coil",
                    order_number, client_name, operator_name,
                    feedback, deduction_details
                )
                if not ok:
                    success = False
                    break

            # Process Rolls
            if success:
                for line in st.session_state.roll_lines:
                    ok, ft = process_production_line(
                        line, roll_extra, "Roll",
                        order_number, client_name, operator_name,
                        feedback, deduction_details
                    )
                    if not ok:
                        success = False
                        break

            if success:
                st.success(f"Order **{order_number}** completed successfully! 🎉")
                for msg in feedback:
                    st.info(msg)

                pdf_buffer = generate_production_pdf(
                    order_number=order_number,
                    client_name=client_name,
                    operator_name=operator_name,
                    deduction_details=deduction_details,
                    box_usage=box_usage
                )

                if send_production_pdf(pdf_buffer, order_number, client_name):
                    st.balloons()
                    st.success("PDF generated and emailed to admin! Form cleared.")
                else:
                    st.warning("PDF generated, but email failed. Form cleared anyway.")

                st.session_state.coil_lines = []
                st.session_state.roll_lines = []

                st.cache_data.clear()
                st.rerun()

            else:
                st.error("Order failed — no changes were saved.")
                for msg in feedback:
                    if msg.startswith("✗"):
                        st.error(msg)                            
with tab3:
    st.subheader("🛒 Stock Picking & Sales")
    st.caption("Perform instant stock removals. Updates will sync across all tablets immediately.")

    # 1. Filter Data based on Category Selection
    # Note: We use singular names here to match our new database cleaning logic
    pick_cat = st.selectbox("What are you picking?", ["Fab Strap", "Roll", "Elbow", "Mineral Wool", "Coil"], key="pick_cat_sales")
    
    # Filter the cached dataframe
    filtered_df = df[df['Category'] == pick_cat]

    with st.form("dedicated_pick_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        with col1:
            if filtered_df.empty:
                st.warning(f"⚠️ No items currently in stock for {pick_cat}")
                selected_mat = None
            else:
                mat_options = sorted(filtered_df['Material'].unique())
                selected_mat = st.selectbox("Select Size / Material", mat_options)

        with col2:
            if selected_mat:
                # Logic for Serialized items (Rolls/Coils) vs Bulk items
                if pick_cat in ["Roll", "Coil"]:
                    specific_ids = filtered_df[filtered_df['Material'] == selected_mat]['Item_ID'].tolist()
                    pick_id = st.selectbox("Select Serial # to Sell", specific_ids)
                    pick_qty = 0 # For serialized, we set footage to 0
                else:
                    # Bulk items use the Material name as ID for the database update
                    pick_id = "BULK" 
                    pick_qty = st.number_input("Quantity to Remove", min_value=1, step=1)

        st.divider()
        
        c1, c2 = st.columns(2)
        customer = c1.text_input("Customer / Job Name", placeholder="e.g. John Doe / Site A")
        # Fallback to 'Admin' if session state username isn't set yet
        picker_name = c2.text_input("Authorized By", value=st.session_state.get("username", "Admin"))

        submit_pick = st.form_submit_button("📤 Confirm Stock Removal", use_container_width=True)

    # --- 2. THE HIGH-SPEED PROCESSING ---
    if submit_pick and selected_mat:
        if not customer:
            st.error("⚠️ Please enter a Customer or Job Name before confirming.")
        else:
            success = False
            
            # CASE A: Serialized (Rolls/Coils) -> Set Footage to 0
            if pick_cat in ["Roll", "Coil"]:
                with st.spinner("Updating Cloud Database..."):
                    success = update_stock(
                        item_id=pick_id, 
                        new_footage=0, 
                        user_name=picker_name, 
                        action_type=f"Sold {pick_cat} to {customer}"
                    )
            
            # CASE B: Bulk Items (Elbows, Straps) -> Subtract Quantity
            else:
                # Find current stock for this specific bulk item
                mask = (df['Category'] == pick_cat) & (df['Material'] == selected_mat)
                current_stock = df.loc[mask, 'Footage'].values[0]
                bulk_item_id = df.loc[mask, 'Item_ID'].values[0] # Get the unique ID
                
                if current_stock >= pick_qty:
                    new_total = current_stock - pick_qty
                    with st.spinner("Processing Bulk Removal..."):
                        success = update_stock(
                            item_id=bulk_item_id, 
                            new_footage=new_total, 
                            user_name=picker_name, 
                            action_type=f"Removed {pick_qty} for {customer}"
                        )
                else:
                    st.error(f"❌ Not enough stock! Current balance: {current_stock}")

            # FINAL FEEDBACK
            if success:
                st.toast(f"Stock Updated for {customer}!", icon="✅")
                st.balloons()
                # Forces the app to re-pull the data from Supabase so the change is visible everywhere
                st.rerun()
with tab4:
    st.subheader("📦 Smart Inventory Receiver")
    
    # 1. High-Level Category Selection
    # Using the standard singular names we set up for the database
    cat_mapping = {
        "Coils": "Coil", "Rolls": "Roll", "Elbows": "Elbow", 
        "Fab Straps": "Fab Strap", "Mineral Wool": "Mineral Wool", "Other": "Other"
    }
    
    raw_cat = st.radio(
        "What are you receiving?", 
        list(cat_mapping.keys()),
        horizontal=True
    )
    cat_choice = cat_mapping[raw_cat]

    with st.form("smart_receive_form", clear_on_submit=True):
        # --- DYNAMIC MATERIAL BUILDER (Your Original Logic) ---
        if cat_choice == "Elbow":
            col1, col2 = st.columns(2)
            angle = col1.selectbox("Angle", ["45°", "90°"])
            size = col2.number_input("Size (1-60)", min_value=1, max_value=60, value=1)
            material = f"{angle} Elbow - Size {size}"
            qty_val = 1.0 
            unit_label = "Pieces"

        elif cat_choice == "Fab Strap":
            col1, col2 = st.columns(2)
            gauge = col1.selectbox("Gauge", [".015", ".020"])
            size_num = col2.number_input("Size Number", min_value=1, max_value=50, value=1)
            material = f"Fab Strap {gauge} - #{size_num}"
            qty_val = 1.0  
            unit_label = "Bundles"

        elif cat_choice == "Mineral Wool":
            col1, col2 = st.columns(2)
            p_size = col1.text_input("Pipe Size", placeholder="e.g. 2-inch")
            thick = col2.text_input("Thickness", placeholder="e.g. 1.5-inch")
            material = f"Min Wool: {p_size} x {thick}"
            qty_val = 1.0
            unit_label = "Sections"

        elif cat_choice == "Other":
            cat_choice = st.text_input("New Category Name", placeholder="e.g. Insulation")
            material = st.text_input("Material Description", placeholder="e.g. Fiberglass Roll")
            qty_val = st.number_input("Qty/Footage per item", min_value=0.1, value=1.0)
            unit_label = "Units"
        
        else: # Coils and Rolls
            # Ensure COIL_MATERIALS and ROLL_MATERIALS lists are defined at the top of your script
            material = st.selectbox("Material Type", COIL_MATERIALS if cat_choice == "Coil" else ROLL_MATERIALS)
            qty_val = st.number_input("Footage per Item", min_value=0.1, value=3000.0 if cat_choice == "Coil" else 100.0)
            unit_label = "Footage"

        st.markdown("---")
        
        # --- LOCATION & QUANTITY ---
        item_count = st.number_input(f"How many {unit_label} are you receiving?", min_value=1, value=1, step=1)
        
        st.markdown("#### Location Selector")
        loc_type = st.radio("Storage Type", ["Rack System", "Floor / Open Space"], horizontal=True)
        if loc_type == "Rack System":
            l1, l2, l3 = st.columns(3)
            bay = l1.number_input("Bay", min_value=1, value=1)
            sec = l2.selectbox("Section", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
            lvl = l3.number_input("Level", min_value=1, value=1)
            gen_loc = f"{bay}{sec}{lvl}"
        else:
            gen_loc = st.text_input("Floor Zone Name", value="FLOOR").strip().upper()

        st.info(f"📍 **Assigned Location:** {gen_loc}")

        # ID Generation
        prefix = cat_choice.upper()[:4]
        starting_id = st.text_input("Starting ID", value=f"{prefix}-1001")
        operator = st.text_input("Receiving Operator", value=st.session_state.get("username", ""))

        submitted = st.form_submit_button("📥 Add to Cloud Inventory", use_container_width=True)

    # --- UPDATED SAVE LOGIC (SUPABASE) ---
    if submitted:
        if not operator:
            st.error("Operator name is required.")
        else:
            with st.spinner("Syncing with Cloud..."):
                is_bulk = cat_choice not in ["Coil", "Roll"]
                
                if is_bulk:
                    # Look for existing material in current df
                    mask = (df['Material'] == material) & (df['Category'] == cat_choice)
                    
                    if mask.any():
                        # UPDATE EXISTING BULK
                        old_qty = df.loc[mask, 'Footage'].values[0]
                        new_qty = old_qty + item_count
                        bulk_id = df.loc[mask, 'Item_ID'].values[0]
                        update_stock(bulk_id, new_qty, operator, f"Added {item_count} stock")
                    else:
                        # CREATE NEW BULK ROW
                        new_id = f"{cat_choice.upper()}-BULK"
                        new_data = {"Item_ID": new_id, "Material": material, "Footage": item_count, 
                                    "Location": gen_loc, "Status": "Active", "Category": cat_choice}
                        supabase.table("inventory").insert(new_data).execute()
                        update_stock(new_id, item_count, operator, "Created Bulk Item")
                
                else:
                    # SERIALIZED (COILS/ROLLS) - Add multiple unique rows
                    try:
                        parts = starting_id.strip().upper().split("-")
                        base = "-".join(parts[:-1])
                        start_num = int(parts[-1])
                        
                        new_rows = []
                        for i in range(item_count):
                            unique_id = f"{base}-{start_num + i}"
                            new_rows.append({
                                "Item_ID": unique_id, "Material": material, "Footage": qty_val,
                                "Location": gen_loc, "Status": "Active", "Category": cat_choice
                            })
                        
                        supabase.table("inventory").insert(new_rows).execute()
                        st.cache_data.clear()
                    except:
                        st.error("ID format error. Use ID-101 format.")

                st.success("Database Updated!")
                st.rerun()

    st.divider()
    
    # --- MOVE ITEM SECTION (SUPABASE) ---
    st.markdown("### 🚚 Move Item")
    col_m1, col_m2 = st.columns([2, 1])
    move_id = col_m1.selectbox("Select Item ID to Move", df['Item_ID'].unique())
    new_move_loc = col_m2.text_input("New Location")
    
    if st.button("Confirm Move", use_container_width=True):
        if move_id and new_move_loc:
            supabase.table("inventory").update({"Location": new_move_loc.strip().upper()}).eq("Item_ID", move_id).execute()
            st.cache_data.clear()
            st.toast(f"Moved {move_id} to {new_move_loc}")
            st.rerun()            
import google.generativeai as genai
import plotly.express as px
import plotly.graph_objects as go

with tab5:
    st.subheader("📈 Inventory Analytics & AI Assistant")

    # 1. HARD-CODED CONFIGURATION TO BYPASS 404
    GEMINI_KEY = st.secrets.get("GEMINI_API_KEY", "----")
    
    try:
        # Force the library to use the stable 'v1' API instead of 'v1beta'
        genai.configure(api_key=GEMINI_KEY, transport='rest')
        
        # Use the 'latest' alias which is the most reliable endpoint
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        
    except Exception as e:
        st.error(f"Configuration Error: {e}")

    if not df.empty:
        # --- [SECTION: GAUGE & CHARTS CODE REMAINS THE SAME] ---
        # (Keeping the charts here ensures they don't disappear)
        total_ft = df['Footage'].sum()
        target_capacity = 50000.0  
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = total_ft,
            title = {'text': "Total Warehouse Footage"},
            gauge = {'axis': {'range': [None, target_capacity]}, 'bar': {'color': "#1E3A8A"}}
        ))
        st.plotly_chart(fig_gauge, use_container_width=True)

        col1, col2 = st.columns(2)
        with col1:
            fig_pie = px.pie(df, names='Category', values='Footage', hole=0.4, color_discrete_sequence=px.colors.qualitative.Bold)
            st.plotly_chart(fig_pie, use_container_width=True)
        with col2:
            mat_sum = df.groupby(['Material', 'Category'])['Footage'].sum().nlargest(10).reset_index()
            fig_bar = px.bar(mat_sum, x='Footage', y='Material', orientation='h', color='Category', color_discrete_sequence=px.colors.qualitative.Bold)
            st.plotly_chart(fig_bar, use_container_width=True)

        st.divider()

        # --- 2. UPDATED AI ASSISTANT LOGIC ---
        st.markdown("### 🤖 MJP Pulse AI Assistant")
        user_q = st.text_input("Ask about stock levels, reorders, or trends:", key="final_ai_fix")

        if user_q:
            # Quick check: Is the key valid?
            if not GEMINI_KEY.startswith("AIza"):
                st.error("The API Key format looks incorrect. Please check Google AI Studio.")
            else:
                with st.spinner("🤖 Connecting to stable AI engine..."):
                    inventory_text = df[['Material', 'Footage', 'Category']].to_string()
                    prompt = f"Warehouse Data:\n{inventory_text}\n\nTask: {user_q}\nRules: RPR=200ft/roll, Others=100ft/roll."
                    
                    try:
                        # Call the model
                        response = model.generate_content(prompt)
                        
                        if response.text:
                            st.info(response.text)
                            st.download_button("📥 Download Report", response.text, file_name="MJP_Report.txt")
                    
                    except Exception as e:
                        # If it still fails, it's likely a key restriction/billing issue
                        st.error(f"Final Attempt Failed: {e}")
                        st.markdown("""
                        **Possible fixes:**
                        1. Go to [Google AI Studio](https://aistudio.google.com/)
                        2. Create a **NEW** API Key.
                        3. Ensure the **Generative Language API** is enabled in your Google Cloud Project.
                        """)
    else:
        st.info("No data available.")
        
with tab6:
    st.subheader("📜 System Audit Log")
    st.caption("Complete history of material movements, production runs, and admin submissions.")

    try:
        # 1. Access the Worksheet using your specific name
        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        
        try:
            audit_ws = sh.worksheet("Audit_Log")
            audit_records = audit_ws.get_all_records()
        except gspread.exceptions.WorksheetNotFound:
            st.error("The worksheet 'Audit_Log' was not found. Please check your Google Sheet tabs.")
            st.stop()

        if not audit_records:
            st.info("No audit logs recorded yet. Logs will appear here as materials are picked or produced.")
        else:
            audit_df = pd.DataFrame(audit_records)
            
            # Ensure Timestamp is handled correctly
            audit_df['Timestamp'] = pd.to_datetime(audit_df['Timestamp'], errors='coerce')
            
            # 2. FILTER & SEARCH BAR
            search_col, filter_col = st.columns([2, 1])
            with search_col:
                query = st.text_input("🔍 Search Logs", placeholder="Search Order #, Operator, or Action...")
            with filter_col:
                # Allows you to quickly see only Production submissions
                actions = ["All"] + sorted(audit_df['Action'].unique().tolist())
                selected_action = st.selectbox("Filter by Action", actions)

            # Apply Filters
            if selected_action != "All":
                audit_df = audit_df[audit_df['Action'] == selected_action]
            
            if query:
                audit_df = audit_df[audit_df.astype(str).apply(lambda x: x.str.contains(query, case=False)).any(axis=1)]

            # 3. DISPLAY THE LOG
            # Sorting so newest is at the top
            audit_df = audit_df.sort_values('Timestamp', ascending=False)

            # Styled Dataframe for a clean "Log" look
            st.dataframe(
                audit_df[['Timestamp', 'Action', 'User', 'Details']], 
                use_container_width=True, 
                hide_index=True
            )

    except Exception as e:
        st.error(f"Audit Log Display Error: {e}")
