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
    layout="wide"
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

# Initialize Global Data
if 'df' not in st.session_state or 'df_audit' not in st.session_state:
    st.session_state.df, st.session_state.df_audit = load_all_tables()

df = st.session_state.df
df_audit = st.session_state.df_audit

# --- 4. MAPS & THRESHOLDS ---
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
LOW_STOCK_THRESHOLDS = {
    ".016 Smooth Aluminum": 6000.0, ".020 Stucco Aluminum": 6000.0,
    ".020 Smooth Aluminum": 3500.0, ".016 Stucco Aluminum": 2500.0,
    ".010 Stainless Steel Polythene": 2500.0
}

# --- 5. PDF & EMAIL FUNCTIONS ---
def generate_production_pdf(order_no, client, operator, details, boxes, summary):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, 'Production Order Complete', 0, 1, 'C')
    pdf.ln(10)
    pdf.set_fill_color(204, 255, 204)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(95, 10, f"Client: {client}", border=1, fill=True)
    pdf.cell(95, 10, f"Order #: {order_no}", border=1, fill=True, ln=1)
    pdf.ln(5)
    pdf.cell(0, 10, "Box Usage Summary:", ln=1)
    pdf.set_font("Arial", '', 10)
    for b_name, b_qty in boxes.items():
        if b_qty > 0: pdf.cell(0, 7, f"- {b_name}: {b_qty}", ln=1)
    pdf.ln(10)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, "MATERIAL TOTALS (CONSOLIDATED)", ln=1)
    for mat, data in summary.items():
        pdf.cell(100, 10, f"{mat}", border=1)
        pdf.cell(45, 10, f"Total Ft: {data['ft']:.1f}", border=1)
        pdf.cell(45, 10, f"Waste: {data['wst']:.1f}", border=1, ln=1)
    return pdf.output(dest='S').encode('latin-1')

def send_production_pdf(pdf_bytes, order_number, client_name):
    try:
        msg = MIMEMultipart()
        msg['From'] = st.secrets["SMTP_EMAIL"]
        msg['To'] = st.secrets["ADMIN_EMAIL"]
        msg['Subject'] = f"Production Order {order_number} - {client_name}"
        msg.attach(MIMEText(f"Order {order_number} completed.", 'plain'))
        part = MIMEApplication(pdf_bytes, Name=f"Order_{order_number}.pdf")
        part['Content-Disposition'] = f'attachment; filename="Order_{order_number}.pdf"'
        msg.attach(part)
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(st.secrets["SMTP_EMAIL"], st.secrets["SMTP_PASSWORD"])
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        st.error(f"Email failed: {e}"); return False

# --- 6. AUTHENTICATION ---
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
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

# --- 7. TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Dashboard", "Production Log", "Stock Picking", "Manage", "Insights", "Audit Trail"])

# --- TAB 1: DASHBOARD ---
with tab1:
    if not df.empty:
        available_categories = sorted(df['Category'].unique().tolist())
        selected_view = st.radio("Select Dashboard View", ["All Materials"] + available_categories, horizontal=True)
        display_df = df.copy() if selected_view == "All Materials" else df[df['Category'] == selected_view].copy()
        
        summary_df = display_df.groupby(['Material', 'Category']).agg({'Footage': 'sum', 'Item_ID': 'count'}).reset_index()
        summary_df.columns = ['Material', 'Type', 'Total_Footage', 'Unit_Count']

        m1, m2, m3 = st.columns(3)
        m1.metric("Selected Footage", f"{display_df['Footage'].sum():,.1f} ft")
        m2.metric("Items in View", len(display_df))
        m3.metric("Material Types", len(summary_df))

        st.divider()
        cols = st.columns(2)
        for idx, row in summary_df.iterrows():
            with cols[idx % 2]:
                mat, ft, cat_type, units = row['Material'], row['Total_Footage'], row['Type'], row['Unit_Count']
                limit = LOW_STOCK_THRESHOLDS.get(mat, 1000.0)
                status_color = "#00C853" if ft >= limit else "#FF4B4B"
                st.markdown(f"""
                <div style="background-color: #f9f9f9; padding: 20px; border-radius: 12px; border-left: 12px solid {status_color}; margin-bottom: 15px; min-height: 160px;">
                    <p style="color: #666; font-size: 11px; margin: 0; font-weight: bold;">{cat_type.upper()}</p>
                    <h3 style="margin: 5px 0; font-size: 18px;">{mat}</h3>
                    <h1 style="margin: 10px 0; color: {status_color};">{ft:,.1f} <span style="font-size: 16px;">FT</span></h1>
                    <p style="color: #888; font-size: 11px; margin: 0;">{units} Serial IDs in Stock</p>
                </div>
                """, unsafe_allow_html=True)
    else: st.info("No data available.")

# --- TAB 2: PRODUCTION LOG ---
with tab2:
    if "coil_lines" not in st.session_state: st.session_state.coil_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []}]
    if "roll_lines" not in st.session_state: st.session_state.roll_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []}]

    st.subheader("📋 Production Log - Multi-Size Orders")
    finish_filter = st.radio("Select Material Finish", ["Smooth", "Stucco"], horizontal=True, key="p_fin")

    coil_opt = [f"{r['Item_ID']} - {r['Material']} ({r['Footage']:.1f} ft)" for _, r in df[(df['Category'].str.lower()=="coil") & (df['Material'].str.contains(finish_filter, case=False))].iterrows()]
    roll_opt = [f"{r['Item_ID']} - {r['Material']} ({r['Footage']:.1f} ft)" for _, r in df[(df['Category'].str.lower()=="roll") & (df['Material'].str.contains(finish_filter, case=False))].iterrows()]

    st.markdown(f"### 🌀 {finish_filter} Coils")
    c_extra = st.number_input("Coil Extra Inch Allowance", value=0.5, step=0.1, key="p_c_ex")
    for i, line in enumerate(st.session_state.coil_lines):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([2, 1, 1, 0.5])
            line["display_size"] = c1.selectbox(f"Size {i+1}", list(SIZE_DISPLAY.keys()), key=f"c_sz_{i}")
            line["pieces"] = c2.number_input(f"Pcs {i+1}", min_value=0, value=line["pieces"], key=f"c_p_{i}")
            line["waste"] = c3.number_input(f"Waste (ft) {i+1}", min_value=0.0, value=line["waste"], key=f"c_w_{i}")
            if c4.button("🗑️", key=f"rm_c_{i}"): 
                st.session_state.coil_lines.pop(i); st.rerun()
            line["items"] = st.multiselect(f"Source Material {i+1}", coil_opt, default=line["items"], key=f"c_s_{i}")
    if st.button("➕ Add Coil Line"): st.session_state.coil_lines.append({"display_size":"#2","pieces":0,"waste":0.0,"items":[]}); st.rerun()

    st.markdown(f"### 🗞️ {finish_filter} Rolls")
    r_extra = st.number_input("Roll Extra Inch Allowance", value=0.5, step=0.1, key="p_r_ex")
    for i, line in enumerate(st.session_state.roll_lines):
        with st.container(border=True):
            r1, r2, r3, r4 = st.columns([2, 1, 1, 0.5])
            line["display_size"] = r1.selectbox(f"Size {i+1}", list(SIZE_DISPLAY.keys()), key=f"r_sz_{i}")
            line["pieces"] = r2.number_input(f"Pcs {i+1}", min_value=0, value=line["pieces"], key=f"r_p_{i}")
            line
