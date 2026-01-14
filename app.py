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
from fpdf import FPDF
import io
from datetime import datetime
from collections import defaultdict

class PDF(FPDF):
    def header(self):
        # Add logo (adjust path/size as needed)
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

    # Table header - only "Type" (Coil/Roll), no Item ID
    pdf.set_font('Arial', 'B', 11)
    pdf.cell(45, 10, "Size / Pieces", border=1)
    pdf.cell(40, 10, "Type", border=1)          # NEW: just "Coil" or "Roll"
    pdf.cell(55, 10, "Material", border=1)
    pdf.cell(30, 10, "Footage (ft)", border=1)
    pdf.cell(30, 10, "Waste (ft)", border=1, ln=1)

    # Table rows
    pdf.set_font('Arial', '', 11)
    for line in deduction_details:
        size_pieces = f"{line['display_size']} / {line['pieces']} pcs"
        line_type = line.get('type', 'Unknown')  # "Coil" or "Roll"
        
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

    # Boxes used (safe dash handling)
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
    # Add more patterns as needed (e.g. "fab strap" vs "fab straps")
    return cat.capitalize()  # fallback

# Apply normalization
if 'Category' in df.columns:
    df['Category_normalized'] = df['Category'].apply(normalize_category)
    category_col = 'Category_normalized'  # Use this normalized column everywhere
else:
    st.warning("No 'Category' column found - normalization skipped")
    category_col = 'Category'  # fallback

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
        # Update inventory
        supabase.table("inventory").update({"Footage": new_footage}).eq("Item_ID", item_id).execute()
        
        # Log entry - ALWAYS include "Details" with a value
        log_entry = {
            "Item_ID": item_id,
            "Action": action_type,
            "User": user_name,
            "Timestamp": datetime.now().isoformat(),
            "Details": f"Updated Item {item_id} to {new_footage:.2f} ft via {action_type}"  # ← non-null value!
            # You can make this more detailed, e.g.:
            # "Details": f"Removed stock for {action_type.split('for ')[-1]} (new total: {new_footage:.2f})"
        }
        supabase.table("audit_log").insert(log_entry).execute()
        
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Failed to update database: {e}")
        return False
        
