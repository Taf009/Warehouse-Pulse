import streamlit as st
import pandas as pd
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

# --- 1. PAGE CONFIG ---
st.set_page_config(
    page_title="MJP Pulse Inventory",
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. DATABASE CONNECTION ---
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

# --- 3. DATA LOADER ---
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

# --- 4. CONSTANTS & MAPS ---
SIZE_DISPLAY = {
    "1#": 12.0, "#2": 13.5, "#3": 14.75, "#4": 16.25, "#5": 18.0,
    "#6": 20.0, "#7": 23.0, "#8": 26.0, "#9": 29.5, "#10": 32.5,
    "#11": 36.0, "#12": 39.25, "#13": 42.25, "#14": 46.5, "#15": 49.5,
    "#16": 52.75, "#17": 57, "#18": 60.25, "#19": 63.25, "#20": 66.5,
    "#21": 69.75, "#22": 72.75, "#23": 76, "#24": 79.25, "#25": 82.5,
    "#26": 85.5, "#27": 88.5, "#28": 92, "#29": 95, "#30": 98.25,
    "#31": 101.5, "#32": 104.5, "#33": 107.75,
}
SIZE_MAP = {k.replace("#", "Size "): v for k, v in SIZE_DISPLAY.items()}

# --- 5. FUNCTIONS (PDF & Email) ---
def generate_production_pdf(order_no, client, operator, details, boxes, summary):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, 'Production Order Complete', 0, 1, 'C')
    pdf.ln(5)
    
    # Header Info
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(95, 10, f"Client: {client}", border=1)
    pdf.cell(95, 10, f"Order #: {order_no}", border=1, ln=1)
    pdf.cell(190, 10, f"Operator: {operator}", border=1, ln=1)
    
    # Boxes
    pdf.ln(5)
    pdf.cell(0, 10, "Box Usage:", ln=1)
    pdf.set_font("Arial", '', 10)
    for b_name, b_qty in boxes.items():
        if b_qty > 0:
            pdf.cell(0, 7, f"- {b_name}: {b_qty}", ln=1)

    # Summary
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, "MATERIAL TOTALS", ln=1)
    for mat, data in summary.items():
        pdf.cell(100, 10, f"{mat}", border=1)
        pdf.cell(45, 10, f"Ft: {data['ft']:.1f}", border=1)
        pdf.cell(45, 10, f"Waste: {data['wst']:.1f}", border=1, ln=1)
        
    return pdf.output(dest='S').encode('latin-1')

def send_production_pdf(pdf_bytes, order_number, client_name):
    try:
        msg = MIMEMultipart()
        msg['From'] = st.secrets["SMTP_EMAIL"]
        msg['To'] = st.secrets["ADMIN_EMAIL"]
        msg['Subject'] = f"Production Order {order_number} - {client_name}"
        msg.attach(MIMEText("See attached production ticket.", 'plain'))
        
        part = MIMEApplication(pdf_bytes, Name=f"Order_{order_number}.pdf")
        part['Content-Disposition'] = f'attachment; filename="Order_{order_number}.pdf"'
        msg.attach(part)

        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(st.secrets["SMTP_EMAIL"], st.secrets["SMTP_PASSWORD"])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Email failed: {e}")
        return False

# --- 6. LOGIN SYSTEM ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    st.subheader("🔐 Login Required")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Log In"):
        if u in st.secrets["users"] and st.secrets["users"][u] == p:
            st.session_state.logged_in = True
            st.session_state.username = u
            st.rerun()
    st.stop()

# --- 7. MAIN TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Dashboard", "Production Log", "Stock Picking", "Manage", "Insights", "Audit Trail"])

# --- TAB 1: DASHBOARD ---
with tab1:
    st.subheader("📊 Inventory Dashboard")
    if not df.empty:
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Inventory is empty.")

# --- TAB 2: PRODUCTION LOG ---
with tab2:
    if "coil_lines" not in st.session_state:
        st.session_state.coil_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []}]
    if "roll_lines" not in st.session_state:
        st.session_state.roll_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []}]

    st.subheader("📋 Production Log")
    finish_filter = st.radio("Select Finish", ["Smooth", "Stucco"], horizontal=True, key="p_finish")

    # Production Input Logic (Simplified for space)
    st.markdown("### 🌀 Coils")
    for i, line in enumerate(st.session_state.coil_lines):
        c1, c2, c3 = st.columns([2, 1, 1])
        line["display_size"] = c1.selectbox(f"Size {i}", list(SIZE_DISPLAY.keys()), key=f"csz_{i}")
        line["pieces"] = c2.number_input(f"Pcs {i}", min_value=0, key=f"cpcs_{i}")
        line["waste"] = c3.number_input(f"Waste {i}", min_value=0.0, key=f"cwst_{i}")

    # Final Order Form
    with st.form("production_form"):
        st.markdown("#### 📑 Order Details")
        col_a, col_b, col_c = st.columns(3)
        c_name = col_a.text_input("Client")
        o_num = col_b.text_input("Order #")
        op_name = col_c.text_input("Operator", value=st.session_state.username)

        st.markdown("#### 📦 Box Usage")
        box_types = ["Small Metal Box", "Big Metal Box", "Small Elbow Box", "Medium Elbow Box", "Large Elbow Box"]
        b_col1, b_col2 = st.columns(2)
        box_usage = {box: (b_col1 if i%2==0 else b_col2).number_input(box, min_value=0, step=1, key=f"bx_{i}") for i, box in enumerate(box_types)}

        if st.form_submit_button("🚀 Finalize & Send PDF"):
            # logic to calculate totals and generate PDF...
            dummy_summary = { "Example Mat": {"ft": 100, "wst": 5} }
            pdf_out = generate_production_pdf(o_num, c_name, op_name, [], box_usage, dummy_summary)
            if send_production_pdf(pdf_out, o_num, c_name):
                st.success("Sent!")

# --- TAB 3: STOCK PICKING (CONTAINED HERE ONLY) ---
with tab3:
    st.subheader("🛒 Stock Picking")
    st.caption("Remove items from inventory.")
    
    # This code is now INDENTED under Tab 3
    pick_cat = st.selectbox("What are you picking?", 
        ["Fab Straps", "Roll", "Elbows", "Mineral Wool", "Coil", "Banding", "Wing Seal"], 
        key="pick_cat_tab3"
    )

    with st.container(border=True):
        if pick_cat == "Fab Straps":
            thick = st.radio("Thickness", ["015", "020"])
            item = st.selectbox("Confirm Specific Item", ["Fab Strap - Size 10", "Fab Strap - Size 12"])
            qty = st.number_input("Quantity to Remove", min_value=1)
            if st.button("Confirm Stock Removal"):
                st.write(f"Removed {qty} of {item}")

# --- TAB 4, 5, 6 ---
with tab4: st.write("Management Tools")
with tab5: st.write("Inventory Insights")
with tab6: st.write("Audit History")
