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

# --- DATABASE CONNECTION ---
# This pulls the credentials you just saved in the "Secrets" section
# --- 2. DATABASE CONNECTION (SMART VERSION) ---
# --- 2. DATABASE CONNECTION (TOP LEVEL) ---
@st.cache_resource 
def init_connection():
    try:
        # Check if secrets exist
        if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
            return None
        
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except:
        return None

# THIS LINE MUST BE OUTSIDE ANY FUNCTION
supabase = init_connection()

# --- 3. UPDATED DATA LOADER ---
@st.cache_data(ttl=300)
def load_all_tables():
    if supabase is None:
        return pd.DataFrame(), pd.DataFrame()
    
    try:
        # Fetching from the table named 'inventory'
        inv_res = supabase.table("inventory").select("*").execute()
        df_inv = pd.DataFrame(inv_res.data)
        
        # Fetching from the table named 'audit_log' (NO 'S')
        audit_res = supabase.table("audit_log").select("*").execute()
        df_audit = pd.DataFrame(audit_res.data)
        
        return df_inv, df_audit
    except Exception as e:
        # This will catch the error and tell us the table name causing it
        st.error(f"Error loading tables: {e}")
        return pd.DataFrame(), pd.DataFrame()
# MUST BE THE FIRST ST COMMAND
st.set_page_config(
    page_title="MJP Pulse Inventory",
    page_icon="⚡", # You can use an emoji or a URL to your logo image
    layout="wide"
)

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
# --- 1. PAGE CONFIG (Must be at the very top) ---
st.set_page_config(
    page_title="MJP Pulse Inventory",
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- 2. PWA & PROFESSIONAL STYLING ---
st.markdown("""
    <style>
        /* PWA Meta Tags (Injected into Header) */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
        
        /* Professional Title Styling */
        .main-title {
            font-family: 'Inter', sans-serif;
            font-weight: 800;
            color: #1E3A8A;
            font-size: 42px;
            margin-bottom: 0px;
        }
        .sub-title {
            font-family: 'Inter', sans-serif;
            color: #64748B;
            font-size: 16px;
            margin-top: -15px;
            margin-bottom: 20px;
        }
        /* Sidebar Polish */
        [data-testid="stSidebar"] {
            background-color: #f8fafc;
            border-right: 1px solid #e2e8f0;
        }
    </style>
    
    <head>
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
        <title>MJP Pulse</title>
    </head>
""", unsafe_allow_html=True)

# --- 3. SIDEBAR BRANDING ---
with st.sidebar:
    # Logo Logic
    try:
        st.image("logo.png", use_container_width=True)
    except:
        st.markdown("<h1 style='text-align: center;'>⚡ MJP</h1>", unsafe_allow_html=True)
    try:
        # Try a tiny query just to check the pulse
        supabase.table("inventory").select("count", count="exact").limit(1).execute()
        st.success("🛰️ Database: Online")
    except Exception:
        st.error("🛰️ Database: Offline")
    
    st.divider()
    
    # User Status Card
    st.markdown(f"""
        <div style="background-color: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 20px;">
            <p style="margin:0; color: #64748B; font-size: 12px; font-weight: bold; text-transform: uppercase;">Current Operator</p>
            <p style="margin:0; color: #1E3A8A; font-size: 18px; font-weight: bold;">{st.session_state.get('username', 'Admin User')}</p>
        </div>
    """, unsafe_allow_html=True)

# --- OFFLINE NOTIFICATION SYSTEM ---
st.markdown("""
    <script>
        const updateOnlineStatus = () => {
            const condition = navigator.onLine ? "online" : "offline";
            if (condition === "offline") {
                // Show a clean red alert at the top of the screen
                const div = document.createElement("div");
                div.id = "offline-warning";
                div.style = "position: fixed; top: 0; left: 0; width: 100%; background: #ef4444; color: white; text-align: center; padding: 10px; z-index: 9999; font-family: sans-serif; font-weight: bold;";
                div.innerHTML = "⚠️ Wi-Fi Connection Lost. Please check your signal to save changes.";
                document.body.appendChild(div);
            } else {
                // Remove the alert if back online
                const warning = document.getElementById("offline-warning");
                if (warning) warning.remove();
            }
        };

        window.addEventListener('online', updateOnlineStatus);
        window.addEventListener('offline', updateOnlineStatus);
    </script>
""", unsafe_allow_html=True)

    # Global Actions
if st.button("🔄 Sync Cloud Data", use_container_width=True):
    st.cache_data.clear()
    st.toast("Pulling fresh data from Supabase...")
    st.rerun()
    
    st.divider()
    # Your Tab/Navigation code usually follows here...

# --- 4. MAIN PAGE HEADER ---
st.markdown('<p class="main-title">MJP Pulse</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Precision Inventory & Logistics Engine</p>', unsafe_allow_html=True) 

st.divider()

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

# --- 1. THE DATA ENGINE (REPLACE YOUR OLD GOOGLE CONNECTION WITH THIS) ---
@st.cache_data(ttl=300)
def load_all_tables():
    try:
        # 1. Fetch Inventory
        inv_response = supabase.table("inventory").select("*").execute()
        df_inv = pd.DataFrame(inv_response.data)
        
        # 2. Fetch Audit Logs
        audit_response = supabase.table("audit_log").select("*").execute()
        df_audit = pd.DataFrame(audit_response.data)
        
        # 3. Fetch log data
        log_response = supabase.table("log_data").select("*").execute()
        df_log = pd.DataFrame(log_response.data)

        # 4 Fetch Production log
        prod_response = supabase.table("production_log").select("*").execute()
        df_prod = pd.DataFrame(prod_response.data)
        
        return df_inv, df_audit
    except Exception as e:
        st.error(f"Error loading tables: {e}")
        return pd.DataFrame(), pd.DataFrame()

# Initialize both
if 'df' not in st.session_state or 'df_audit' not in st.session_state:
    st.session_state.df, st.session_state.df_audit = load_all_tables()

df = st.session_state.df
df_audit = st.session_state.df_audit

# --- SAVE FUNCTION (PROTECTED VERSION) ---
def save_inventory():
    try:
        # 1. Safety Check: If the dataframe is empty, DO NOT SAVE.
        # This prevents accidental wiping of your Google Sheet.
        if st.session_state.df is None or st.session_state.df.empty:
            st.error("⚠️ CRITICAL: Inventory data is empty. Save aborted to prevent data loss.")
            return

        gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
        sh = gc.open_by_url(st.secrets["SHEET_URL"])
        inv_ws = sh.worksheet("Inventory")

        # 2. Prepare the data for Google Sheets
        # We use the current state of 'df' to create the list for the sheet
        new_data = [st.session_state.df.columns.tolist()] + st.session_state.df.values.tolist()

        # 3. Update the worksheet
        inv_ws.clear()
        inv_ws.update('A1', new_data)
        
        # A small notification that disappears after a few seconds
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
        
def update_stock(item_id, new_footage, user_name, action_type):
    try:
        # Update the Inventory table
        supabase.table("inventory").update({"Footage": new_footage}).eq("Item_ID", item_id).execute()
        
        # Insert into the Audit Log table
        log_entry = {
            "Item_ID": item_id,
            "Action": action_type,
            "User": user_name,
            "Timestamp": datetime.now().isoformat()
        }
        supabase.table("audit_logs").insert(log_entry).execute()
        
        # CRITICAL: Clear cache so the app pulls the new numbers immediately
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update database: {e}")
        return False

# --- TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Dashboard", "Production Log", "Stock Picking", "Manage", "Insights", "Audit Trail"])

with tab1:
    # 1. Dashboard Navigation
    if not df.empty:
        available_categories = sorted(df['Category'].unique().tolist())
        view_options = ["All Materials"] + available_categories
        
        selected_view = st.radio(
            "Select Dashboard View", 
            view_options, 
            horizontal=True,
            help="Switch between Coils, Rolls, or other material categories"
        )
        
        # Filter data based on selection
        if selected_view == "All Materials":
            display_df = df.copy()
            st.subheader("📊 Global Material Pulse")
        else:
            display_df = df[df['Category'] == selected_view].copy()
            st.subheader(f"📊 {selected_view} Inventory Pulse")

        # 2. DATA AGGREGATION
        summary_df = display_df.groupby(['Material', 'Category']).agg({
            'Footage': 'sum',
            'Item_ID': 'count'
        }).reset_index()
        summary_df.columns = ['Material', 'Type', 'Total_Footage', 'Unit_Count']

        # 3. TOP-LEVEL METRICS
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
                cat_type = row['Type'] 
                
                # --- A. SET DEFAULTS ---
                display_value = f"{ft:,.1f}"
                unit_text = "Units"
                sub_label_text = "In Stock"

                # --- B. LOGIC BRANCHES ---
                if cat_type == "Rolls":
                    # Smart check for RPR 200ft vs Standard 100ft
                    divisor = 200 if "RPR" in mat.upper() else 100
                    roll_qty = ft / divisor
                    display_value = f"{roll_qty:.1f}"
                    unit_text = f"Rolls ({divisor}ft)"
                    sub_label_text = f"Total: {ft:,.1f} FT"
                
                elif cat_type == "Coils":
                    display_value = f"{ft:,.1f}"
                    unit_text = "FT"
                    sub_label_text = f"{int(units)} Separate Coils"
                
                elif cat_type == "Fab Straps":
                    display_value = f"{int(ft)}"
                    unit_text = "Bundles"
                    sub_label_text = "Standard Stock"

                elif cat_type == "Elbows":
                    display_value = f"{int(ft)}"
                    unit_text = "Pcs"
                    sub_label_text = "Standard Stock"

                # --- C. THRESHOLD / HEALTH LOGIC ---
                limit = LOW_STOCK_THRESHOLDS.get(mat, 10.0 if cat_type in ["Fab Straps", "Elbows"] else 1000.0)
                
                if ft < limit:
                    status_color, status_text = "#FF4B4B", "🚨 REORDER REQUIRED"
                elif ft < (limit * 1.5):
                    status_color, status_text = "#FFA500", "⚠️ MONITOR CLOSELY"
                else:
                    status_color, status_text = "#00C853", "✅ STOCK HEALTHY"

                # --- D. RENDER THE CARD ---
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

        # 5. INDIVIDUAL ITEM TABLE
        with st.expander(f"🔍 View {selected_view} Serial Numbers / Detail"):
            st.dataframe(
                display_df[['Item_ID', 'Category', 'Material', 'Footage', 'Location']].sort_values('Material'), 
                use_container_width=True, 
                hide_index=True
            )
    else:
        st.info("No data available. Add inventory in the Warehouse tab.")
# --- TAB 2: PRODUCTION LOG ---
with tab2:
    st.subheader("📋 Production Log - Multi-Size Orders")

    # 1. Guard Rail: Check if data exists
    if df.empty:
        st.warning("⚠️ No data found in the 'inventory' table. Please add items in the Warehouse tab.")
        st.stop()

    # 2. Case-Insensitive Column Check for 'Category'
    cols_map = {c.lower(): c for c in df.columns}
    category_col = cols_map.get('category')

    if not category_col:
        st.error(f"🚨 Column 'Category' not found in database. Found: {list(df.columns)}")
        st.stop()

    # 3. Initialize Session State for dynamic lines if they don't exist
    if "coil_lines" not in st.session_state:
        st.session_state.coil_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []}]
    if "roll_lines" not in st.session_state:
        st.session_state.roll_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []}]

    # 4. Safe Filtering
    available_coils = df[(df[category_col] == "Coil") & (df['Footage'] > 0)]
    available_rolls = df[(df[category_col] == "Roll") & (df['Footage'] > 0)]

    if available_coils.empty and available_rolls.empty:
        st.info("No available stock for Coils or Rolls.")
        st.stop()

    # --- COILS SECTION ---
    st.markdown("### 🌀 Coils Production")
    coil_extra = st.number_input("Coil Extra Inch Allowance (per piece)", min_value=0.0, value=0.5, step=0.1, key="c_allowance_bar")
    
    coil_options = [f"{r['Item_ID']} - {r['Material']} ({r['Footage']:.1f} ft)" for _, r in available_coils.iterrows()]

    for i, line in enumerate(st.session_state.coil_lines):
        with st.container():
            c1, c2, c3, c4 = st.columns([2, 1, 1, 0.5])
            with c1:
                line["display_size"] = st.selectbox(f"Coil Size {i+1}", list(SIZE_DISPLAY.keys()), key=f"c_sz_{i}")
            with c2:
                line["pieces"] = st.number_input(f"Pcs {i+1}", min_value=0, value=line["pieces"], key=f"c_pcs_{i}")
            with c3:
                line["waste"] = st.number_input(f"Waste (ft) {i+1}", min_value=0.0, value=line["waste"], key=f"c_wst_{i}")
            with c4:
                if st.button("🗑️", key=f"rm_c_{i}"):
                    st.session_state.coil_lines.pop(i)
                    st.rerun()
            
            # Validation for selections
            valid_coil_defaults = [item for item in line["items"] if item in coil_options]
            line["items"] = st.multiselect(f"Source Coils {i+1}", coil_options, default=valid_coil_defaults, key=f"c_sel_{i}")

    if st.button("➕ Add Coil Size Line"):
        st.session_state.coil_lines.append({"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []})
        st.rerun()

    st.divider()

    # --- ROLLS SECTION ---
    st.markdown("### 🗞️ Rolls Production")
    roll_extra = st.number_input("Roll Extra Inch Allowance (per piece)", min_value=0.0, value=0.5, step=0.1, key="r_allowance_bar")

    roll_options = [f"{r['Item_ID']} - {r['Material']} ({r['Footage']:.1f} ft)" for _, r in available_rolls.iterrows()]

    for i, line in enumerate(st.session_state.roll_lines):
        with st.container():
            r1, r2, r3, r4 = st.columns([2, 1, 1, 0.5])
            with r1:
                line["display_size"] = st.selectbox(f"Roll Size {i+1}", list(SIZE_DISPLAY.keys()), key=f"r_sz_{i}")
            with r2:
                line["pieces"] = st.number_input(f"Pcs {i+1}", min_value=0, value=line["pieces"], key=f"r_pcs_{i}")
            with r3:
                line["waste"] = st.number_input(f"Waste (ft) {i+1}", min_value=0.0, value=line["waste"], key=f"r_wst_{i}")
            with r4:
                if st.button("🗑️", key=f"rm_r_{i}"):
                    st.session_state.roll_lines.pop(i)
                    st.rerun()
            
            valid_roll_defaults = [item for item in line["items"] if item in roll_options]
            line["items"] = st.multiselect(f"Source Rolls {i+1}", roll_options, default=valid_roll_defaults, key=f"r_sel_{i}")

    if st.button("➕ Add Roll Size Line"):
        st.session_state.roll_lines.append({"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []})
        st.rerun()

    st.divider()
    
    # --- FINAL SUBMISSION FORM ---
    with st.form("production_submit_form"):
        st.markdown("#### 📑 Order Details")
        f1, f2, f3 = st.columns(3)
        with f1: client_name = st.text_input("Client Name")
        with f2: order_number = st.text_input("Internal Order #")
        with f3: operator_name = st.text_input("Operator Name")

        st.markdown("#### 📦 Box Usage")
        box_types = ["Small Metal Box", "Big Metal Box", "Small Elbow Box", "Medium Elbow Box", "Large Elbow Box"]
        box_usage = {box: st.number_input(box, min_value=0, step=1, key=f"box_{box}") for box in box_types}

        submitted = st.form_submit_button("🚀 Complete Order & Send PDF", use_container_width=True)

        if submitted:
            if not client_name or not order_number or not operator_name:
                st.error("Client, Order #, and Operator are required.")
            else:
                production_details = []
                
                # Process Coils logic
                for line in st.session_state.coil_lines:
                    if line["pieces"] > 0 and line["items"]:
                        base_inches = SIZE_MAP.get(line["display_size"].replace("#", "Size "), 0)
                        total_ft = (line["pieces"] * (base_inches + coil_extra) / 12) + line["waste"]
                        
                        target_id = line["items"][0].split(" - ")[0]
                        material_info = line["items"][0].split(" - ")[1].split(" (")[0]
                        
                        # Deduct from local dataframe
                        df.loc[df['Item_ID'] == target_id, 'Footage'] -= total_ft
                        
                        production_details.append({
                            "material": material_info, 
                            "display_size": line["display_size"],
                            "pieces": line["pieces"],
                            "waste": line["waste"],
                            "total_used": total_ft,
                            "items": target_id
                        })

                # Process Rolls logic
                for line in st.session_state.roll_lines:
                    if line["pieces"] > 0 and line["items"]:
                        base_inches = SIZE_MAP.get(line["display_size"].replace("#", "Size "), 0)
                        total_ft = (line["pieces"] * (base_inches + roll_extra) / 12) + line["waste"]
                        
                        target_id = line["items"][0].split(" - ")[0]
                        material_info = line["items"][0].split(" - ")[1].split(" (")[0]
                        
                        df.loc[df['Item_ID'] == target_id, 'Footage'] -= total_ft
                        
                        production_details.append({
                            "material": material_info,
                            "display_size": line["display_size"],
                            "pieces": line["pieces"],
                            "waste": line["waste"],
                            "total_used": total_ft,
                            "items": target_id
                        })

                if not production_details:
                    st.error("No production data entered.")
                else:
                    save_inventory() # Syncs with Google Sheets
                    save_production_log(order_number, client_name, operator_name, production_details, box_usage)
                    
                    pdf_buffer = generate_production_pdf(order_number, client_name, operator_name, production_details, box_usage, coil_extra)
                    
                    if send_production_pdf(pdf_buffer, order_number, client_name):
                        st.success(f"Order {order_number} Processed and Emailed!")
                        st.balloons()
                        # Reset session lines
                        st.session_state.coil_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []}]
                        st.session_state.roll_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": []}]
                        st.rerun()                            
with tab3:
    st.subheader("🛒 Sales & Picking")
    st.caption("Perform instant stock removals. Updates will sync across all devices immediately.")

# 1. IDENTIFY COLUMNS (Handles 'category' vs 'Category')
c_map = {c.lower(): c for c in df.columns}
col_cat = c_map.get('category', 'Category')
col_mat = c_map.get('material', 'Material')
col_id = c_map.get('item_id', 'Item_ID')
col_foot = c_map.get('footage', 'Footage')

# 2. SELECTION UI
pick_cat = st.selectbox("What are you picking?", ["Fab Strap", "Roll", "Elbow", "Mineral Wool", "Coil"], key="pick_cat_sales")

# 3. FILTER DATA (Case-Insensitive)
# This matches "Coil" from your UI to "coil" or "COIL" in your database
filtered_df = df[df[col_cat].astype(str).str.lower() == pick_cat.lower()]

with st.form("dedicated_pick_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    
    with col1:
        if filtered_df.empty:
            st.warning(f"⚠️ No items currently in stock for {pick_cat}")
            selected_mat = None
        else:
            # Get unique materials available
            mat_options = sorted(filtered_df[col_mat].unique())
            selected_mat = st.selectbox("Select Size / Material", mat_options)

    with col2:
        if selected_mat:
            # Filter specifically for the selected material
            mat_data = filtered_df[filtered_df[col_mat] == selected_mat]
            
            # Logic for Serialized items (Rolls/Coils) vs Bulk items
            if pick_cat in ["Roll", "Coil"]:
                # Show Serial #s/IDs and current footage for clarity
                specific_ids = [
                    f"{r[col_id]} ({r[col_foot]:.1f} ft)" for _, r in mat_data.iterrows()
                ]
                pick_selection = st.selectbox("Select Serial # to Sell", specific_ids)
                # Extract just the ID from the selection string
                pick_id = pick_selection.split(" (")[0]
                pick_qty = 0 # Serialized items are usually removed entirely
            else:
                # Bulk items
                pick_id = "BULK" 
                pick_qty = st.number_input("Quantity to Remove", min_value=1, step=1)
    
    submitted = st.form_submit_button("🚀 Confirm Removal", use_container_width=True)
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