# ── HELPER: Process one production line (coil or roll) ───────────────────────────
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

        # Fresh read
        res = supabase.table("inventory").select("Footage").eq("Item_ID", item_id).execute()
        if not res.data:
            raise ValueError(f"Item {item_id} not found in inventory")

        current_ft = float(res.data[0]["Footage"])
        if current_ft < ft_needed - 0.01:
            raise ValueError(f"Insufficient stock ({material_type}): need {ft_needed:.2f} ft, have {current_ft:.2f} ft")

        new_footage = current_ft - ft_needed

        # CRITICAL UPDATE - with error checking
        update_response = supabase.table("inventory").update({"Footage": new_footage}).eq("Item_ID", item_id).execute()

        # Log the response for debugging (visible in logs)
        print(f"UPDATE RESPONSE for {item_id} ({material_type}): {update_response}")

        # If we got here, show success in app
        feedback.append(f"✓ {material_type} {item_id} – deducted {ft_needed:.2f} ft (Footage now: {new_footage:.2f})")
        st.toast(f"Inventory updated: {item_id} → {new_footage:.2f} ft", icon="✅")

        # Log to production_log2
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
        st.error(error_msg)  # Show real error in app
        return False, 0.0
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
# ── TAB 2: Production Log ────────────────────────────────────────────────────────
with tab2:
    st.subheader("📋 Production Log - Multi-Size Orders")

    # Guard rails
    if df.empty:
        st.warning("⚠️ No inventory data found. Please add items first.")
        st.stop()

    # Safe column name handling
    category_col = next((c for c in df.columns if c.lower() == 'category'), None)
    if not category_col:
        st.error("Column 'Category' not found in inventory data.")
        st.stop()

    # Initialize session state - start with one default line each
    if "coil_lines" not in st.session_state:
        st.session_state.coil_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": [], "use_custom": False, "custom_inches": 12.0}]
    if "roll_lines" not in st.session_state:
        st.session_state.roll_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "items": [], "use_custom": False, "custom_inches": 12.0}]

    # Material type toggle
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

    available_coils = filter_materials(df[(df[category_col] == "Coil") & (df['Footage'] > 0)])
    available_rolls = filter_materials(df[(df[category_col] == "Roll") & (df['Footage'] > 0)])

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

                # Generate PDF
                pdf_buffer = generate_production_pdf(
                    order_number=order_number,
                    client_name=client_name,
                    operator_name=operator_name,
                    deduction_details=deduction_details,
                    box_usage=box_usage
                )

                # Send email
                if send_production_pdf(pdf_buffer, order_number, client_name):
                    st.balloons()
                    st.success("PDF generated and emailed to admin! Form cleared.")
                else:
                    st.warning("PDF generated, but email failed. Form cleared anyway.")

                # Clear dynamic lines only (form fields auto-clear via clear_on_submit)
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
    st.caption("Perform instant stock removals. Updates sync across all devices in real-time.")

    # ── Local helper function - only for this tab (safe, no global changes) ─────
    def normalize_pick_category(cat):
        if pd.isna(cat) or not isinstance(cat, str):
            return "Unknown"
        
        cat_lower = str(cat).strip().lower()
        
        mapping = {
            'fab strap':     'Fab Straps',
            'fabstraps':     'Fab Straps',
            'fab straps':    'Fab Straps',
            'strap':         'Fab Straps',
            'straps':        'Fab Straps',
            'coil':          'Coils',
            'coils':         'Coils',
            'roll':          'Rolls',
            'rolls':         'Rolls',
            'elbow':         'Elbows',
            'elbows':        'Elbows',
            'mineral wool':  'Mineral Wool',
            'mineralwools':  'Mineral Wool',
            'mineral wools': 'Mineral Wool',
        }
        
        for key, value in mapping.items():
            if key in cat_lower:
                return value
        
        # Fallback - make it plural-ish if it doesn't look plural
        return cat.strip().title() + 's' if not cat.strip().endswith(('s', 'wool')) else cat.strip().title()

    # ── Work on a local copy only ───────────────────────────────────────────────
    pick_df = df.copy()
    if 'Category' in pick_df.columns:
        pick_df['Category'] = pick_df['Category'].apply(normalize_pick_category)

    # Consistent plural category options
    category_options = ["Fab Straps", "Rolls", "Elbows", "Mineral Wool", "Coils"]
    
    pick_cat = st.selectbox(
        "What are you picking?",
        category_options,
        key="pick_cat_sales"
    )
    
    # Filter using the locally normalized copy
    filtered_df = pick_df[pick_df['Category'] == pick_cat].copy()
    
    with st.form("dedicated_pick_form", clear_on_submit=True):
        
        # ── Two separate panels for Customer & Sales Order ──────────────────────
        st.markdown("#### 📋 Order & Customer Information")
        
        col_cust, col_order = st.columns(2, gap="medium")
        
        with col_cust:
            st.markdown("""
                <div style="background-color: #f0f7ff; padding: 20px; border-radius: 12px; 
                            border: 1px solid #d1e3ff; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <p style="font-weight: bold; margin: 0 0 12px 0; color: #1e40af;">Customer / Job</p>
            """, unsafe_allow_html=True)
            
            customer = st.text_input(
                "Customer / Job Name",
                placeholder="e.g. John Doe / Site A",
                key="pick_customer"
            )
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        with col_order:
            st.markdown("""
                <div style="background-color: #fff7e6; padding: 20px; border-radius: 12px; 
                            border: 1px solid #ffe8c2; box-shadow: 0 2px 8px rgba(0,0,0,0.05);">
                    <p style="font-weight: bold; margin: 0 0 12px 0; color: #92400e;">Sales Order</p>
            """, unsafe_allow_html=True)
            
            sales_order = st.text_input(
                "Sales Order Number",
                placeholder="e.g. SO-2026-0456",
                key="pick_sales_order"
            )
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.divider()
        
        # ── Material Selection ──────────────────────────────────────────────────
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
                if pick_cat in ["Rolls", "Coils"]:
                    specific_ids = filtered_df[filtered_df['Material'] == selected_mat]['Item_ID'].tolist()
                    pick_id = st.selectbox("Select Serial # to Sell", specific_ids or ["No items available"])
                    pick_qty = 0
                else:
                    pick_id = "BULK"
                    pick_qty = st.number_input("Quantity to Remove", min_value=1, step=1)

        st.divider()
        
        # Authorized By (single field, below panels)
        picker_name = st.text_input(
            "Authorized By",
            value=st.session_state.get("username", "Admin"),
            key="pick_authorized"
        )

        submit_pick = st.form_submit_button("📤 Confirm Stock Removal", use_container_width=True, type="primary")

    # ── Processing logic ────────────────────────────────────────────────────────
    if submit_pick and selected_mat:
        if not customer.strip():
            st.error("⚠️ Please enter Customer / Job Name.")
        elif not sales_order.strip():
            st.error("⚠️ Please enter Sales Order Number.")
        else:
            success = False
            
            action_suffix = f" (SO: {sales_order})"
            
            if pick_cat in ["Rolls", "Coils"]:
                with st.spinner("Updating Cloud Database..."):
                    success = update_stock(
                        item_id=pick_id,
                        new_footage=0,
                        user_name=picker_name,
                        action_type=f"Sold {pick_cat[:-1]} to {customer}{action_suffix}"
                    )
            else:
                # Use global df for actual update (safety)
                mask = (df['Category'] == pick_cat) & (df['Material'] == selected_mat)
                if mask.any():
                    current_stock = df.loc[mask, 'Footage'].values[0]
                    bulk_item_id = df.loc[mask, 'Item_ID'].values[0]
                    
                    if current_stock >= pick_qty:
                        new_total = current_stock - pick_qty
                        with st.spinner("Processing Bulk Removal..."):
                            success = update_stock(
                                item_id=bulk_item_id,
                                new_footage=new_total,
                                user_name=picker_name,
                                action_type=f"Removed {pick_qty} {pick_cat[:-1]}(s) for {customer}{action_suffix}"
                            )
                    else:
                        st.error(f"❌ Not enough stock! Current: {current_stock} | Requested: {pick_qty}")
                else:
                    st.error("Item not found in current data – try Sync Cloud Data.")

            if success:
                st.success(f"✅ Stock removed for {customer} ({sales_order})!")
                st.balloons()          # Classic balloons
                st.snow()              # Falling snow/confetti effect
                st.toast("Another one bites the dust! 🦆", icon="🎉")
                st.cache_data.clear()
                st.rerun()
with tab4:
    st.subheader("📦 Smart Inventory Receiver")
    
    # Category mapping (plural consistent)
    cat_mapping = {
        "Coils": "Coils", 
        "Rolls": "Rolls", 
        "Elbows": "Elbows", 
        "Fab Straps": "Fab Straps", 
        "Mineral Wool": "Mineral Wool",
        "Fiberglass Insulation": "Fiberglass Insulation",
        "Wing Seals": "Wing Seals",
        "Wire": "Wire",
        "Banding": "Banding",
        "Other": "Other"
    }
    
    raw_cat = st.radio("What are you receiving?", list(cat_mapping.keys()), horizontal=True)
    cat_choice = cat_mapping[raw_cat]

    with st.form("smart_receive_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        
        # ── Dynamic Material Builder with Hierarchy ─────────────────────────────
        material = ""
        qty_val = 1.0  # Default per-item quantity (e.g., footage, rolls, pieces)
        unit_label = "Items"  # Default
        is_serialized = cat_choice in ["Coils", "Rolls", "Wire"]  # Wire still optional serialized
        
        with col1:
            st.markdown("**Specs (Step 1)**")
        with col2:
            st.markdown("**Details (Step 2)**")
        
        if cat_choice == "Coils" or cat_choice == "Rolls":
            texture = st.radio("Texture", ["Stucco", "Smooth"], horizontal=True)
            metal = st.radio("Metal Type", ["Aluminum", "Stainless Steel"], horizontal=True)
            gauge = st.selectbox("Gauge", [".010", ".016", ".020", ".024", ".032", "Other"])
            if gauge == "Other":
                gauge = st.text_input("Custom Gauge (e.g. .040)")
            
            clean_gauge = gauge.replace('.', '')
            texture_code = "SMP" if texture == "Smooth" else "STP"
            metal_code = "AL" if metal == "Aluminum" else "SST"
            
            material = f"{texture} {metal} {cat_choice[:-1]} - {gauge} Gauge"
            qty_val = st.number_input("Footage per Item", min_value=0.1, value=3000.0 if cat_choice == "Coils" else 100.0)
            unit_label = "Footage"
            
            id_prefix = f"{cat_choice[:-1]}-{metal_code}-{clean_gauge}-{texture_code}-{int(qty_val)}"
        
        elif cat_choice == "Fiberglass Insulation":
            form_type = st.radio("Form", ["Rolls", "Batts", "Pipe Wrap", "Other"])
            thickness = st.selectbox("Thickness", ["0.25 in", "0.5 in", "1 in", "1.5 in", "2 in", "Other"])
            if thickness == "Other":
                thickness = st.text_input("Custom Thickness (e.g. 3 in)")
            
            sq_ft_per_roll = st.number_input("Sq Ft per Roll", min_value=1.0, value=150.0)
            material = f"Fiberglass {form_type} - {thickness} Thickness - {sq_ft_per_roll} sq ft/roll"
            qty_val = sq_ft_per_roll
            unit_label = "Sq Ft"
            is_serialized = form_type == "Rolls"
            
            id_prefix = f"FG-{thickness.replace(' ', '')}-{int(sq_ft_per_roll)}"
        
        elif cat_choice == "Elbows":
            angle = st.radio("Angle", ["45°", "90°", "Other"], horizontal=True)
            if angle == "Other":
                angle = st.text_input("Custom Angle (e.g. 22.5°)")
            size_num = st.number_input("Size Number", min_value=1, max_value=60, value=1)
            metal = st.radio("Metal Type", ["Aluminum", "Stainless Steel", "Galvanized", "Other"])
            
            material = f"{angle} Elbow - Size #{size_num} - {metal}"
            qty_val = 1.0
            unit_label = "Pieces"
            id_prefix = f"ELB-{angle.replace('°', '')}-S{size_num}"
        
        elif cat_choice == "Mineral Wool":
            pipe_size = st.selectbox("Pipe Size", ["1 in", "2 in", "3 in", "4 in", "Other"])
            if pipe_size == "Other":
                pipe_size = st.text_input("Custom Pipe Size")
            thickness = st.selectbox("Thickness", ["0.5 in", "1 in", "1.5 in", "2 in", "Other"])
            if thickness == "Other":
                thickness = st.text_input("Custom Thickness")
            
            material = f"Mineral Wool - Pipe Size: {pipe_size} - Thickness: {thickness}"
            qty_val = 1.0
            unit_label = "Sections"
            id_prefix = f"MW-PS{pipe_size.replace(' ', '')}-THK{thickness.replace(' ', '')}"
        
        elif cat_choice == "Wing Seals":
            seal_type = st.radio("Type", ["Open", "Closed"], horizontal=True)
            size = st.radio("Size", ["1/2 in", "3/4 in"], horizontal=True)
            gauge = st.selectbox("Gauge", [".028", ".032", "Other"])
            if gauge == "Other":
                gauge = st.text_input("Custom Gauge")
            grooves = st.radio("Grooves", ["With Grooves (Center)", "Without Grooves"])
            joint_pos = st.radio("Joint Position", ["Bottom", "Top", "N/A"])
            
            material = f"{seal_type} Wing Seal - {size} - {gauge} Gauge - {grooves} - Joint at {joint_pos}"
            box_qty = st.number_input("Pieces per Box", min_value=1, value=1000, step=100)
            qty_val = box_qty
            unit_label = "Pieces"
            id_prefix = f"WS-{seal_type[0]}-{size.replace('/','').replace(' ','')}-{gauge.replace('.', '')}"
        
        elif cat_choice == "Wire":
            gauge = st.selectbox("Gauge", ["14", "16", "18", "Other"])
            if gauge == "Other":
                gauge = st.text_input("Custom Gauge")
            rolls_count = st.number_input("Number of Rolls per Batch", min_value=1, value=1, step=1)
            footage_per_roll = st.number_input("Footage per Roll (optional)", min_value=0.0, value=0.0)  # If you track footage
            
            material = f"Wire - {gauge} Gauge - {rolls_count} Roll(s)"
            qty_val = rolls_count if footage_per_roll == 0 else footage_per_roll * rolls_count
            unit_label = "Rolls" if footage_per_roll == 0 else "Footage"
            is_serialized = st.checkbox("Assign unique ID to each roll?", value=False)  # Optional serialization
            
            id_prefix = f"WIRE-{gauge}"  # Simple prefix if serialized
        
        elif cat_choice == "Banding":
            osc_type = st.radio("Type", ["Oscillated", "Non-Oscillated"])
            size = st.radio("Size", ["3/4 in", "1/2 in"])
            gauge = st.selectbox("Gauge", [".015", ".020"])
            core = st.radio("Core", ["Metal Core", "Non-Metal Core"])
            
            material = f"{osc_type} Banding - {size} - {gauge} Gauge - {core}"
            qty_val = st.number_input("Footage per Item", min_value=0.1, value=100.0)
            unit_label = "Footage"
            is_serialized = True
            
            id_prefix = f"BAND-{osc_type[0]}-{size.replace('/','').replace(' ','')}-{gauge.replace('.', '')}"
        
        elif cat_choice == "Fab Straps":
            gauge = st.selectbox("Gauge", [".015", ".020"])
            size_num = st.number_input("Size Number", min_value=1, max_value=50, value=1)
            metal = st.radio("Metal Type", ["Aluminum", "Stainless Steel", "Other"])
            
            material = f"Fab Strap {gauge} - #{size_num} - {metal}"
            qty_val = 1.0
            unit_label = "Bundles"
            id_prefix = f"FS-{gauge.replace('.', '')}-S{size_num}"
        
        elif cat_choice == "Other":
            cat_choice = st.text_input("New Category Name", placeholder="e.g. Accessories")
            material = st.text_input("Material Description", placeholder="e.g. Custom Gaskets")
            qty_val = st.number_input("Qty/Footage per item", min_value=0.1, value=1.0)
            unit_label = st.text_input("Unit Label", value="Units")
            id_prefix = f"OTH-{cat_choice.upper()[:3]}" if cat_choice else "OTH-UNK"
        
        # ── Purchase Order Number ───────────────────────────────────────────────
        st.divider()
        purchase_order_num = st.text_input(
            "Purchase Order Number",
            placeholder="e.g. PO-2026-001",
            help="Supplier PO# for batch/quality tracking"
        )
        
        # ── Quantity & Location ─────────────────────────────────────────────────
        st.divider()
        item_count = st.number_input(f"How many {unit_label} are you receiving?", min_value=1, value=1, step=1)
        total_added = item_count * qty_val
        st.info(f"**Preview:** Adding {item_count} × '{material}' ({total_added} total {unit_label.lower()}) | PO: {purchase_order_num or 'N/A'}")
        
        loc_type = st.radio("Storage Type", ["Rack System", "Floor / Open Space"], horizontal=True)
        if loc_type == "Rack System":
            l1, l2, l3 = st.columns(3)
            bay = l1.number_input("Bay", min_value=1, value=1)
            sec = l2.selectbox("Section", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))
            lvl = l3.number_input("Level", min_value=1, value=1)
            gen_loc = f"{bay}{sec}{lvl}"
        else:
            gen_loc = st.text_input("Floor Zone Name", value="FLOOR").strip().upper()

        operator = st.text_input("Receiving Operator", value=st.session_state.get("username", ""))

        # ── ID Generation ───────────────────────────────────────────────────────
        if cat_choice == "Coils" and is_serialized:
            starting_num = st.number_input("Starting Identifier Number", min_value=1, value=1, step=1)
            id_preview = f"{id_prefix}-{starting_num:02d}"
            st.info(f"**ID Preview (first item):** {id_preview}")
        
        elif cat_choice == "Rolls" and is_serialized:
            pallet_num = st.number_input("Pallet Number", min_value=1, value=1, step=1)
            id_preview = f"{id_prefix}-{pallet_num:02d}"
            st.info(f"**Pallet ID Preview:** {id_preview} (Total Footage: {total_added})")
            is_serialized = False  # Pallet as bulk
        
        elif is_serialized:
            starting_id = st.text_input("Starting ID", value=f"{id_prefix}-1001")
            id_preview = starting_id
            st.info(f"**ID Preview (first item):** {id_preview}")
        
        else:
            st.info("Bulk item - no unique IDs needed (quantity will be added to existing or new row)")

        submitted = st.form_submit_button("📥 Add to Cloud Inventory", use_container_width=True)

    # ── Save Logic ──────────────────────────────────────────────────────────────
    if submitted:
        if not operator or not material:
            st.error("Operator and material details required.")
        else:
            with st.spinner("Syncing with Cloud..."):
                try:
                    if is_serialized:
                        new_rows = []
                        for i in range(item_count):
                            if cat_choice == "Coils":
                                unique_id = f"{id_prefix}-{ (starting_num + i):02d }"
                            else:
                                parts = starting_id.split('-')
                                base = '-'.join(parts[:-1])
                                num = int(parts[-1]) + i
                                unique_id = f"{base}-{num:04d}"
                            
                            new_rows.append({
                                "Item_ID": unique_id,
                                "Material": material,
                                "Footage": qty_val,
                                "Location": gen_loc,
                                "Status": "Active",
                                "Category": cat_choice,
                                "Purchase_Order_Num": purchase_order_num.strip() or None
                            })
                        
                        supabase.table("inventory").insert(new_rows).execute()
                    
                    else:
                        mask = (df['Category'] == cat_choice) & (df['Material'] == material)
                        if mask.any():
                            current_qty = df.loc[mask, 'Footage'].values[0]
                            new_qty = current_qty + total_added
                            bulk_id = df.loc[mask, 'Item_ID'].values[0]
                            update_stock(bulk_id, new_qty, operator, f"Received {total_added} {unit_label.lower()} (PO: {purchase_order_num or 'N/A'})")
                        else:
                            unique_id = id_preview if 'id_preview' in locals() else f"{cat_choice.upper()}-BULK-{datetime.now().strftime('%Y%m%d')}"
                            new_data = {
                                "Item_ID": unique_id,
                                "Material": material,
                                "Footage": total_added,
                                "Location": gen_loc,
                                "Status": "Active",
                                "Category": cat_choice,
                                "Purchase_Order_Num": purchase_order_num.strip() or None
                            }
                            supabase.table("inventory").insert(new_data).execute()
                    
                    # Audit log
                    log_id = unique_id if 'unique_id' in locals() else bulk_id
                    log_entry = {
                        "Item_ID": log_id,
                        "Action": "Received",
                        "User": operator,
                        "Timestamp": datetime.now().isoformat(),
                        "Details": f"PO: {purchase_order_num or 'N/A'} | {item_count} × {material} ({total_added} {unit_label.lower()})"
                    }
                    supabase.table("audit_logs").insert(log_entry).execute()
                    
                    st.cache_data.clear()
                    st.success(f"Added {item_count} × '{material}' ({total_added} {unit_label.lower()}) to {gen_loc}! PO: {purchase_order_num or 'N/A'}")
                    st.rerun()
                
                except Exception as e:
                    st.error(f"Failed to add inventory: {e}")

    # ── Receipt Report Section (PDF) ────────────────────────────────────────────
    st.divider()
    st.subheader("📄 Export Receipt Report (PDF)")
    st.caption("Generate and email a PDF report for items received under a specific Purchase Order Number.")

    with st.form("export_report_form"):
        report_po_num = st.text_input(
            "Purchase Order Number",
            placeholder="e.g. PO-2026-001",
            key="report_po"
        )
        
        export_mode = st.radio(
            "Action",
            ["Download Only", "Download & Email to Admin"],
            horizontal=True
        )
        
        submitted_report = st.form_submit_button("Generate PDF Report", use_container_width=True, type="primary")

    if submitted_report and report_po_num.strip():
        with st.spinner(f"Fetching items for PO: {report_po_num}..."):
            response = supabase.table("inventory").select("*").eq("Purchase_Order_Num", report_po_num.strip()).execute()
            report_df = pd.DataFrame(response.data)
            
            if report_df.empty:
                st.warning(f"No items found for PO: {report_po_num}")
            else:
                pdf_buffer = generate_receipt_pdf(
                    po_num=report_po_num,
                    df=report_df,
                    operator=st.session_state.get('username', 'Operator')
                )
                
                file_name = f"Receipt_{report_po_num.replace(' ', '_')}.pdf"
                
                st.download_button(
                    label="📥 Download PDF Report",
                    data=pdf_buffer.getvalue(),
                    file_name=file_name,
                    mime="application/pdf",
                    key=f"dl_{report_po_num}"
                )
                
                if export_mode == "Download & Email to Admin":
                    if send_email_to_admin("tmilazi@gmail.com", report_po_num, pdf_buffer.getvalue(), file_name=file_name):
                        st.success(f"PDF report for PO {report_po_num} emailed to admin!")
                    else:
                        st.warning("PDF generated, but email failed. Use the download button above.")            
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
