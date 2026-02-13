import streamlit as st
import pandas as pd
from datetime import datetime
from fpdf import FPDF
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
import io
from supabase import create_client, Client
from collections import defaultdict
import time

# --- PAGE CONFIG (MUST BE FIRST) ---
st.set_page_config(
    page_title="MJP Pulse Inventory",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- PWA & PROFESSIONAL STYLING ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;800&display=swap');
        
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

# --- LOW STOCK ALERT STYLING ---
st.markdown("""
<style>
.low-stock-banner {
    background-color: #FFB74D;
    padding: 15px;
    border-radius: 8px;
    border-left: 6px solid #FF8F00;
    margin-bottom: 20px;
}
.low-stock-text {
    color: #000000;
    font-weight: bold;
    font-size: 18px;
}
.low-stock-item {
    color: #000000;
    font-weight: bold;
}
.low-stock-row {
    background-color: #FFF9C4 !important;
    font-weight: bold;
    color: #000000 !important;
}
</style>
""", unsafe_allow_html=True)

# --- Supabase CONNECTION ---
@st.cache_resource
def init_connection():
    try:
        if "SUPABASE_URL" not in st.secrets or "SUPABASE_KEY" not in st.secrets:
            return None
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
        return create_client(url, key)
    except Exception as e:
        st.error(f"Supabase connection failed: {e}")
        return None

supabase = init_connection()

# --- CATEGORY NORMALIZATION ---
def normalize_category(cat):
    """Normalize category names to handle singular/plural variations"""
    if pd.isna(cat) or not isinstance(cat, str):
        return "Other"
    
    cat_lower = str(cat).strip().lower()
    
    # Map all variations to standard plural form
    mapping = {
        'coil': 'Coils',
        'coils': 'Coils',
        'roll': 'Rolls',
        'rolls': 'Rolls',
        'elbow': 'Elbows',
        'elbows': 'Elbows',
        'fab strap': 'Fab Straps',
        'fab straps': 'Fab Straps',
        'fabstrap': 'Fab Straps',
        'fabstraps': 'Fab Straps',
        'strap': 'Fab Straps',
        'straps': 'Fab Straps',
        'mineral wool': 'Mineral Wool',
        'mineralwool': 'Mineral Wool',
        'fiberglass insulation': 'Fiberglass Insulation',
        'fiberglass': 'Fiberglass Insulation',
        'wing seal': 'Wing Seals',
        'wing seals': 'Wing Seals',
        'wingseals': 'Wing Seals',
        'wire': 'Wire',
        'banding': 'Banding',
        'other': 'Other',
    }
    
    # Check for exact match first
    if cat_lower in mapping:
        return mapping[cat_lower]
    
    # Check for partial match
    for key, value in mapping.items():
        if key in cat_lower:
            return value
    
    # Return original with title case if no match
    return cat.strip().title()

# --- DATA LOADER (Supabase only) ---
@st.cache_data(ttl=5)
def load_all_tables():
    if supabase is None:
        st.error("Supabase not connected")
        # Return empty DataFrames WITH proper structure
        empty_inv = pd.DataFrame(columns=['Item_ID', 'Material', 'Footage', 'Location', 'Status', 'Category', 'Purchase_Order_Num'])
        empty_audit = pd.DataFrame(columns=['Item_ID', 'Action', 'User', 'Timestamp', 'Details'])
        return empty_inv, empty_audit
    
    try:
        inv_res = supabase.table("inventory").select("*").execute()
        audit_res = supabase.table("audit_log").select("*").execute()
        
        # Create DataFrames with proper structure even if empty
        if inv_res.data:
            df_inv = pd.DataFrame(inv_res.data)
        else:
            df_inv = pd.DataFrame(columns=['Item_ID', 'Material', 'Footage', 'Location', 'Status', 'Category', 'Purchase_Order_Num'])
        
        if audit_res.data:
            df_audit = pd.DataFrame(audit_res.data)
        else:
            df_audit = pd.DataFrame(columns=['Item_ID', 'Action', 'User', 'Timestamp', 'Details'])
        
        return df_inv, df_audit
        
    except Exception as e:
        st.error(f"Error loading from Supabase: {e}")
        # Return properly structured empty DataFrames
        empty_inv = pd.DataFrame(columns=['Item_ID', 'Material', 'Footage', 'Location', 'Status', 'Category', 'Purchase_Order_Num'])
        empty_audit = pd.DataFrame(columns=['Item_ID', 'Action', 'User', 'Timestamp', 'Details'])
        return empty_inv, empty_audit
        
# Initialize df - reload if not present or if force refresh flag is set
if 'df' not in st.session_state or 'df_audit' not in st.session_state or st.session_state.get('force_refresh', False):
    st.session_state.df, st.session_state.df_audit = load_all_tables()
    st.session_state.force_refresh = False

df = st.session_state.df
df_audit = st.session_state.df_audit

# Normalize categories in the dataframe
if df is not None and not df.empty and 'Category' in df.columns:
    df['Category'] = df['Category'].apply(normalize_category)
    st.session_state.df = df
    
# Paste update_stock here
def update_stock(item_id, new_footage, user_name, action_type):
    try:
        # Update the inventory
        supabase.table("inventory").update({"Footage": new_footage}).eq("Item_ID", item_id).execute()
        
        # Log the action
        log_entry = {
            "Item_ID": item_id,
            "Action": action_type,
            "User": user_name,
            "Timestamp": datetime.now().isoformat(),
            "Details": f"Updated Item {item_id} to {new_footage:.2f} ft via {action_type}"
        }
        supabase.table("audit_log").insert(log_entry).execute()
        
        # Clear ALL caches and session state to force fresh data
        st.cache_data.clear()
        
        # Force refresh session state data
        if 'df' in st.session_state:
            del st.session_state['df']
        if 'df_audit' in st.session_state:
            del st.session_state['df_audit']
        
        return True
    except Exception as e:
        st.error(f"Failed to update database: {e}")
        return False

# Then continue with login, sidebar, etc.

# --- LOW STOCK THRESHOLDS (define FIRST - before the function) ---
LOW_STOCK_THRESHOLDS = {
    ".016 Smooth Aluminum": 6000.0,
    ".020 Stucco Aluminum": 6000.0,
    ".020 Smooth Aluminum": 3500.0,
    ".016 Stucco Aluminum": 2500.0,
    ".010 Stainless Steel Polythene": 2500.0,
    # Add more as needed (e.g. for rolls, insulation, etc.)
}

# --- LOW STOCK CHECK & EMAIL (now safe) ---
def check_and_alert_low_stock():
    if df is None or df.empty:
        st.warning("Low stock check skipped: No inventory data loaded.")
        return
    
    low_materials = []
    for material, threshold in LOW_STOCK_THRESHOLDS.items():
        total = df[df['Material'] == material]['Footage'].sum()
        if total < threshold:
            low_materials.append(f"{material}: {total:.1f} ft (below {threshold})")

    if low_materials:
        subject = "URGENT: Low Stock Alert - MJP Pulse"
        body = "The following materials are low:\n\n" + "\n".join(low_materials) + "\n\nCheck dashboard immediately."
        
        try:
            msg = MIMEMultipart()
            msg['From'] = st.secrets["SMTP_EMAIL"]
            msg['To'] = st.secrets["ADMIN_EMAIL"]
            msg['Subject'] = subject
            msg.attach(MIMEText(body, 'plain'))

            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(st.secrets["SMTP_EMAIL"], st.secrets["SMTP_PASSWORD"])
            server.send_message(msg)
            server.quit()
            st.toast("Low stock alert email sent!", icon="⚠️")
        except Exception as e:
            st.error(f"Low stock email failed: {e}")
            
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
            
            # Check low stock after login (df now exists)
           # check_and_alert_low_stock()
            
            st.rerun()
        else:
            st.error("Invalid username or password")
    st.stop()

# --- SIDEBAR BRANDING ---
with st.sidebar:
    try:
        st.image("logo.png", use_container_width=True)
    except:
        st.markdown("<h1 style='text-align: center;'>⚡ MJP</h1>", unsafe_allow_html=True)
    try:
        supabase.table("inventory").select("count", count="exact").limit(1).execute()
        st.success("🛰️ Database: Online")
    except Exception:
        st.error("🛰️ Database: Offline")
    
    st.divider()
    
    st.markdown(f"""
        <div style="background-color: white; padding: 15px; border-radius: 10px; border: 1px solid #e2e8f0; margin-bottom: 20px;">
            <p style="margin:0; color: #64748B; font-size: 12px; font-weight: bold; text-transform: uppercase;">Current Operator</p>
            <p style="margin:0; color: #1E3A8A; font-size: 18px; font-weight: bold;">{st.session_state.get('username', 'Admin User')}</p>
        </div>
    """, unsafe_allow_html=True)

    # Manual low stock check
    if st.button("⚠️ Check Low Stock Now"):
        check_and_alert_low_stock()

# --- OFFLINE NOTIFICATION SYSTEM ---
st.markdown("""
    <script>
        const updateOnlineStatus = () => {
            const condition = navigator.onLine ? "online" : "offline";
            if (condition === "offline") {
                const div = document.createElement("div");
                div.id = "offline-warning";
                div.style = "position: fixed; top: 0; left: 0; width: 100%; background: #ef4444; color: white; text-align: center; padding: 10px; z-index: 9999; font-family: sans-serif; font-weight: bold;";
                div.innerHTML = "⚠️ Wi-Fi Connection Lost. Please check your signal to save changes.";
                document.body.appendChild(div);
            } else {
                const warning = document.getElementById("offline-warning");
                if (warning) warning.remove();
            }
        };

        window.addEventListener('online', updateOnlineStatus);
        window.addEventListener('offline', updateOnlineStatus);
    </script>
""", unsafe_allow_html=True)

# --- GLOBAL SYNC BUTTON ---
if st.button("🔄 Sync Cloud Data", use_container_width=True):
    # Clear everything
    st.cache_data.clear()
    if 'df' in st.session_state:
        del st.session_state['df']
    if 'df_audit' in st.session_state:
        del st.session_state['df_audit']
    st.session_state.force_refresh = True
    st.toast("Pulling fresh data from Supabase...", icon="🛰️")
    st.rerun()

# --- MAIN PAGE HEADER ---
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

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER
from io import BytesIO
from datetime import datetime
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def process_production_line(line, extra_allowance, material_type, order_number, client_name, operator_name, feedback, deduction_details):
    """
    Process a single production line (coil or roll).
    
    Args:
        line: Dictionary with production line details
        extra_allowance: Extra inches per piece
        material_type: "Coil" or "Roll"
        order_number: Internal order number
        client_name: Client name
        operator_name: Operator name
        feedback: List to append feedback messages
        deduction_details: List to append deduction records
    
    Returns:
        tuple: (success: bool, total_footage: float)
    """
    if line["pieces"] <= 0:
        return True, 0.0  # Skip empty lines
    
    if not line["items"]:
        feedback.append(f"✗ {material_type} line for {line['display_size']} has no source selected")
        return False, 0.0
    
    # Calculate required footage
    if line["use_custom"]:
        # Custom inches mode
        inches_per_piece = line["custom_inches"]
        size_label = f"Custom {inches_per_piece}in"
    else:
        # Standard size mode
        inches_per_piece = SIZE_DISPLAY.get(line["display_size"], 12.0)
        size_label = line["display_size"]
    
    # Calculate production footage (pieces × inches per piece + extra allowance per piece)
    total_inches = (inches_per_piece + extra_allowance) * line["pieces"]
    production_footage = total_inches / 12.0  # This is JUST production, no waste
    
    # Waste is separate
    waste_footage = line["waste"]
    
    # Total needed for deduction = production + waste
    total_footage_needed = production_footage + waste_footage
    
    # Get source items - refresh from database to get current values
    source_items = []
    for item_str in line["items"]:
        item_id = item_str.split(" - ")[0]
        
        # Fetch current footage from database
        try:
            response = supabase.table("inventory").select("*").eq("Item_ID", item_id).execute()
            if response.data:
                item_data = response.data[0]
                source_items.append({
                    'id': item_id,
                    'footage': float(item_data['Footage']),
                    'material': item_data['Material']
                })
        except Exception as e:
            feedback.append(f"✗ Error fetching {item_id}: {e}")
            return False, 0.0
    
    if not source_items:
        feedback.append(f"✗ No valid sources found for {material_type} {size_label}")
        return False, 0.0
    
    # Calculate available footage
    available_footage = sum(item['footage'] for item in source_items)
    
    if available_footage < total_footage_needed:
        feedback.append(f"✗ Insufficient stock for {material_type} {size_label}: need {total_footage_needed:.2f} ft, have {available_footage:.2f} ft")
        return False, 0.0
    
    # Deduct from sources
    remaining_needed = total_footage_needed
    
    for item in source_items:
        if remaining_needed <= 0:
            break
        
        deduct_amount = min(item['footage'], remaining_needed)
        new_footage = item['footage'] - deduct_amount
        
        # Calculate how much of this deduction is production vs waste
        # (proportionally allocate if using multiple sources)
        if total_footage_needed > 0:
            proportion = deduct_amount / total_footage_needed
            item_production = production_footage * proportion
            item_waste = waste_footage * proportion
        else:
            item_production = 0
            item_waste = 0
        
        # Update database
        try:
            action_details = f"Production: {line['pieces']} pcs of {size_label} ({item_production:.2f} ft production + {item_waste:.2f} ft waste = {deduct_amount:.2f} ft total) for {client_name} (Order: {order_number})"
            
            success_update = update_stock(
                item_id=item['id'],
                new_footage=new_footage,
                user_name=operator_name,
                action_type=action_details
            )
            
            if not success_update:
                feedback.append(f"✗ Failed to update {item['id']}")
                return False, 0.0
            
            # Record for PDF - SEPARATE production and waste
            deduction_details.append({
                'source_id': item['id'],
                'material': item['material'],
                'size': size_label,
                'pieces': line['pieces'],
                'inches_per_piece': inches_per_piece,
                'production_footage': item_production,  # Production ONLY (no waste)
                'waste': item_waste,                    # Waste ONLY
                'total_deducted': deduct_amount,        # Total deducted from this source
                'material_type': material_type,
                # Keep footage_used for backward compatibility
                'footage_used': deduct_amount
            })
            
            remaining_needed -= deduct_amount
            
        except Exception as e:
            feedback.append(f"✗ Error updating {item['id']}: {e}")
            return False, 0.0
    
    feedback.append(f"✓ {material_type} {size_label}: {line['pieces']} pieces produced ({production_footage:.2f} ft production + {waste_footage:.2f} ft waste = {total_footage_needed:.2f} ft total)")
    return True, total_footage_needed
    

def generate_production_pdf(order_number, client_name, operator_name, deduction_details, box_usage, coil_extra=0.5, roll_extra=0.5):
    """
    Generate a professional production order PDF with navy blue theme.
    
    Args:
        order_number: Internal order number
        client_name: Client name
        operator_name: Operator name
        deduction_details: List of deduction records
        box_usage: Dictionary of box types and quantities
        coil_extra: Extra inch allowance for coils
        roll_extra: Extra inch allowance for rolls
    
    Returns:
        BytesIO: PDF file buffer
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, 
                           rightMargin=0.5*inch, leftMargin=0.5*inch,
                           topMargin=0.75*inch, bottomMargin=0.5*inch)
    
    elements = []
    styles = getSampleStyleSheet()
    
    # Navy blue theme colors
    navy_blue = colors.HexColor('#1e3a8a')
    light_navy = colors.HexColor('#dbeafe')
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=22,
        textColor=navy_blue,
        spaceAfter=8,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=20,
        alignment=TA_CENTER
    )
    
    # Title
    elements.append(Paragraph("MJP PRODUCTION ORDER LOG", title_style))
    elements.append(Paragraph("Manufacturing & Stock Deduction Documentation", subtitle_style))
    
    # Order metadata with fillable production order number
    current_time = datetime.now().strftime('%B %d, %Y at %I:%M %p')
    
    metadata = [
        ['Internal Order #:', order_number],
        ['Production Order #:', '____________________________'],  # Fillable space
        ['Client:', client_name],
        ['Operator:', operator_name],
        ['Completed:', current_time]
    ]
    
    meta_table = Table(metadata, colWidths=[1.8*inch, 4.7*inch])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), light_navy),
        ('TEXTCOLOR', (0, 0), (0, -1), navy_blue),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    
    elements.append(meta_table)
    elements.append(Spacer(1, 0.2*inch))
    
    # Production details table (compact for up to 10+ sizes)
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=11,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=8,
        spaceBefore=8
    )
    
    elements.append(Paragraph("Production Details", heading_style))
    
    # Table data - UPDATED COLUMNS: Production and Waste separate
    table_data = [['Type', 'Source ID', 'Size', 'Pcs', 'Production', 'Waste', 'Extra"']]
    
    for detail in deduction_details:
        extra_allowance = coil_extra if detail['material_type'] == 'Coil' else roll_extra
        
        # Use new field names, with fallback for backward compatibility
        production_ft = detail.get('production_footage', detail.get('footage_used', 0) - detail.get('waste', 0))
        waste_ft = detail.get('waste', 0)
        
        table_data.append([
            detail['material_type'][:4],  # Coil/Roll
            str(detail['source_id'])[:15],  # Truncate if needed
            detail['size'],
            str(detail['pieces']),
            f"{production_ft:.1f}",   # Production footage ONLY
            f"{waste_ft:.1f}",        # Waste ONLY
            f"{extra_allowance}"
        ])
    
    col_widths = [0.5*inch, 1.3*inch, 0.6*inch, 0.5*inch, 0.8*inch, 0.6*inch, 0.6*inch]
    prod_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    prod_table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), navy_blue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
        ('TOPPADDING', (0, 0), (-1, 0), 6),
        
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 1), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ('LEFTPADDING', (0, 0), (-1, -1), 5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 5),
        ('TOPPADDING', (0, 1), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 4),
    ]))
    
    elements.append(prod_table)
    elements.append(Spacer(1, 0.15*inch))
    
    # TOTALS SECTION - Group by material with CLEAR separation
    elements.append(Paragraph("TOTALS BY MATERIAL", heading_style))
    
    # Calculate totals by material - SEPARATE production and waste
    material_totals = {}
    for detail in deduction_details:
        material_key = detail['material']
        if material_key not in material_totals:
            material_totals[material_key] = {
                'production': 0,
                'waste': 0,
                'pieces': 0,
                'type': detail['material_type']
            }
        
        # Use new field names with fallback
        production_ft = detail.get('production_footage', detail.get('footage_used', 0) - detail.get('waste', 0))
        waste_ft = detail.get('waste', 0)
        
        material_totals[material_key]['production'] += production_ft
        material_totals[material_key]['waste'] += waste_ft
        material_totals[material_key]['pieces'] += detail['pieces']
    
    # Create totals table - UPDATED COLUMNS
    totals_data = [['Material', 'Type', 'Pieces', 'Production (ft)', 'Waste (ft)', 'Total (ft)']]
    
    grand_production = 0
    grand_waste = 0
    grand_pieces = 0
    
    for material, totals in material_totals.items():
        material_total = totals['production'] + totals['waste']
        totals_data.append([
            material[:30],  # Truncate long names
            totals['type'],
            str(totals['pieces']),
            f"{totals['production']:.2f}",
            f"{totals['waste']:.2f}",
            f"{material_total:.2f}"
        ])
        grand_production += totals['production']
        grand_waste += totals['waste']
        grand_pieces += totals['pieces']
    
    grand_total = grand_production + grand_waste
    
    # Grand total row
    totals_data.append([
        'GRAND TOTAL',
        '',
        str(grand_pieces),
        f"{grand_production:.2f}",
        f"{grand_waste:.2f}",
        f"{grand_total:.2f}"
    ])
    
    totals_table = Table(totals_data, colWidths=[1.8*inch, 0.6*inch, 0.7*inch, 1.1*inch, 0.9*inch, 0.9*inch])
    totals_table.setStyle(TableStyle([
        # Header
        ('BACKGROUND', (0, 0), (-1, 0), navy_blue),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        
        # Data rows
        ('FONTNAME', (0, 1), (-1, -2), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -2), 9),
        ('ALIGN', (0, 1), (0, -2), 'LEFT'),
        ('ALIGN', (1, 1), (-1, -2), 'CENTER'),
        
        # Grand total row (last row)
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fef3c7')),
        ('TEXTCOLOR', (0, -1), (-1, -1), colors.HexColor('#92400e')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 10),
        ('ALIGN', (0, -1), (-1, -1), 'CENTER'),
        
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, light_navy]),
        ('PADDING', (0, 0), (-1, -1), 6),
    ]))
    
    elements.append(totals_table)
    elements.append(Spacer(1, 0.15*inch))
    
    # Summary box - CLEAR breakdown
    summary_style = ParagraphStyle(
        'SummaryStyle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=navy_blue,
        alignment=TA_CENTER,
        spaceAfter=10,
        fontName='Helvetica-Bold'
    )
    
    elements.append(Paragraph(
        f"SUMMARY: {grand_production:.2f} ft Production + {grand_waste:.2f} ft Waste = {grand_total:.2f} ft Total Deducted",
        summary_style
    ))
    
    # Extra allowance note
    allowance_note = ParagraphStyle(
        'AllowanceNote',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#64748b'),
        alignment=TA_CENTER,
        spaceAfter=10
    )
    
    elements.append(Paragraph(
        f"<b>Note:</b> Extra allowance included in production - Coils: {coil_extra}\" per piece | Rolls: {roll_extra}\" per piece",
        allowance_note
    ))
    
    # Box usage section (if any)
    if any(box_usage.values()):
        elements.append(Spacer(1, 0.1*inch))
        elements.append(Paragraph("Box Usage", heading_style))
        
        box_data = [['Box Type', 'Quantity Used']]
        for box_type, qty in box_usage.items():
            if qty > 0:
                box_data.append([box_type, str(qty)])
        
        box_table = Table(box_data, colWidths=[3.5*inch, 1.5*inch])
        box_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), navy_blue),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 9),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, light_navy]),
            ('PADDING', (0, 0), (-1, -1), 6),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
        ]))
        
        elements.append(box_table)
    
    elements.append(Spacer(1, 0.2*inch))
    
    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=7,
        textColor=colors.HexColor('#94a3b8'),
        alignment=TA_CENTER
    )
    
    elements.append(Paragraph(
        "This production log was automatically generated by the MJP Pulse Warehouse Management System.<br/>"
        "For questions or updates, please contact the production manager.",
        footer_style
    ))
    
    doc.build(elements)
    buffer.seek(0)
    
    return buffer
def send_production_pdf(pdf_buffer, order_number, client_name):
    """
    Send production PDF via email to admin.
    
    Args:
        pdf_buffer (BytesIO): PDF file buffer
        order_number: Order number
        client_name: Client name
    
    Returns:
        bool: True if email sent successfully
    """
    try:
        # Get email config from secrets
        smtp_server = st.secrets["email"]["smtp_server"]
        smtp_port = st.secrets["email"]["smtp_port"]
        sender_email = st.secrets["email"]["sender_email"]
        sender_password = st.secrets["email"]["sender_password"]
        admin_email = st.secrets["email"]["admin_email"]
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = admin_email
        msg['Subject'] = f"📋 Production Order Complete - {order_number}"
        
        # Email body
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #1e3a8a;">Production Order Completed</h2>
            <p>A new production order has been completed and is ready for review.</p>
            
            <table style="border-collapse: collapse; margin: 20px 0;">
                <tr>
                    <td style="padding: 8px; background: #dbeafe; font-weight: bold;">Order Number:</td>
                    <td style="padding: 8px;">{order_number}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background: #dbeafe; font-weight: bold;">Client:</td>
                    <td style="padding: 8px;">{client_name}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background: #dbeafe; font-weight: bold;">Completed:</td>
                    <td style="padding: 8px;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td>
                </tr>
            </table>
            
            <p>Please find the detailed production report attached as a PDF.</p>
            
            <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">
            <p style="color: #64748b; font-size: 12px;">
                This is an automated email from the MJP Pulse Warehouse Management System.
            </p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Attach PDF
        pdf_buffer.seek(0)
        attachment = MIMEBase('application', 'pdf')
        attachment.set_payload(pdf_buffer.read())
        encoders.encode_base64(attachment)
        attachment.add_header('Content-Disposition', f'attachment; filename=Production_Order_{order_number}.pdf')
        msg.attach(attachment)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        return True
    
    except Exception as e:
        print(f"Email error: {e}")
        return False
        
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

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from io import BytesIO
from datetime import datetime

def generate_receipt_pdf(po_num, df, operator):
    """
    Generate a professional PDF receipt report for received inventory items.
    
    Args:
        po_num (str): Purchase Order Number
        df (DataFrame): DataFrame containing inventory items
        operator (str): Name of receiving operator
    
    Returns:
        BytesIO: PDF file buffer
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, 
                           rightMargin=0.75*inch, leftMargin=0.75*inch,
                           topMargin=1*inch, bottomMargin=0.75*inch)
    
    # Container for PDF elements
    elements = []
    
    # Styles
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=24,
        textColor=colors.HexColor('#15803d'),
        spaceAfter=12,
        alignment=TA_CENTER,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'CustomSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#64748b'),
        spaceAfter=30,
        alignment=TA_CENTER
    )
    
    heading_style = ParagraphStyle(
        'CustomHeading',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#1e293b'),
        spaceAfter=12,
        spaceBefore=12
    )
    
    # Title
    elements.append(Paragraph("📦 RECEIVING REPORT", title_style))
    elements.append(Paragraph("Purchase Order Receipt Documentation", subtitle_style))
    
    # Metadata section
    current_time = datetime.now().strftime('%B %d, %Y at %I:%M %p')
    
    metadata = [
        ['Purchase Order:', po_num],
        ['Generated:', current_time],
        ['Operator:', operator],
        ['Total Items:', str(len(df))]
    ]
    
    meta_table = Table(metadata, colWidths=[2*inch, 4*inch])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0fdf4')),
        ('TEXTCOLOR', (0, 0), (0, -1), colors.HexColor('#15803d')),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    
    elements.append(meta_table)
    elements.append(Spacer(1, 0.3*inch))
    
    # Items Table Header
    elements.append(Paragraph("Received Items", heading_style))
    
    # Group items by Material and Location to consolidate rows
    grouped_data = df.groupby(['Category', 'Material', 'Location']).agg({
        'Footage': 'sum',  # Sum quantities
        'Item_ID': 'count'  # Count how many items
    }).reset_index()
    
    grouped_data.columns = ['Category', 'Material', 'Location', 'Total_Qty', 'Item_Count']
    
    # Prepare table data with simplified columns
    table_data = [['Category', 'Specifications', 'Quantity', 'Location']]
    
    for _, row in grouped_data.iterrows():
        category = str(row['Category'])
        material = str(row['Material'])
        
        # Extract key specs from material description
        # e.g., "Smooth Aluminum Coil - .016 Gauge" -> ".016 Aluminum Smooth"
        specs = material
        if category in ['Coils', 'Rolls']:
            # Try to extract gauge and key descriptors
            parts = material.split(' - ')
            if len(parts) > 1:
                gauge_part = parts[-1].replace(' Gauge', '')  # ".016"
                desc_parts = parts[0].split()  # ["Smooth", "Aluminum", "Coil"]
                if len(desc_parts) >= 2:
                    specs = f"{gauge_part} {desc_parts[1]} {desc_parts[0]}"  # ".016 Aluminum Smooth"
        
        # Format quantity with item count
        qty_display = f"{int(row['Item_Count'])} items ({row['Total_Qty']} total)"
        if category in ['Coils', 'Rolls']:
            qty_display = f"{int(row['Item_Count'])} {category}"
        
        table_data.append([
            category,
            specs,
            qty_display,
            str(row['Location'])
        ])
    
    # Create table with adjusted column widths
    col_widths = [1.2*inch, 3*inch, 1.5*inch, 1*inch]
    items_table = Table(table_data, colWidths=col_widths, repeatRows=1)
    
    # Table styling
    items_table.setStyle(TableStyle([
        # Header row
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#16a34a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, 0), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        
        # Data rows
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 1), (0, -1), 'LEFT'),
        ('ALIGN', (1, 1), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 1), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e5e7eb')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f9fafb')]),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 6),
    ]))
    
    elements.append(items_table)
    elements.append(Spacer(1, 0.5*inch))
    
    # Footer
    footer_style = ParagraphStyle(
        'Footer',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#94a3b8'),
        alignment=TA_CENTER
    )
    
    elements.append(Paragraph(
        "This report was automatically generated by the Warehouse Management System.<br/>"
        "For questions or updates, please contact the warehouse administrator.",
        footer_style
    ))
    
    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    
    return buffer

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

def send_receipt_email(admin_email, po_num, pdf_buffer, operator):
    """
    Send receipt PDF via email to admin.
    
    Args:
        admin_email (str): Admin email address
        po_num (str): Purchase Order Number
        pdf_buffer (BytesIO): PDF file buffer
        operator (str): Name of receiving operator
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # Get email config from Streamlit secrets
        smtp_server = st.secrets["email"]["smtp_server"]
        smtp_port = st.secrets["email"]["smtp_port"]
        sender_email = st.secrets["email"]["sender_email"]
        sender_password = st.secrets["email"]["sender_password"]
        
        # Create message
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = admin_email
        msg['Subject'] = f"📦 Receipt Report - PO: {po_num}"
        
        # Email body
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <h2 style="color: #16a34a;">Receiving Report</h2>
            <p>A new receipt report has been generated for your review.</p>
            
            <table style="border-collapse: collapse; margin: 20px 0;">
                <tr>
                    <td style="padding: 8px; background: #f0fdf4; font-weight: bold;">Purchase Order:</td>
                    <td style="padding: 8px;">{po_num}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background: #f0fdf4; font-weight: bold;">Received By:</td>
                    <td style="padding: 8px;">{operator}</td>
                </tr>
                <tr>
                    <td style="padding: 8px; background: #f0fdf4; font-weight: bold;">Generated:</td>
                    <td style="padding: 8px;">{datetime.now().strftime('%B %d, %Y at %I:%M %p')}</td>
                </tr>
            </table>
            
            <p>Please find the detailed receipt report attached as a PDF.</p>
            
            <hr style="border: 1px solid #e5e7eb; margin: 20px 0;">
            <p style="color: #64748b; font-size: 12px;">
                This is an automated email from the Warehouse Management System.
            </p>
        </body>
        </html>
        """
        
        msg.attach(MIMEText(body, 'html'))
        
        # Attach PDF
        pdf_buffer.seek(0)
        attachment = MIMEBase('application', 'pdf')
        attachment.set_payload(pdf_buffer.read())
        encoders.encode_base64(attachment)
        attachment.add_header('Content-Disposition', f'attachment; filename=Receipt_{po_num}.pdf')
        msg.attach(attachment)
        
        # Send email
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender_email, sender_password)
            server.send_message(msg)
        
        return True
    
    except Exception as e:
        print(f"Email error: {e}")
        return False


# Alternative: Using SendGrid (if you prefer API-based email)
def send_receipt_email_sendgrid(admin_email, po_num, pdf_buffer, operator):
    """
    Send receipt PDF via SendGrid API.
    Requires: pip install sendgrid
    """
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType, Disposition
        import base64
        
        # Your SendGrid API key
        SENDGRID_API_KEY = "your-sendgrid-api-key"
        
        # Encode PDF
        pdf_buffer.seek(0)
        encoded_pdf = base64.b64encode(pdf_buffer.read()).decode()
        
        # Create attachment
        attachment = Attachment(
            FileContent(encoded_pdf),
            FileName(f'Receipt_{po_num}.pdf'),
            FileType('application/pdf'),
            Disposition('attachment')
        )
        
        # Create email
        message = Mail(
            from_email='your-verified-sender@example.com',
            to_emails=admin_email,
            subject=f'📦 Receipt Report - PO: {po_num}',
            html_content=f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color: #16a34a;">Receiving Report</h2>
                <p>A new receipt report has been generated.</p>
                <p><strong>PO:</strong> {po_num}<br>
                <strong>Operator:</strong> {operator}<br>
                <strong>Date:</strong> {datetime.now().strftime('%B %d, %Y')}</p>
                <p>Please find the detailed report attached.</p>
            </body>
            </html>
            """
        )
        message.attachment = attachment
        
        # Send
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        
        return response.status_code == 202
    
    except Exception as e:
        print(f"SendGrid error: {e}")
        return False

# --- END OF PRE-TABS LAYOUT ---

tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["Dashboard", "Production Log", "Stock Picking", "Manage", "Admin Actions", "Insights", "Audit Trail", "Reports"])
with tab1:
    # Refresh controls
    col_refresh, col_auto = st.columns([1, 2])
    with col_refresh:
        if st.button("🔄 Refresh Dashboard", use_container_width=False):
            st.cache_data.clear()
            st.session_state.force_refresh = True
            st.toast("Dashboard refreshed from cloud!", icon="🛰️")
            st.rerun()
    
    with col_auto:
        auto_refresh = st.checkbox("Auto-refresh every 30 seconds", value=False, key="auto_refresh_dash")
        if auto_refresh:
            time.sleep(30)
            st.rerun()

    st.caption(f"Data last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if not df.empty:
        # Available categories (sorted)
        available_categories = sorted(df['Category'].unique().tolist())
        view_options = ["All Materials"] + available_categories

        # Sidebar filter
        with st.sidebar:
            st.subheader("Dashboard Filters")
            
            # Category filter
            selected_view = st.selectbox(
                "Category",
                view_options,
                index=0,
                placeholder="Select category...",
                help="Choose what to show on the dashboard",
                key="dashboard_category_filter"
            )
            
            # Sub-filters for Coils and Rolls
            selected_metal = None
            selected_gauge = None
            selected_texture = None
            
            if selected_view in ["Coils", "Rolls"]:
                st.markdown("---")
                st.markdown(f"**🔍 {selected_view} Filters**")
                
                # Get unique values from the selected category
                category_df = df[df['Category'] == selected_view].copy()
                
                # Extract metal types from Material column
                def extract_metal(material):
                    material_lower = str(material).lower()
                    if 'stainless' in material_lower:
                        return 'Stainless Steel'
                    elif 'aluminum' in material_lower:
                        return 'Aluminum'
                    elif 'galvanized' in material_lower:
                        return 'Galvanized'
                    else:
                        return 'Other'
                
                # Extract gauge from Material column
                def extract_gauge(material):
                    import re
                    match = re.search(r'\.(\d{3})', str(material))
                    if match:
                        return f".{match.group(1)}"
                    return 'Unknown'
                
                # Extract texture from Material column
                def extract_texture(material):
                    material_lower = str(material).lower()
                    if 'smooth' in material_lower:
                        return 'Smooth'
                    elif 'stucco' in material_lower:
                        return 'Stucco'
                    else:
                        return 'Other'
                
                category_df['Metal_Type'] = category_df['Material'].apply(extract_metal)
                category_df['Gauge'] = category_df['Material'].apply(extract_gauge)
                category_df['Texture'] = category_df['Material'].apply(extract_texture)
                
                # Metal filter
                metal_options = ["All"] + sorted(category_df['Metal_Type'].unique().tolist())
                selected_metal = st.selectbox(
                    "🔩 Metal Type",
                    metal_options,
                    key="dashboard_metal_filter"
                )
                
                # Gauge filter
                gauge_options = ["All"] + sorted(category_df['Gauge'].unique().tolist())
                selected_gauge = st.selectbox(
                    "📏 Gauge",
                    gauge_options,
                    key="dashboard_gauge_filter"
                )
                
                # Texture filter
                texture_options = ["All"] + sorted(category_df['Texture'].unique().tolist())
                selected_texture = st.selectbox(
                    "🎨 Texture",
                    texture_options,
                    key="dashboard_texture_filter"
                )

        # Filter data based on selections
        if selected_view == "All Materials":
            display_df = df.copy()
            st.subheader("📊 Global Material Pulse")
        else:
            display_df = df[df['Category'] == selected_view].copy()
            
            # Apply sub-filters for Coils/Rolls
            if selected_view in ["Coils", "Rolls"]:
                # Define extract functions again for this scope
                def extract_metal(material):
                    material_lower = str(material).lower()
                    if 'stainless' in material_lower:
                        return 'Stainless Steel'
                    elif 'aluminum' in material_lower:
                        return 'Aluminum'
                    elif 'galvanized' in material_lower:
                        return 'Galvanized'
                    else:
                        return 'Other'
                
                def extract_gauge(material):
                    import re
                    match = re.search(r'\.(\d{3})', str(material))
                    if match:
                        return f".{match.group(1)}"
                    return 'Unknown'
                
                def extract_texture(material):
                    material_lower = str(material).lower()
                    if 'smooth' in material_lower:
                        return 'Smooth'
                    elif 'stucco' in material_lower:
                        return 'Stucco'
                    else:
                        return 'Other'
                
                # Add extracted columns
                display_df['Metal_Type'] = display_df['Material'].apply(extract_metal)
                display_df['Gauge'] = display_df['Material'].apply(extract_gauge)
                display_df['Texture'] = display_df['Material'].apply(extract_texture)
                
                if selected_metal and selected_metal != "All":
                    display_df = display_df[display_df['Metal_Type'] == selected_metal]
                
                if selected_gauge and selected_gauge != "All":
                    display_df = display_df[display_df['Gauge'] == selected_gauge]
                
                if selected_texture and selected_texture != "All":
                    display_df = display_df[display_df['Texture'] == selected_texture]
                
                # Build subtitle
                filter_parts = []
                if selected_metal and selected_metal != "All":
                    filter_parts.append(selected_metal)
                if selected_gauge and selected_gauge != "All":
                    filter_parts.append(selected_gauge)
                if selected_texture and selected_texture != "All":
                    filter_parts.append(selected_texture)
                
                if filter_parts:
                    st.subheader(f"📊 {selected_view} - {' | '.join(filter_parts)}")
                else:
                    st.subheader(f"📊 {selected_view} Inventory Pulse")
            else:
                st.subheader(f"📊 {selected_view} Inventory Pulse")

        # Check if we have data after filtering
        if display_df.empty:
            st.warning("No items match the selected filters.")
        else:
            # DATA AGGREGATION - Group by Material to show each specific type
            summary_df = display_df.groupby(['Material', 'Category']).agg({
                'Footage': 'sum',
                'Item_ID': 'count'
            }).reset_index()
            summary_df.columns = ['Material', 'Type', 'Total_Footage', 'Unit_Count']
            
            # Sort by footage descending so highest stock appears first
            summary_df = summary_df.sort_values('Total_Footage', ascending=False)

            # TOP-LEVEL METRICS
            m1, m2, m3 = st.columns(3)
            current_total_ft = display_df['Footage'].sum()
            current_unit_count = len(display_df)
            unique_mats = len(summary_df)
            
            m1.metric("Total Footage", f"{current_total_ft:,.1f} ft")
            m2.metric("Items in View", current_unit_count)
            m3.metric("Material Types", unique_mats)

            st.divider()

            # QUICK STATS FOR COILS/ROLLS (when filtered)
            if selected_view in ["Coils", "Rolls"] and not display_df.empty:
                st.markdown("### 📈 Quick Stats")
                
                qs1, qs2, qs3, qs4 = st.columns(4)
                
                with qs1:
                    avg_footage = display_df['Footage'].mean()
                    st.metric("Avg Footage/Item", f"{avg_footage:,.1f} ft")
                
                with qs2:
                    min_footage = display_df['Footage'].min()
                    st.metric("Lowest Stock", f"{min_footage:,.1f} ft")
                
                with qs3:
                    max_footage = display_df['Footage'].max()
                    st.metric("Highest Stock", f"{max_footage:,.1f} ft")
                
                with qs4:
                    locations = display_df['Location'].nunique()
                    st.metric("Locations", locations)
                
                st.divider()

            # THE PULSE GRID - Shows each material type separately
            cols = st.columns(2)
            for idx, row in summary_df.iterrows():
                with cols[idx % 2]:
                    mat = row['Material']
                    ft = row['Total_Footage']
                    units = row['Unit_Count']
                    cat_type = row['Type']
                    
                    # --- CREATE SHORT NAME FOR DISPLAY ---
                    import re
                    
                    # Extract key info for short name
                    gauge_match = re.search(r'\.(\d{3})', mat)
                    gauge_str = f".{gauge_match.group(1)}" if gauge_match else ""
                    
                    mat_lower = mat.lower()
                    texture_str = "Smooth" if "smooth" in mat_lower else ("Stucco" if "stucco" in mat_lower else "")
                    metal_str = "Aluminum" if "aluminum" in mat_lower else ("Stainless Steel" if "stainless" in mat_lower else "")
                    
                    # Build short name (e.g., ".016 Smooth Aluminum")
                    if gauge_str and texture_str and metal_str:
                        short_name = f"{gauge_str} {texture_str} {metal_str}"
                    else:
                        # Use first 40 chars of material name if can't parse
                        short_name = mat[:40] + ("..." if len(mat) > 40 else "")
                    
                    # --- SET DEFAULTS ---
                    display_value = f"{ft:,.1f}"
                    unit_text = "Units"
                    sub_label_text = "In Stock"

                    # --- LOGIC BRANCHES ---
                    if cat_type == "Rolls":
                        # Show actual roll count with average size
                        if units > 0:
                            avg_per_roll = ft / units
                            display_value = f"{int(units)}"
                            unit_text = "Rolls"
                            sub_label_text = f"Total: {ft:,.1f} FT (~{avg_per_roll:.0f} ft/roll)"
                        else:
                            display_value = "0"
                            unit_text = "Rolls"
                            sub_label_text = "No stock"
                    
                    elif cat_type == "Coils":
                        # Show total footage and coil count
                        display_value = f"{ft:,.1f}"
                        unit_text = "FT"
                        sub_label_text = f"{int(units)} Coil{'s' if units != 1 else ''} in stock"
                    
                    elif cat_type == "Fab Straps":
                        display_value = f"{int(ft)}"
                        unit_text = "Bundles"
                        sub_label_text = f"{int(units)} item{'s' if units != 1 else ''}"

                    elif cat_type == "Elbows":
                        display_value = f"{int(ft)}"
                        unit_text = "Pcs"
                        sub_label_text = f"{int(units)} item{'s' if units != 1 else ''}"
                    
                    elif cat_type == "Wire":
                        display_value = f"{int(units)}"
                        unit_text = "Rolls"
                        sub_label_text = f"Total: {ft:,.1f} FT"
                    
                    elif cat_type == "Banding":
                        display_value = f"{int(units)}"
                        unit_text = "Rolls"
                        sub_label_text = f"Total: {ft:,.1f} FT"
                    
                    elif cat_type == "Wing Seals":
                        display_value = f"{int(ft)}"
                        unit_text = "Pcs"
                        sub_label_text = f"{int(units)} box{'es' if units != 1 else ''}"
                    
                    elif cat_type == "Mineral Wool":
                        display_value = f"{int(ft)}"
                        unit_text = "Sections"
                        sub_label_text = f"{int(units)} item{'s' if units != 1 else ''}"
                    
                    elif cat_type == "Fiberglass Insulation":
                        display_value = f"{int(units)}"
                        unit_text = "Rolls/Batts"
                        sub_label_text = f"Total: {ft:,.1f} sq ft"
                    
                    else:
                        # Generic fallback
                        display_value = f"{ft:,.1f}"
                        unit_text = "Units"
                        sub_label_text = f"{int(units)} item{'s' if units != 1 else ''}"

                    # --- THRESHOLD / HEALTH LOGIC ---
                    limit = LOW_STOCK_THRESHOLDS.get(mat, 10.0 if cat_type in ["Fab Straps", "Elbows"] else 1000.0)
                    
                    if ft < limit:
                        status_color, status_text = "#FF4B4B", "🚨 REORDER"
                    elif ft < (limit * 1.5):
                        status_color, status_text = "#FFA500", "⚠️ LOW"
                    else:
                        status_color, status_text = "#00C853", "✅ OK"

                    # --- RENDER THE CARD ---
                    st.markdown(f"""
                    <div style="background-color: #f9f9f9; padding: 20px; border-radius: 12px; 
                                border-left: 12px solid {status_color}; margin-bottom: 15px; min-height: 220px;">
                        <p style="color: #666; font-size: 11px; margin: 0; font-weight: bold;">{cat_type.upper()}</p>
                        <h3 style="margin: 5px 0 0 0; font-size: 18px; color: #1e293b;">{short_name}</h3>
                        <p style="color: #94a3b8; font-size: 10px; margin: 2px 0 10px 0; word-wrap: break-word;">{mat}</p>
                        <h1 style="margin: 10px 0; color: {status_color};">{display_value} <span style="font-size: 16px;">{unit_text}</span></h1>
                        <p style="color: #666; font-size: 13px; margin: 5px 0;">{sub_label_text}</p>
                        <div style="display: flex; justify-content: space-between; align-items: center; border-top: 1px solid #eee; padding-top: 10px; margin-top: 10px;">
                            <span style="font-weight: bold; color: {status_color}; font-size: 12px;">{status_text}</span>
                            <span style="color: #888; font-size: 11px;">{units} ID{'s' if units != 1 else ''}</span>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            
            # INDIVIDUAL ITEM TABLE
            with st.expander(f"🔍 View Individual Items ({len(display_df)} items)"):
                # Show additional columns for Coils/Rolls
                if selected_view in ["Coils", "Rolls"] and 'Metal_Type' in display_df.columns:
                    st.dataframe(
                        display_df[['Item_ID', 'Material', 'Metal_Type', 'Gauge', 'Texture', 'Footage', 'Location']].sort_values('Material'), 
                        use_container_width=True, 
                        hide_index=True
                    )
                else:
                    st.dataframe(
                        display_df[['Item_ID', 'Category', 'Material', 'Footage', 'Location']].sort_values('Material'), 
                        use_container_width=True, 
                        hide_index=True
                    )
    else:
        st.info("No data available. Add inventory in the Receive tab.")

# ── TAB 2: Production Log ────────────────────────────────────────────────────────
with tab2:
    st.subheader("📋 Production Log - Multi-Size Orders with Coil Pooling")

    # ══════════════════════════════════════════════════════════════════════════════
    # MST TIMESTAMP HELPER
    # ══════════════════════════════════════════════════════════════════════════════
    def get_mst_timestamp():
        """Get current timestamp in Mountain Standard Time"""
        from datetime import timezone, timedelta
        utc_now = datetime.now(timezone.utc)
        mst_offset = timedelta(hours=-7)  # MST is UTC-7
        mst_now = utc_now + mst_offset
        return mst_now.strftime('%Y-%m-%dT%H:%M:%S')
    
    def get_mst_display():
        """Get formatted display timestamp in MST"""
        from datetime import timezone, timedelta
        utc_now = datetime.now(timezone.utc)
        mst_offset = timedelta(hours=-7)
        mst_now = utc_now + mst_offset
        return mst_now.strftime('%B %d, %Y at %I:%M %p MST')

    # Guard rails
    if df.empty:
        st.warning("⚠️ No inventory data found. Please add items first.")

    # Safe column name handling
    category_col = next((c for c in df.columns if c.lower() == 'category'), None)
    if not category_col:
        st.error("Column 'Category' not found in inventory data.")

    # Initialize session state - start with one default line each
    if "coil_lines" not in st.session_state:
        st.session_state.coil_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "pool": [], "use_custom": False, "custom_inches": 12.0}]
    if "roll_lines" not in st.session_state:
        st.session_state.roll_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "pool": [], "use_custom": False, "custom_inches": 12.0}]

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

    available_coils = filter_materials(df[(df[category_col] == "Coils") & (df['Footage'] > 0)])
    available_rolls = filter_materials(df[(df[category_col] == "Rolls") & (df['Footage'] > 0)])

    if available_coils.empty and available_rolls.empty:
        st.info("No available stock matching the selected texture.")

    # Create option lists with footage info
    coil_options = [f"{r['Item_ID']} | {r['Material'][:30]}... | {r['Footage']:.1f} ft" for _, r in available_coils.iterrows()]
    roll_options = [f"{r['Item_ID']} | {r['Material'][:30]}... | {r['Footage']:.1f} ft" for _, r in available_rolls.iterrows()]

    # ══════════════════════════════════════════════════════════════════════════════
    # POOL HELPER FUNCTIONS
    # ══════════════════════════════════════════════════════════════════════════════
    
    def calculate_pool_capacity(pool_ids, available_df):
        """Calculate total available footage in a pool"""
        total = 0
        for item_id in pool_ids:
            match = available_df[available_df['Item_ID'] == item_id]
            if not match.empty:
                total += float(match.iloc[0]['Footage'])
        return total
    
    def get_pool_details(pool_ids, available_df):
        """Get detailed info for each item in pool"""
        details = []
        for item_id in pool_ids:
            match = available_df[available_df['Item_ID'] == item_id]
            if not match.empty:
                row = match.iloc[0]
                details.append({
                    'id': item_id,
                    'material': row['Material'],
                    'footage': float(row['Footage']),
                    'location': row.get('Location', 'N/A')
                })
        return details

    def process_pool_deduction(pool_ids, total_needed, production_footage, waste_footage, available_df, 
                                supabase_client, operator, order_number, client_name, line_description, size_label, pieces):
        """
        Process sequential deduction from a pool of coils/rolls.
        Returns: (success: bool, deduction_log: list, error_message: str)
        """
        # Get current footage for each item in pool (fresh from DB)
        pool_items = []
        for item_id in pool_ids:
            try:
                response = supabase_client.table("inventory").select("*").eq("Item_ID", item_id).execute()
                if response.data:
                    item_data = response.data[0]
                    pool_items.append({
                        'id': item_id,
                        'footage': float(item_data['Footage']),
                        'material': item_data['Material']
                    })
            except Exception as e:
                return False, [], f"Error fetching {item_id}: {e}"
        
        # Calculate total available
        total_available = sum(item['footage'] for item in pool_items)
        
        if total_available < total_needed:
            return False, [], f"Insufficient pool capacity: need {total_needed:.2f} ft, pool has {total_available:.2f} ft"
        
        # Sequential deduction
        remaining_needed = total_needed
        deduction_log = []
        
        for item in pool_items:
            if remaining_needed <= 0:
                break
            
            available = item['footage']
            deduct_amount = min(available, remaining_needed)
            new_footage = available - deduct_amount
            
            # Calculate proportion for this deduction (for splitting production vs waste)
            proportion = deduct_amount / total_needed if total_needed > 0 else 0
            item_production = production_footage * proportion
            item_waste = waste_footage * proportion
            
            # Determine new status
            new_status = "Depleted" if new_footage <= 0 else "Active"
            
            # Update database
            try:
                update_data = {"Footage": new_footage}
                if new_footage <= 0:
                    update_data["Status"] = "Depleted"
                
                supabase_client.table("inventory").update(update_data).eq("Item_ID", item['id']).execute()
                
                # Log this deduction
                deduction_log.append({
                    'source_id': item['id'],
                    'material': item['material'],
                    'size': size_label,
                    'pieces': pieces,
                    'footage_used': deduct_amount,
                    'production_footage': item_production,
                    'waste': item_waste,
                    'previous_footage': available,
                    'remaining_footage': new_footage,
                    'status': new_status
                })
                
                # Audit log entry with MST timestamp
                log_entry = {
                    "Item_ID": item['id'],
                    "Action": f"Production: {pieces} pcs of {size_label}",
                    "User": operator,
                    "Timestamp": get_mst_timestamp(),
                    "Details": f"Production: {pieces} pcs of {size_label} ({item_production:.2f} ft production + {item_waste:.2f} ft waste = {deduct_amount:.2f} ft used) for {client_name} (Order: {order_number}) | Pool deduction | Previous: {available:.2f} ft → Remaining: {new_footage:.2f} ft | Status: {new_status}"
                }
                supabase_client.table("audit_log").insert(log_entry).execute()
                
                remaining_needed -= deduct_amount
                
            except Exception as e:
                return False, deduction_log, f"Error updating {item['id']}: {e}"
        
        return True, deduction_log, ""

    # ══════════════════════════════════════════════════════════════════════════════
    # COILS SECTION WITH POOL
    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown("### 🌀 Coils Production")
    
    # Extra allowance - DEFAULT IS 0
    coil_extra = st.number_input(
        "Extra Inch Allowance per piece (Coils)",
        min_value=0.0, 
        value=0.0,  # DEFAULT TO 0
        step=0.1,
        key="coil_extra_allowance",
        help="Additional inches added to each piece for trim/overlap"
    )

    # Add "Custom" to size options
    COIL_SIZE_OPTIONS = list(SIZE_DISPLAY.keys()) + ["Custom (Inches)", "Custom (Feet)"]

    for i in range(len(st.session_state.coil_lines)):
        line = st.session_state.coil_lines[i]
        
        with st.container(border=True):
            st.markdown(f"**📦 Coil Production Line {i + 1}**")
            
            col1, col2, col3, col4, col5 = st.columns([2, 1.5, 1, 1, 0.4])
            
            with col1:
                current_size = line.get("display_size", "#2")
                if current_size in COIL_SIZE_OPTIONS:
                    default_index = COIL_SIZE_OPTIONS.index(current_size)
                else:
                    default_index = 0
                
                size_selection = st.selectbox(
                    "📐 Size",
                    COIL_SIZE_OPTIONS,
                    index=default_index,
                    key=f"c_size_{i}"
                )
                st.session_state.coil_lines[i]["display_size"] = size_selection
            
            with col2:
                if size_selection == "Custom (Inches)":
                    custom_val = st.number_input(
                        "📏 Inches per piece",
                        min_value=0.1,
                        value=float(line.get("custom_inches", 12.0)),
                        step=0.25,
                        key=f"c_custom_in_{i}"
                    )
                    st.session_state.coil_lines[i]["custom_inches"] = custom_val
                    st.session_state.coil_lines[i]["use_custom"] = True
                    st.session_state.coil_lines[i]["custom_unit"] = "inches"
                    
                elif size_selection == "Custom (Feet)":
                    custom_val = st.number_input(
                        "📏 Feet per piece",
                        min_value=0.1,
                        value=float(line.get("custom_feet", 1.0)),
                        step=0.5,
                        key=f"c_custom_ft_{i}"
                    )
                    st.session_state.coil_lines[i]["custom_feet"] = custom_val
                    st.session_state.coil_lines[i]["custom_inches"] = custom_val * 12
                    st.session_state.coil_lines[i]["use_custom"] = True
                    st.session_state.coil_lines[i]["custom_unit"] = "feet"
                else:
                    st.session_state.coil_lines[i]["use_custom"] = False
                    st.session_state.coil_lines[i]["custom_inches"] = SIZE_DISPLAY.get(size_selection, 12.0)
            
            with col3:
                pieces_val = st.number_input(
                    "🔢 Pieces",
                    min_value=0,
                    value=int(line.get("pieces", 0)),
                    step=1,
                    key=f"c_pcs_{i}"
                )
                st.session_state.coil_lines[i]["pieces"] = pieces_val
            
            with col4:
                waste_val = st.number_input(
                    "🗑️ Waste (ft)",
                    min_value=0.0,
                    value=float(line.get("waste", 0.0)),
                    step=0.5,
                    key=f"c_waste_{i}"
                )
                st.session_state.coil_lines[i]["waste"] = waste_val
            
            with col5:
                if st.button("🗑", key=f"del_coil_{i}", help="Remove line"):
                    st.session_state.coil_lines.pop(i)
                    st.rerun()
            
            # Calculate required footage for this line
            if pieces_val > 0:
                if size_selection in ["Custom (Inches)", "Custom (Feet)"]:
                    calc_inches = (st.session_state.coil_lines[i]["custom_inches"] + coil_extra) * pieces_val
                else:
                    std_inches = SIZE_DISPLAY.get(size_selection, 12.0)
                    calc_inches = (std_inches + coil_extra) * pieces_val
                
                production_footage = calc_inches / 12.0
                total_footage_needed = production_footage + waste_val
                
                # Show calculated footage
                st.caption(f"📊 **Production:** {production_footage:.2f} ft + **Waste:** {waste_val:.1f} ft = **Total:** {total_footage_needed:.2f} ft")
            else:
                production_footage = 0
                total_footage_needed = 0
            
            # ── COIL POOL SELECTOR ──────────────────────────────────────────────
            st.markdown("---")
            st.markdown("**🏊 Coil Pool** - Select source coils in order of deduction")
            
            # Initialize pool if not exists
            if "pool" not in st.session_state.coil_lines[i]:
                st.session_state.coil_lines[i]["pool"] = []
            
            current_pool = st.session_state.coil_lines[i]["pool"]
            
            # Pool management columns
            pool_col1, pool_col2 = st.columns([3, 2])
            
            with pool_col1:
                # Filter out already selected coils
                available_for_pool = [opt for opt in coil_options if opt.split(" | ")[0] not in current_pool]
                
                add_to_pool = st.selectbox(
                    "➕ Add coil to pool",
                    ["-- Select to add --"] + available_for_pool,
                    key=f"add_pool_coil_{i}"
                )
                
                if add_to_pool != "-- Select to add --":
                    if st.button("➕ Add to Pool", key=f"btn_add_pool_{i}", type="secondary"):
                        coil_id = add_to_pool.split(" | ")[0]
                        st.session_state.coil_lines[i]["pool"].append(coil_id)
                        st.rerun()
            
            with pool_col2:
                # Pool capacity display
                pool_capacity = calculate_pool_capacity(current_pool, available_coils)
                
                if total_footage_needed > 0:
                    if pool_capacity >= total_footage_needed:
                        st.success(f"✅ Pool: {pool_capacity:,.1f} ft available")
                        st.caption(f"Need: {total_footage_needed:,.1f} ft")
                    else:
                        shortage = total_footage_needed - pool_capacity
                        st.error(f"❌ Pool: {pool_capacity:,.1f} ft (short {shortage:,.1f} ft)")
                else:
                    st.info(f"🏊 Pool: {pool_capacity:,.1f} ft available")
            
            # Display current pool with reordering
            if current_pool:
                st.markdown("**📋 Current Pool (deduction order):**")
                
                pool_details = get_pool_details(current_pool, available_coils)
                
                for idx, item in enumerate(pool_details):
                    pcol1, pcol2, pcol3, pcol4 = st.columns([0.3, 2.5, 1, 0.5])
                    
                    with pcol1:
                        st.markdown(f"**{idx + 1}.**")
                    
                    with pcol2:
                        st.markdown(f"`{item['id']}` - **{item['footage']:,.1f} ft**")
                        st.caption(f"{item['material'][:40]}...")
                    
                    with pcol3:
                        # Move up/down buttons
                        btn_col1, btn_col2 = st.columns(2)
                        with btn_col1:
                            if idx > 0:
                                if st.button("⬆️", key=f"up_{i}_{idx}", help="Move up"):
                                    pool = st.session_state.coil_lines[i]["pool"]
                                    pool[idx], pool[idx-1] = pool[idx-1], pool[idx]
                                    st.rerun()
                        with btn_col2:
                            if idx < len(current_pool) - 1:
                                if st.button("⬇️", key=f"down_{i}_{idx}", help="Move down"):
                                    pool = st.session_state.coil_lines[i]["pool"]
                                    pool[idx], pool[idx+1] = pool[idx+1], pool[idx]
                                    st.rerun()
                    
                    with pcol4:
                        if st.button("❌", key=f"remove_pool_{i}_{idx}", help="Remove"):
                            st.session_state.coil_lines[i]["pool"].pop(idx)
                            st.rerun()
                
                # Show deduction preview
                if total_footage_needed > 0 and pool_capacity >= total_footage_needed:
                    with st.expander("👁️ Preview Deduction Sequence"):
                        remaining = total_footage_needed
                        st.markdown("**How footage will be deducted:**")
                        
                        for item in pool_details:
                            if remaining <= 0:
                                st.markdown(f"- `{item['id']}`: ✅ No deduction needed (stays at {item['footage']:,.1f} ft)")
                                continue
                            
                            deduct = min(item['footage'], remaining)
                            new_footage = item['footage'] - deduct
                            status = "🔴 **DEPLETED**" if new_footage <= 0 else f"🟢 {new_footage:,.1f} ft remaining"
                            
                            st.markdown(f"- `{item['id']}`: **-{deduct:,.1f} ft** → {status}")
                            remaining -= deduct
            else:
                st.info("👆 Add coils to the pool above")
                
            # Option to copy this pool to all other coil lines
            if current_pool and len(st.session_state.coil_lines) > 1:
                if st.button("📋 Copy this pool to all coil lines", key=f"copy_pool_coil_{i}", type="secondary"):
                    for j, other_line in enumerate(st.session_state.coil_lines):
                        if j != i:  # Don't copy to itself
                            st.session_state.coil_lines[j]["pool"] = current_pool.copy()
                    st.success(f"✅ Pool copied to {len(st.session_state.coil_lines) - 1} other line(s)")
                    st.rerun()
            
            # Show summary for custom sizes
            if size_selection in ["Custom (Inches)", "Custom (Feet)"] and pieces_val > 0:
                if st.session_state.coil_lines[i].get("custom_unit") == "feet":
                    st.caption(f"📋 {pieces_val} pieces × {st.session_state.coil_lines[i].get('custom_feet', 0)} ft + {coil_extra}\" allowance + {waste_val} ft waste")
                else:
                    st.caption(f"📋 {pieces_val} pieces × {st.session_state.coil_lines[i].get('custom_inches', 0)} in + {coil_extra}\" allowance + {waste_val} ft waste")

    # Add another roll line - auto-populate pool from previous line
    if st.button("➕ Add another roll size", use_container_width=True, key="add_roll_line"):
        # Get pool from the last line (if exists) to auto-populate
        if st.session_state.roll_lines:
            last_pool = st.session_state.roll_lines[-1].get("pool", []).copy()
        else:
            last_pool = []
        
        st.session_state.roll_lines.append({
            "display_size": "#2", 
            "pieces": 0, 
            "waste": 0.0,
            "pool": last_pool,  # Auto-populate from previous line
            "use_custom": False, 
            "custom_inches": 12.0
        })
        st.rerun()
        
    st.divider()

    # ══════════════════════════════════════════════════════════════════════════════
    # ROLLS SECTION WITH POOL
    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown("### 🗞️ Rolls Production")
    
    # Extra allowance - DEFAULT IS 0
    roll_extra = st.number_input(
        "Extra Inch Allowance per piece (Rolls)",
        min_value=0.0, 
        value=0.0,  # DEFAULT TO 0
        step=0.1,
        key="roll_extra_allowance",
        help="Additional inches added to each piece for trim/overlap"
    )

    for i in range(len(st.session_state.roll_lines)):
        line = st.session_state.roll_lines[i]
        
        with st.container(border=True):
            st.markdown(f"**📦 Roll Production Line {i + 1}**")
            
            r1, r2, r3, r4 = st.columns([3, 1.2, 1.2, 0.4])
            
            with r1:
                current_roll_size = line.get("display_size", "#2")
                if current_roll_size in list(SIZE_DISPLAY.keys()):
                    roll_default_idx = list(SIZE_DISPLAY.keys()).index(current_roll_size)
                else:
                    roll_default_idx = 0
                
                line["display_size"] = st.selectbox(
                    "Size", list(SIZE_DISPLAY.keys()),
                    index=roll_default_idx,
                    key=f"r_size_{i}"
                )
            with r2:
                line["pieces"] = st.number_input(
                    "Pieces", min_value=0, step=1,
                    value=int(line.get("pieces", 0)),
                    key=f"r_pcs_{i}"
                )
            with r3:
                line["waste"] = st.number_input(
                    "Waste (ft)", min_value=0.0, step=0.5,
                    value=float(line.get("waste", 0.0)),
                    key=f"r_waste_{i}"
                )
            with r4:
                if st.button("🗑", key=f"del_roll_{i}", help="Remove line"):
                    st.session_state.roll_lines.pop(i)
                    st.rerun()

            line["use_custom"] = st.checkbox(
                "Use custom inches instead of standard size",
                value=line.get("use_custom", False),
                key=f"r_custom_chk_{i}"
            )

            if line["use_custom"]:
                current_custom = line.get("custom_inches", 12.0)
                line["custom_inches"] = st.number_input(
                    "Custom length per piece (inches)",
                    min_value=0.1,
                    value=float(current_custom) if current_custom else 12.0,
                    step=0.25,
                    key=f"r_custom_in_{i}"
                )
            else:
                line["custom_inches"] = 0.0
            
            # Calculate required footage
            if line["pieces"] > 0:
                if line["use_custom"]:
                    calc_inches = (line["custom_inches"] + roll_extra) * line["pieces"]
                else:
                    std_inches = SIZE_DISPLAY.get(line["display_size"], 12.0)
                    calc_inches = (std_inches + roll_extra) * line["pieces"]
                
                roll_production_footage = calc_inches / 12.0
                roll_total_needed = roll_production_footage + line["waste"]
                
                st.caption(f"📊 **Production:** {roll_production_footage:.2f} ft + **Waste:** {line['waste']:.1f} ft = **Total:** {roll_total_needed:.2f} ft")
            else:
                roll_production_footage = 0
                roll_total_needed = 0

            # ── ROLL POOL SELECTOR ──────────────────────────────────────────────
            st.markdown("---")
            st.markdown("**🏊 Roll Pool** - Select source rolls in order of deduction")
            
            if "pool" not in line:
                line["pool"] = []
            
            current_roll_pool = line["pool"]
            
            rpool_col1, rpool_col2 = st.columns([3, 2])
            
            with rpool_col1:
                available_for_roll_pool = [opt for opt in roll_options if opt.split(" | ")[0] not in current_roll_pool]
                
                add_to_roll_pool = st.selectbox(
                    "➕ Add roll to pool",
                    ["-- Select to add --"] + available_for_roll_pool,
                    key=f"add_pool_roll_{i}"
                )
                
                if add_to_roll_pool != "-- Select to add --":
                    if st.button("➕ Add to Pool", key=f"btn_add_roll_pool_{i}", type="secondary"):
                        roll_id = add_to_roll_pool.split(" | ")[0]
                        line["pool"].append(roll_id)
                        st.rerun()
            
            with rpool_col2:
                roll_pool_capacity = calculate_pool_capacity(current_roll_pool, available_rolls)
                
                if roll_total_needed > 0:
                    if roll_pool_capacity >= roll_total_needed:
                        st.success(f"✅ Pool: {roll_pool_capacity:,.1f} ft")
                        st.caption(f"Need: {roll_total_needed:,.1f} ft")
                    else:
                        shortage = roll_total_needed - roll_pool_capacity
                        st.error(f"❌ Short {shortage:,.1f} ft")
                else:
                    st.info(f"🏊 Pool: {roll_pool_capacity:,.1f} ft")
            
            # Display current roll pool
            if current_roll_pool:
                st.markdown("**📋 Current Pool (deduction order):**")
                
                roll_pool_details = get_pool_details(current_roll_pool, available_rolls)
                
                for idx, item in enumerate(roll_pool_details):
                    rpcol1, rpcol2, rpcol3, rpcol4 = st.columns([0.3, 2.5, 1, 0.5])
                    
                    with rpcol1:
                        st.markdown(f"**{idx + 1}.**")
                    
                    with rpcol2:
                        st.markdown(f"`{item['id']}` - **{item['footage']:,.1f} ft**")
                        st.caption(f"{item['material'][:40]}...")
                    
                    with rpcol3:
                        btn_c1, btn_c2 = st.columns(2)
                        with btn_c1:
                            if idx > 0 and st.button("⬆️", key=f"rup_{i}_{idx}"):
                                line["pool"][idx], line["pool"][idx-1] = line["pool"][idx-1], line["pool"][idx]
                                st.rerun()
                        with btn_c2:
                            if idx < len(current_roll_pool) - 1 and st.button("⬇️", key=f"rdown_{i}_{idx}"):
                                line["pool"][idx], line["pool"][idx+1] = line["pool"][idx+1], line["pool"][idx]
                                st.rerun()
                    
                    with rpcol4:
                        if st.button("❌", key=f"rrem_{i}_{idx}"):
                            line["pool"].pop(idx)
                            st.rerun()
                
                # Preview
                if roll_total_needed > 0 and roll_pool_capacity >= roll_total_needed:
                    with st.expander("👁️ Preview Deduction Sequence"):
                        remaining = roll_total_needed
                        for item in roll_pool_details:
                            if remaining <= 0:
                                st.markdown(f"- `{item['id']}`: ✅ No deduction (stays at {item['footage']:,.1f} ft)")
                                continue
                            deduct = min(item['footage'], remaining)
                            new_footage = item['footage'] - deduct
                            status = "🔴 **DEPLETED**" if new_footage <= 0 else f"🟢 {new_footage:,.1f} ft remaining"
                            st.markdown(f"- `{item['id']}`: **-{deduct:,.1f} ft** → {status}")
                            remaining -= deduct
            else:
                st.info("👆 Add rolls to the pool above")
                
    #Add another roll line - auto-populate pool from previous line
    if st.button("➕ Add another roll size", use_container_width=True, key="add_roll_line"):
        # Get pool from the last line (if exists) to auto-populate
        if st.session_state.roll_lines:
            last_pool = st.session_state.roll_lines[-1].get("pool", []).copy()
        else:
            last_pool = []
        
        st.session_state.roll_lines.append({
            "display_size": "#2", 
            "pieces": 0, 
            "waste": 0.0,
            "pool": last_pool,  # Auto-populate from previous line
            "use_custom": False, 
            "custom_inches": 12.0
        })
        st.rerun()
        
    st.divider()

    # ══════════════════════════════════════════════════════════════════════════════
    # SUBMISSION FORM
    # ══════════════════════════════════════════════════════════════════════════════
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
            # ══════════════════════════════════════════════════════════════════════
            # VALIDATION - Check all pools have sufficient capacity
            # ══════════════════════════════════════════════════════════════════════
            validation_errors = []
            
            # Check coil lines
            for i, line in enumerate(st.session_state.coil_lines):
                if line["pieces"] <= 0:
                    continue
                
                if not line.get("pool"):
                    validation_errors.append(f"Coil Line {i+1}: No coils in pool")
                    continue
                
                # Calculate required footage
                if line.get("use_custom") or line["display_size"] in ["Custom (Inches)", "Custom (Feet)"]:
                    calc_inches = (line.get("custom_inches", 12.0) + coil_extra) * line["pieces"]
                else:
                    std_inches = SIZE_DISPLAY.get(line["display_size"], 12.0)
                    calc_inches = (std_inches + coil_extra) * line["pieces"]
                
                production_footage = calc_inches / 12.0
                total_needed = production_footage + line["waste"]
                
                pool_capacity = calculate_pool_capacity(line["pool"], available_coils)
                
                if pool_capacity < total_needed:
                    validation_errors.append(f"Coil Line {i+1}: Pool has {pool_capacity:.1f} ft, needs {total_needed:.1f} ft")
            
            # Check roll lines
            for i, line in enumerate(st.session_state.roll_lines):
                if line["pieces"] <= 0:
                    continue
                
                if not line.get("pool"):
                    validation_errors.append(f"Roll Line {i+1}: No rolls in pool")
                    continue
                
                if line.get("use_custom"):
                    calc_inches = (line.get("custom_inches", 12.0) + roll_extra) * line["pieces"]
                else:
                    std_inches = SIZE_DISPLAY.get(line["display_size"], 12.0)
                    calc_inches = (std_inches + roll_extra) * line["pieces"]
                
                production_footage = calc_inches / 12.0
                total_needed = production_footage + line["waste"]
                
                pool_capacity = calculate_pool_capacity(line["pool"], available_rolls)
                
                if pool_capacity < total_needed:
                    validation_errors.append(f"Roll Line {i+1}: Pool has {pool_capacity:.1f} ft, needs {total_needed:.1f} ft")
            
            if validation_errors:
                st.error("❌ **Validation Errors:**")
                for err in validation_errors:
                    st.error(f"• {err}")
            else:
                # ══════════════════════════════════════════════════════════════════
                # PROCESS ALL LINES
                # ══════════════════════════════════════════════════════════════════
                with st.spinner("Processing production order..."):
                    all_deductions = []
                    pool_mapping = {}
                    success = True
                    feedback = []
                    
                    # Process Coil Lines
                    for i, line in enumerate(st.session_state.coil_lines):
                        if line["pieces"] <= 0:
                            continue
                        
                        size_label = line["display_size"]
                        if line.get("use_custom") or line["display_size"] in ["Custom (Inches)", "Custom (Feet)"]:
                            if line.get("custom_unit") == "feet":
                                size_label = f"Custom {line.get('custom_feet', 1.0)} ft"
                            else:
                                size_label = f"Custom {line.get('custom_inches', 12.0)} in"
                        
                        # Calculate footage
                        if line.get("use_custom") or line["display_size"] in ["Custom (Inches)", "Custom (Feet)"]:
                            calc_inches = (line.get("custom_inches", 12.0) + coil_extra) * line["pieces"]
                        else:
                            std_inches = SIZE_DISPLAY.get(line["display_size"], 12.0)
                            calc_inches = (std_inches + coil_extra) * line["pieces"]
                        
                        production_footage = calc_inches / 12.0
                        waste_footage = line["waste"]
                        total_needed = production_footage + waste_footage
                        
                        line_desc = f"Coil Production: {line['pieces']} pcs of {size_label}"
                        
                        ok, deduction_log, error = process_pool_deduction(
                            pool_ids=line["pool"],
                            total_needed=total_needed,
                            production_footage=production_footage,
                            waste_footage=waste_footage,
                            available_df=available_coils,
                            supabase_client=supabase,
                            operator=operator_name,
                            order_number=order_number,
                            client_name=client_name,
                            line_description=line_desc,
                            size_label=size_label,
                            pieces=line["pieces"]
                        )
                        
                        if not ok:
                            st.error(f"❌ Coil Line {i+1}: {error}")
                            success = False
                            break
                        
                        # Store for PDF
                        for ded in deduction_log:
                            ded['material_type'] = 'Coil'
                            all_deductions.append(ded)
                        
                        pool_mapping[f"coil_line_{i+1}"] = {
                            'size': size_label,
                            'pieces': line['pieces'],
                            'total_footage': total_needed,
                            'production_footage': production_footage,
                            'waste': waste_footage,
                            'sources': deduction_log
                        }
                        
                        # Build traceability string
                        source_breakdown = " | ".join([f"{d['footage_used']:.1f}ft from {d['source_id']}" for d in deduction_log])
                        feedback.append(f"✓ Coil {size_label}: {line['pieces']} pcs ({total_needed:.2f} ft) ← {source_breakdown}")
                    
                    # Process Roll Lines
                    if success:
                        for i, line in enumerate(st.session_state.roll_lines):
                            if line["pieces"] <= 0:
                                continue
                            
                            size_label = line["display_size"]
                            if line.get("use_custom"):
                                size_label = f"Custom {line.get('custom_inches', 12.0)} in"
                            
                            if line.get("use_custom"):
                                calc_inches = (line.get("custom_inches", 12.0) + roll_extra) * line["pieces"]
                            else:
                                std_inches = SIZE_DISPLAY.get(line["display_size"], 12.0)
                                calc_inches = (std_inches + roll_extra) * line["pieces"]
                            
                            production_footage = calc_inches / 12.0
                            waste_footage = line["waste"]
                            total_needed = production_footage + waste_footage
                            
                            line_desc = f"Roll Production: {line['pieces']} pcs of {size_label}"
                            
                            ok, deduction_log, error = process_pool_deduction(
                                pool_ids=line["pool"],
                                total_needed=total_needed,
                                production_footage=production_footage,
                                waste_footage=waste_footage,
                                available_df=available_rolls,
                                supabase_client=supabase,
                                operator=operator_name,
                                order_number=order_number,
                                client_name=client_name,
                                line_description=line_desc,
                                size_label=size_label,
                                pieces=line["pieces"]
                            )
                            
                            if not ok:
                                st.error(f"❌ Roll Line {i+1}: {error}")
                                success = False
                                break
                            
                            for ded in deduction_log:
                                ded['material_type'] = 'Roll'
                                all_deductions.append(ded)
                            
                            pool_mapping[f"roll_line_{i+1}"] = {
                                'size': size_label,
                                'pieces': line['pieces'],
                                'total_footage': total_needed,
                                'production_footage': production_footage,
                                'waste': waste_footage,
                                'sources': deduction_log
                            }
                            
                            source_breakdown = " | ".join([f"{d['footage_used']:.1f}ft from {d['source_id']}" for d in deduction_log])
                            feedback.append(f"✓ Roll {size_label}: {line['pieces']} pcs ({total_needed:.2f} ft) ← {source_breakdown}")
                    
                    if success:
                        st.success(f"Order **{order_number}** completed successfully! 🎉")
                        
                        for msg in feedback:
                            st.info(msg)
                        
                        # Show pool deduction summary
                        st.markdown("### 📊 Pool Deduction Summary")
                        
                        for line_key, line_data in pool_mapping.items():
                            with st.expander(f"📦 {line_key.replace('_', ' ').title()}: {line_data['size']} ({line_data['pieces']} pcs)"):
                                st.markdown(f"**Total:** {line_data['total_footage']:.2f} ft (Production: {line_data['production_footage']:.2f} + Waste: {line_data['waste']:.2f})")
                                st.markdown("**Source Breakdown:**")
                                for src in line_data['sources']:
                                    status_icon = "🔴" if src['status'] == 'Depleted' else "🟢"
                                    st.markdown(f"- `{src['source_id']}`: **{src['footage_used']:.2f} ft** | {src['previous_footage']:.1f} → {src['remaining_footage']:.1f} ft {status_icon}")
                        
                        # Generate PDF
                        pdf_buffer = generate_production_pdf(
                            order_number=order_number,
                            client_name=client_name,
                            operator_name=operator_name,
                            deduction_details=all_deductions,
                            box_usage=box_usage,
                            coil_extra=coil_extra,
                            roll_extra=roll_extra
                        )

                        # Send email
                        if send_production_pdf(pdf_buffer, order_number, client_name):
                            st.balloons()
                            st.success("PDF generated and emailed to admin!")
                        else:
                            st.warning("PDF generated, but email failed.")

                        # Clear lines
                        st.session_state.coil_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "pool": [], "use_custom": False, "custom_inches": 12.0}]
                        st.session_state.roll_lines = [{"display_size": "#2", "pieces": 0, "waste": 0.0, "pool": [], "use_custom": False, "custom_inches": 12.0}]

                        # Force refresh
                        st.cache_data.clear()
                        if 'df' in st.session_state:
                            del st.session_state['df']
                        if 'df_audit' in st.session_state:
                            del st.session_state['df_audit']
                        st.session_state.force_refresh = True
                        
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error("Order failed — check errors above.")

    # ══════════════════════════════════════════════════════════════════════════════
    # PRODUCTION ORDER REVERSAL SECTION
    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h2 style="color: #dc2626; margin: 0;">🔄 Reverse Production Order</h2>
            <p style="color: #64748b; margin-top: 8px;">Undo a production order and restore deducted footage</p>
        </div>
    """, unsafe_allow_html=True)
    
    with st.expander("🔄 Reverse a Production Order", expanded=False):
        st.warning("⚠️ **Use with caution!** This will restore footage to the source materials.")
        
        try:
            # Fetch recent production orders from audit log
            response = supabase.table("audit_log").select("*").ilike("Action", "%Production%").order("Timestamp", desc=True).limit(100).execute()
            
            if not response.data:
                st.info("📭 No recent production orders found")
            else:
                # Group by order number (extract from Details)
                import re
                from collections import defaultdict
                
                orders = defaultdict(list)
                
                for log in response.data:
                    details = log.get('Details', '')
                    # Extract order number from details
                    order_match = re.search(r'\(Order:\s*([^)]+)\)', details)
                    if order_match:
                        order_num = order_match.group(1).strip()
                        orders[order_num].append(log)
                
                if not orders:
                    st.info("📭 No production orders with order numbers found")
                else:
                    # Create selection list
                    order_options = []
                    for order_num, logs in orders.items():
                        latest_log = max(logs, key=lambda x: x.get('Timestamp', ''))
                        details = latest_log.get('Details', '')
                        
                        # Extract client name
                        client_match = re.search(r'for\s+([^(]+)\s*\(Order:', details)
                        client_name_extracted = client_match.group(1).strip() if client_match else "Unknown"
                        
                        timestamp = latest_log.get('Timestamp', '')[:16]
                        
                        order_options.append({
                            'display': f"{order_num} - {client_name_extracted} ({timestamp})",
                            'order_num': order_num,
                            'logs': logs,
                            'client': client_name_extracted,
                            'timestamp': timestamp
                        })
                    
                    order_options.sort(key=lambda x: x['timestamp'], reverse=True)
                    
                    selected_order = st.selectbox(
                        "Select Production Order to Reverse",
                        options=["-- Select an order --"] + [o['display'] for o in order_options],
                        key="reverse_order_select"
                    )
                    
                    if selected_order != "-- Select an order --":
                        selected = next((o for o in order_options if o['display'] == selected_order), None)
                        
                        if selected:
                            st.markdown("---")
                            st.markdown(f"### 📋 Order Details: {selected['order_num']}")
                            st.write(f"**Client:** {selected['client']}")
                            st.write(f"**Date:** {selected['timestamp']}")
                            
                            st.markdown("**Items to Restore:**")
                            
                            items_to_restore = []
                            
                            for log in selected['logs']:
                                details = log.get('Details', '')
                                item_id = log.get('Item_ID', '')
                                
                                # Parse footage - handle both old and new format
                                # New format: "Production: X pcs of SIZE (Y ft production + Z ft waste = W ft used)"
                                # Old format: "Production: X pcs of SIZE (W ft used)"
                                
                                footage_match = re.search(r'(\d+\.?\d*)\s*ft\s*(?:used|production)', details)
                                pieces_match = re.search(r'Production:\s*(\d+)\s*pcs\s*of\s*([^(]+)', details)
                                
                                # Try to get total used (for pool deductions)
                                total_match = re.search(r'=\s*(\d+\.?\d*)\s*ft\s*used', details)
                                
                                if total_match:
                                    footage_used = float(total_match.group(1))
                                elif footage_match:
                                    footage_used = float(footage_match.group(1))
                                else:
                                    continue
                                
                                pieces = int(pieces_match.group(1)) if pieces_match else 0
                                size = pieces_match.group(2).strip() if pieces_match else "Unknown"
                                
                                items_to_restore.append({
                                    'item_id': item_id,
                                    'footage_to_restore': footage_used,
                                    'pieces': pieces,
                                    'size': size,
                                    'original_log': log
                                })
                                
                                st.write(f"• **{item_id}**: +{footage_used:.2f} ft ({pieces} pcs of {size})")
                            
                            if items_to_restore:
                                total_to_restore = sum(item['footage_to_restore'] for item in items_to_restore)
                                st.markdown(f"**Total Footage to Restore:** {total_to_restore:.2f} ft")
                                
                                st.markdown("---")
                                
                                reversal_reason = st.text_input(
                                    "Reason for Reversal *",
                                    placeholder="e.g. Wrong material used, customer cancelled, data entry error",
                                    key="reversal_reason"
                                )
                                
                                confirm_reversal = st.checkbox(
                                    f"I confirm I want to reverse order {selected['order_num']} and restore {total_to_restore:.2f} ft",
                                    key="confirm_reversal"
                                )
                                
                                if st.button("🔄 Reverse This Order", type="primary", use_container_width=True):
                                    if not reversal_reason.strip():
                                        st.error("⚠️ Please provide a reason for the reversal")
                                    elif not confirm_reversal:
                                        st.error("⚠️ Please confirm the reversal")
                                    else:
                                        with st.spinner("Reversing production order..."):
                                            try:
                                                success_count = 0
                                                
                                                for item in items_to_restore:
                                                    inv_response = supabase.table("inventory").select("Footage, Status").eq("Item_ID", item['item_id']).execute()
                                                    
                                                    if inv_response.data:
                                                        current_footage = float(inv_response.data[0]['Footage'])
                                                        new_footage = current_footage + item['footage_to_restore']
                                                        
                                                        # Update inventory - also restore status if it was depleted
                                                        update_data = {"Footage": new_footage}
                                                        if inv_response.data[0].get('Status') == 'Depleted':
                                                            update_data["Status"] = "Active"
                                                        
                                                        supabase.table("inventory").update(update_data).eq("Item_ID", item['item_id']).execute()
                                                        
                                                        # Log the reversal with MST timestamp
                                                        log_entry = {
                                                            "Item_ID": item['item_id'],
                                                            "Action": "Production Reversal",
                                                            "User": st.session_state.get('username', 'Admin'),
                                                            "Timestamp": get_mst_timestamp(),
                                                            "Details": f"Reversed order {selected['order_num']}: Restored {item['footage_to_restore']:.2f} ft ({item['pieces']} pcs of {item['size']}). Reason: {reversal_reason}. Previous: {current_footage:.2f} ft → New: {new_footage:.2f} ft"
                                                        }
                                                        supabase.table("audit_log").insert(log_entry).execute()
                                                        
                                                        success_count += 1
                                                    else:
                                                        st.warning(f"⚠️ Item {item['item_id']} not found - skipped")
                                                
                                                # Log the overall reversal
                                                summary_log = {
                                                    "Item_ID": selected['order_num'],
                                                    "Action": "Order Reversed",
                                                    "User": st.session_state.get('username', 'Admin'),
                                                    "Timestamp": get_mst_timestamp(),
                                                    "Details": f"Reversed production order {selected['order_num']} for {selected['client']}. Restored {total_to_restore:.2f} ft across {success_count} items. Reason: {reversal_reason}"
                                                }
                                                supabase.table("audit_log").insert(summary_log).execute()
                                                
                                                st.success(f"✅ Successfully reversed order {selected['order_num']}!")
                                                st.success(f"📦 Restored {total_to_restore:.2f} ft to {success_count} item(s)")
                                                st.balloons()
                                                
                                                st.cache_data.clear()
                                                st.session_state.force_refresh = True
                                                time.sleep(1)
                                                st.rerun()
                                                
                                            except Exception as e:
                                                st.error(f"❌ Error reversing order: {e}")
                            else:
                                st.warning("⚠️ Could not parse deduction details from this order")
        
        except Exception as e:
            st.error(f"Error loading production orders: {e}")
            
with tab3:
    st.subheader("🛒 Stock Picking & Sales")
    st.caption("Perform instant stock removals. Updates sync across all devices in real-time.")

    # ── Safety check for empty database ─────────────────────────────────────────
    if df is None or df.empty:
        st.info("📦 No inventory available for picking. Please add items in the 'Manage' tab first.")
        st.markdown("---")
        st.markdown("### Getting Started")
        st.markdown("""
        1. Go to the **Manage** tab
        2. Receive your first inventory items
        3. Return here to start picking orders
        """)
    else:
        # ── Local helper function ───────────────────────────────────────────────────
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
            
            return cat.strip().title() + 's' if not cat.strip().endswith(('s', 'wool')) else cat.strip().title()

        # ── Work on a local copy ────────────────────────────────────────────────────
        pick_df = df.copy()
        if 'Category' in pick_df.columns and not pick_df.empty:
            pick_df['Category'] = pick_df['Category'].apply(normalize_pick_category)
        
        # Add Roll Type for RPR detection
        def get_roll_type(row):
            if row.get('Category') != 'Rolls':
                return None
            if 'RPR' in str(row.get('Item_ID', '')).upper() or 'RPR' in str(row.get('Material', '')).upper():
                return 'RPR'
            return 'Regular'
        
        pick_df['Roll_Type'] = pick_df.apply(get_roll_type, axis=1)

        category_options = ["Coils", "Rolls", "Fab Straps", "Elbows", "Mineral Wool"]
        
        # Filter to only show categories that exist in inventory
        available_categories = [cat for cat in category_options if cat in pick_df['Category'].unique()]
        if not available_categories:
            available_categories = category_options  # Fallback
        
        # ── Initialize Session State for Cart ───────────────────────────────────────
        if 'pick_cart' not in st.session_state:
            st.session_state.pick_cart = []
        
        if 'show_back_order' not in st.session_state:
            st.session_state.show_back_order = False
            st.session_state.back_order_items = []
            st.session_state.last_customer = ""
            st.session_state.last_sales_order = ""

        # ── Order Information (Outside form so it persists) ─────────────────────────
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
                key="pick_customer_persist",
                label_visibility="collapsed"
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
                key="pick_sales_order_persist",
                label_visibility="collapsed"
            )
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.divider()

        # ── Add Items to Cart ───────────────────────────────────────────────────────
        st.markdown("#### ➕ Add Items to Order")
        
        # Category selection
        pick_cat = st.selectbox(
            "📦 Category",
            available_categories,
            key="pick_cat_add"
        )
        
        # Filter by category
        filtered_df = pick_df[pick_df['Category'] == pick_cat].copy() if not pick_df.empty else pd.DataFrame()
        filtered_df = filtered_df[filtered_df['Footage'] > 0]  # Only show items with stock
        
        # ════════════════════════════════════════════════════════════════════════════
        # COILS PICKING
        # ════════════════════════════════════════════════════════════════════════════
        if pick_cat == "Coils":
            if filtered_df.empty:
                st.warning("⚠️ No coils in stock")
            else:
                # Extract coil properties for filtering
                import re
                
                def extract_coil_props(row):
                    mat = str(row['Material']).lower()
                    
                    # Gauge
                    gauge_match = re.search(r'\.(\d{3})', str(row['Material']))
                    gauge = f".{gauge_match.group(1)}" if gauge_match else "Unknown"
                    
                    # Texture
                    texture = "Smooth" if "smooth" in mat else ("Stucco" if "stucco" in mat else "Other")
                    
                    # Metal
                    metal = "Aluminum" if "aluminum" in mat else ("Stainless Steel" if "stainless" in mat else "Other")
                    
                    return pd.Series({'Gauge': gauge, 'Texture': texture, 'Metal': metal})
                
                filtered_df[['Gauge', 'Texture', 'Metal']] = filtered_df.apply(extract_coil_props, axis=1)
                
                # Filters
                col1, col2, col3 = st.columns(3)
                
                with col1:
                    texture_opts = ["All"] + sorted(filtered_df['Texture'].unique().tolist())
                    sel_texture = st.selectbox("🎨 Texture", texture_opts, key="coil_texture_filter")
                
                with col2:
                    metal_opts = ["All"] + sorted(filtered_df['Metal'].unique().tolist())
                    sel_metal = st.selectbox("🔩 Metal", metal_opts, key="coil_metal_filter")
                
                with col3:
                    gauge_opts = ["All"] + sorted(filtered_df['Gauge'].unique().tolist())
                    sel_gauge = st.selectbox("📏 Gauge", gauge_opts, key="coil_gauge_filter")
                
                # Apply filters
                display_df = filtered_df.copy()
                if sel_texture != "All":
                    display_df = display_df[display_df['Texture'] == sel_texture]
                if sel_metal != "All":
                    display_df = display_df[display_df['Metal'] == sel_metal]
                if sel_gauge != "All":
                    display_df = display_df[display_df['Gauge'] == sel_gauge]
                
                if display_df.empty:
                    st.warning("No coils match the selected filters")
                else:
                    # Show available coils
                    st.markdown(f"**{len(display_df)} coil(s) available:**")
                    st.dataframe(
                        display_df[['Item_ID', 'Material', 'Footage', 'Location']].sort_values('Footage', ascending=False),
                        use_container_width=True,
                        hide_index=True,
                        height=200
                    )
                    
                    st.markdown("---")
                    
                    # Pick form
                    with st.form("pick_coil_form", clear_on_submit=True):
                        # Select specific coil
                        coil_options = [f"{row['Item_ID']} | {row['Material'][:35]}... | {row['Footage']:.0f} ft" 
                                       for _, row in display_df.iterrows()]
                        
                        selected_coil = st.selectbox("🎯 Select Coil", coil_options, key="coil_select")
                        
                        if selected_coil:
                            coil_id = selected_coil.split(" | ")[0]
                            coil_data = display_df[display_df['Item_ID'] == coil_id].iloc[0]
                            current_footage = float(coil_data['Footage'])
                            
                            col1, col2 = st.columns(2)
                            
                            with col1:
                                pick_footage = st.number_input(
                                    "📏 Footage to Pick",
                                    min_value=1.0,
                                    max_value=current_footage,
                                    value=min(100.0, current_footage),
                                    step=10.0,
                                    key="coil_pick_footage"
                                )
                            
                            with col2:
                                remaining = current_footage - pick_footage
                                st.metric("Remaining After Pick", f"{remaining:,.0f} ft")
                                if remaining < 100:
                                    st.caption("⚠️ Low stock warning")
                        
                        add_coil = st.form_submit_button("🛒 Add Coil to Cart", use_container_width=True)
                    
                    if add_coil and selected_coil:
                        coil_id = selected_coil.split(" | ")[0]
                        coil_data = display_df[display_df['Item_ID'] == coil_id].iloc[0]
                        
                        st.session_state.pick_cart.append({
                            'category': 'Coils',
                            'material': coil_data['Material'],
                            'item_id': coil_id,
                            'quantity': pick_footage,
                            'unit': 'ft',
                            'available': coil_data['Footage'],
                            'shortfall': 0,
                            'pick_type': 'partial'  # Indicates we're picking footage, not whole coil
                        })
                        st.success(f"✅ Added {pick_footage:.0f} ft from Coil {coil_id}")
                        st.rerun()
        
        # ════════════════════════════════════════════════════════════════════════════
        # ROLLS PICKING
        # ════════════════════════════════════════════════════════════════════════════
        elif pick_cat == "Rolls":
            if filtered_df.empty:
                st.warning("⚠️ No rolls in stock")
            else:
                # Extract roll properties
                import re
                
                def extract_roll_props(row):
                    mat = str(row['Material']).lower()
                    
                    gauge_match = re.search(r'\.(\d{3})', str(row['Material']))
                    gauge = f".{gauge_match.group(1)}" if gauge_match else "Unknown"
                    
                    texture = "Smooth" if "smooth" in mat else ("Stucco" if "stucco" in mat else "Other")
                    metal = "Aluminum" if "aluminum" in mat else ("Stainless Steel" if "stainless" in mat else "Other")
                    
                    # RPR detection
                    roll_type = "RPR" if ("rpr" in mat or "rpr" in str(row['Item_ID']).lower()) else "Regular"
                    
                    return pd.Series({'Gauge': gauge, 'Texture': texture, 'Metal': metal, 'Roll_Type': roll_type})
                
                filtered_df[['Gauge', 'Texture', 'Metal', 'Roll_Type']] = filtered_df.apply(extract_roll_props, axis=1)
                
                # Filters
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    roll_type_opts = ["All"] + sorted(filtered_df['Roll_Type'].unique().tolist())
                    sel_roll_type = st.selectbox("🗞️ Type", roll_type_opts, key="roll_type_filter")
                
                with col2:
                    texture_opts = ["All"] + sorted(filtered_df['Texture'].unique().tolist())
                    sel_texture = st.selectbox("🎨 Texture", texture_opts, key="roll_texture_filter")
                
                with col3:
                    metal_opts = ["All"] + sorted(filtered_df['Metal'].unique().tolist())
                    sel_metal = st.selectbox("🔩 Metal", metal_opts, key="roll_metal_filter")
                
                with col4:
                    gauge_opts = ["All"] + sorted(filtered_df['Gauge'].unique().tolist())
                    sel_gauge = st.selectbox("📏 Gauge", gauge_opts, key="roll_gauge_filter")
                
                # Apply filters
                display_df = filtered_df.copy()
                if sel_roll_type != "All":
                    display_df = display_df[display_df['Roll_Type'] == sel_roll_type]
                if sel_texture != "All":
                    display_df = display_df[display_df['Texture'] == sel_texture]
                if sel_metal != "All":
                    display_df = display_df[display_df['Metal'] == sel_metal]
                if sel_gauge != "All":
                    display_df = display_df[display_df['Gauge'] == sel_gauge]
                
                if display_df.empty:
                    st.warning("No rolls match the selected filters")
                else:
                    st.markdown(f"**{len(display_df)} roll(s) available:**")
                    st.dataframe(
                        display_df[['Item_ID', 'Roll_Type', 'Material', 'Footage', 'Location']].sort_values(['Roll_Type', 'Material']),
                        use_container_width=True,
                        hide_index=True,
                        height=200
                    )
                    
                    st.markdown("---")
                    
                    # Pick mode selection
                    pick_mode = st.radio(
                        "Pick Mode",
                        ["Pick entire roll(s)", "Pick partial footage"],
                        horizontal=True,
                        key="roll_pick_mode"
                    )
                    
                    if pick_mode == "Pick entire roll(s)":
                        # Multi-select for whole rolls
                        roll_options = [f"{row['Item_ID']} | {row['Roll_Type']} | {row['Footage']:.0f} ft" 
                                       for _, row in display_df.iterrows()]
                        
                        selected_rolls = st.multiselect(
                            "🎯 Select Roll(s) to Pick",
                            roll_options,
                            key="roll_multi_select"
                        )
                        
                        if selected_rolls:
                            total_footage = 0
                            for roll_str in selected_rolls:
                                roll_id = roll_str.split(" | ")[0]
                                roll_footage = display_df[display_df['Item_ID'] == roll_id]['Footage'].values[0]
                                total_footage += roll_footage
                            
                            st.info(f"📦 Selected: {len(selected_rolls)} roll(s) = **{total_footage:,.0f} ft** total")
                            
                            if st.button("🛒 Add Selected Rolls to Cart", type="primary", use_container_width=True):
                                for roll_str in selected_rolls:
                                    roll_id = roll_str.split(" | ")[0]
                                    roll_data = display_df[display_df['Item_ID'] == roll_id].iloc[0]
                                    
                                    st.session_state.pick_cart.append({
                                        'category': 'Rolls',
                                        'material': roll_data['Material'],
                                        'item_id': roll_id,
                                        'quantity': roll_data['Footage'],
                                        'unit': 'ft (whole roll)',
                                        'available': roll_data['Footage'],
                                        'shortfall': 0,
                                        'pick_type': 'whole',
                                        'roll_type': roll_data['Roll_Type']
                                    })
                                
                                st.success(f"✅ Added {len(selected_rolls)} roll(s) to cart")
                                st.rerun()
                    
                    else:  # Partial footage
                        with st.form("pick_roll_partial_form", clear_on_submit=True):
                            roll_options = [f"{row['Item_ID']} | {row['Roll_Type']} | {row['Material'][:30]}... | {row['Footage']:.0f} ft" 
                                           for _, row in display_df.iterrows()]
                            
                            selected_roll = st.selectbox("🎯 Select Roll", roll_options, key="roll_single_select")
                            
                            if selected_roll:
                                roll_id = selected_roll.split(" | ")[0]
                                roll_data = display_df[display_df['Item_ID'] == roll_id].iloc[0]
                                current_footage = float(roll_data['Footage'])
                                
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    pick_footage = st.number_input(
                                        "📏 Footage to Pick",
                                        min_value=1.0,
                                        max_value=current_footage,
                                        value=min(50.0, current_footage),
                                        step=5.0,
                                        key="roll_pick_footage"
                                    )
                                
                                with col2:
                                    remaining = current_footage - pick_footage
                                    st.metric("Remaining", f"{remaining:,.0f} ft")
                            
                            add_roll = st.form_submit_button("🛒 Add to Cart", use_container_width=True)
                        
                        if add_roll and selected_roll:
                            roll_id = selected_roll.split(" | ")[0]
                            roll_data = display_df[display_df['Item_ID'] == roll_id].iloc[0]
                            
                            st.session_state.pick_cart.append({
                                'category': 'Rolls',
                                'material': roll_data['Material'],
                                'item_id': roll_id,
                                'quantity': pick_footage,
                                'unit': 'ft',
                                'available': roll_data['Footage'],
                                'shortfall': 0,
                                'pick_type': 'partial',
                                'roll_type': roll_data.get('Roll_Type', 'Regular')
                            })
                            st.success(f"✅ Added {pick_footage:.0f} ft from Roll {roll_id}")
                            st.rerun()
        
        # ════════════════════════════════════════════════════════════════════════════
        # OTHER CATEGORIES (Fab Straps, Elbows, Mineral Wool, etc.)
        # ════════════════════════════════════════════════════════════════════════════
        else:
            if filtered_df.empty:
                st.warning(f"⚠️ No {pick_cat.lower()} in stock")
            else:
                st.markdown(f"**{len(filtered_df)} item(s) available:**")
                st.dataframe(
                    filtered_df[['Item_ID', 'Material', 'Footage', 'Location']].sort_values('Material'),
                    use_container_width=True,
                    hide_index=True,
                    height=200
                )
                
                st.markdown("---")
                
                with st.form("pick_other_form", clear_on_submit=True):
                    # Material selection
                    mat_options = sorted(filtered_df['Material'].unique().tolist())
                    selected_mat = st.selectbox("📦 Select Material", mat_options, key="other_mat_select")
                    
                    if selected_mat:
                        mat_data = filtered_df[filtered_df['Material'] == selected_mat].iloc[0]
                        current_qty = int(mat_data['Footage'])
                        
                        col1, col2 = st.columns(2)
                        
                        with col1:
                            pick_qty = st.number_input(
                                "🔢 Quantity to Pick",
                                min_value=1,
                                max_value=current_qty,
                                value=1,
                                step=1,
                                key="other_pick_qty"
                            )
                        
                        with col2:
                            remaining = current_qty - pick_qty
                            st.metric("Remaining", f"{remaining} pcs")
                            if remaining < 5:
                                st.caption("⚠️ Low stock warning")
                    
                    add_other = st.form_submit_button("🛒 Add to Cart", use_container_width=True)
                
                if add_other and selected_mat:
                    mat_data = filtered_df[filtered_df['Material'] == selected_mat].iloc[0]
                    current_qty = int(mat_data['Footage'])
                    
                    available = min(current_qty, pick_qty)
                    shortfall = max(0, pick_qty - current_qty)
                    
                    st.session_state.pick_cart.append({
                        'category': pick_cat,
                        'material': selected_mat,
                        'item_id': mat_data['Item_ID'],
                        'quantity': pick_qty,
                        'unit': 'pcs',
                        'available': available,
                        'shortfall': shortfall,
                        'pick_type': 'quantity'
                    })
                    
                    if shortfall > 0:
                        st.warning(f"⚠️ Added: {available} available, {shortfall} back ordered")
                    else:
                        st.success(f"✅ Added {pick_qty} × {selected_mat}")
                    st.rerun()

        # ════════════════════════════════════════════════════════════════════════════
        # DISPLAY CART
        # ════════════════════════════════════════════════════════════════════════════
        if st.session_state.pick_cart:
            st.markdown("---")
            st.markdown("#### 🛒 Current Order")
            
            total_coil_footage = 0
            total_roll_footage = 0
            total_other_items = 0
            
            for idx, item in enumerate(st.session_state.pick_cart):
                col_item, col_remove = st.columns([5, 1])
                
                with col_item:
                    status = ""
                    if item.get('shortfall', 0) > 0:
                        status = f" ⚠️ ({item['available']} avail, {item['shortfall']} backorder)"
                    
                    if item['category'] == 'Coils':
                        st.markdown(f"**🔄 Coil** - {item['material'][:40]}...")
                        st.caption(f"ID: {item['item_id']} | Pick: **{item['quantity']:.0f} ft**{status}")
                        total_coil_footage += item['quantity']
                    
                    elif item['category'] == 'Rolls':
                        roll_type_icon = "🔷" if item.get('roll_type') == 'RPR' else "📜"
                        pick_label = "Whole Roll" if item.get('pick_type') == 'whole' else f"{item['quantity']:.0f} ft"
                        st.markdown(f"**{roll_type_icon} {item.get('roll_type', 'Regular')} Roll** - {item['material'][:35]}...")
                        st.caption(f"ID: {item['item_id']} | Pick: **{pick_label}**{status}")
                        total_roll_footage += item['quantity']
                    
                    else:
                        st.markdown(f"**📦 {item['category']}** - {item['material'][:40]}...")
                        st.caption(f"Qty: **{item['quantity']} {item.get('unit', 'pcs')}**{status}")
                        total_other_items += item['quantity']
                
                with col_remove:
                    if st.button("🗑️", key=f"remove_{idx}", help="Remove from cart"):
                        st.session_state.pick_cart.pop(idx)
                        st.rerun()
            
            # Cart summary
            st.markdown("---")
            sum_col1, sum_col2, sum_col3 = st.columns(3)
            if total_coil_footage > 0:
                sum_col1.metric("Coil Footage", f"{total_coil_footage:,.0f} ft")
            if total_roll_footage > 0:
                sum_col2.metric("Roll Footage", f"{total_roll_footage:,.0f} ft")
            if total_other_items > 0:
                sum_col3.metric("Other Items", f"{total_other_items:,}")
            
            st.divider()
            
            # Authorized By
            picker_name = st.text_input(
                "👤 Authorized By",
                value=st.session_state.get("username", "Admin"),
                key="pick_authorized"
            )
            
            col_process, col_clear = st.columns(2)
            
            with col_process:
                if st.button("📤 Process Order", type="primary", use_container_width=True):
                    if not customer.strip():
                        st.error("⚠️ Please enter Customer / Job Name.")
                    elif not sales_order.strip():
                        st.error("⚠️ Please enter Sales Order Number.")
                    elif not picker_name.strip():
                        st.error("⚠️ Please enter Authorized By name.")
                    else:
                        st.session_state.last_customer = customer.strip()
                        st.session_state.last_sales_order = sales_order.strip()
                        st.session_state.back_order_items = []
                        
                        all_success = True
                        
                        with st.spinner("Processing order..."):
                            for item in st.session_state.pick_cart:
                                try:
                                    # Get current stock from database
                                    response = supabase.table("inventory").select("Footage").eq("Item_ID", item['item_id']).execute()
                                    
                                    if response.data:
                                        current_stock = float(response.data[0]['Footage'])
                                        
                                        if item['pick_type'] == 'whole':
                                            # Remove entire roll/coil (set to 0 or delete)
                                            new_footage = 0
                                            action_desc = f"Picked whole {item['category'][:-1]} ({item['quantity']:.0f} ft)"
                                        else:
                                            # Partial pick
                                            new_footage = current_stock - item['quantity']
                                            if new_footage < 0:
                                                new_footage = 0
                                            action_desc = f"Picked {item['quantity']:.0f} {item.get('unit', 'units')} from {item['category']}"
                                        
                                        # Update database
                                        supabase.table("inventory").update({
                                            "Footage": new_footage
                                        }).eq("Item_ID", item['item_id']).execute()
                                        
                                        # Log the pick
                                        log_entry = {
                                            "Item_ID": item['item_id'],
                                            "Action": f"Stock Pick - {item['category']}",
                                            "User": picker_name,
                                            "Timestamp": datetime.now().isoformat(),
                                            "Details": f"{action_desc} for {customer} (SO: {sales_order}). Material: {item['material'][:40]}. Remaining: {new_footage:.0f}"
                                        }
                                        supabase.table("audit_log").insert(log_entry).execute()
                                        
                                        # Track back orders
                                        if item.get('shortfall', 0) > 0:
                                            st.session_state.back_order_items.append(item)
                                    else:
                                        st.warning(f"Item {item['item_id']} not found")
                                        all_success = False
                                        
                                except Exception as e:
                                    st.error(f"Error processing {item['item_id']}: {e}")
                                    all_success = False
                        
                        if all_success:
                            st.success(f"✅ Order processed for {customer} ({sales_order})!")
                            
                            if st.session_state.back_order_items:
                                st.session_state.show_back_order = True
                            else:
                                st.balloons()
                                st.toast("Order complete! 🎉", icon="🎉")
                                st.session_state.pick_cart = []
                                st.cache_data.clear()
                                st.session_state.force_refresh = True
                                time.sleep(1)
                                st.rerun()
                        else:
                            st.error("Some items failed. Check above for details.")
            
            with col_clear:
                if st.button("🗑️ Clear Cart", use_container_width=True):
                    st.session_state.pick_cart = []
                    st.rerun()

        # ════════════════════════════════════════════════════════════════════════════
        # BACK ORDER MANAGEMENT
        # ════════════════════════════════════════════════════════════════════════════
        if not st.session_state.pick_cart and not st.session_state.show_back_order:
            st.markdown("---")
            st.markdown("#### 📦 Back Order Management")
            
            try:
                # Fetch all back orders (not just open)
                response = supabase.table("back_orders").select("*").order("id", desc=True).execute()
                all_back_orders = response.data if response.data else []
                
                # Separate by status
                open_orders = [bo for bo in all_back_orders if bo.get('status') == 'Open']
                fulfilled_orders = [bo for bo in all_back_orders if bo.get('status') == 'Fulfilled']
                cancelled_orders = [bo for bo in all_back_orders if bo.get('status') == 'Cancelled']
                
                # Summary metrics
                metric_col1, metric_col2, metric_col3 = st.columns(3)
                metric_col1.metric("🔴 Open", len(open_orders))
                metric_col2.metric("✅ Fulfilled", len(fulfilled_orders))
                metric_col3.metric("❌ Cancelled", len(cancelled_orders))
                
                # Tabs for different views
                bo_tab1, bo_tab2, bo_tab3 = st.tabs(["🔴 Open Orders", "✅ Fulfilled", "📊 All Orders"])
                
                # ── OPEN ORDERS TAB ─────────────────────────────────────────────────
                with bo_tab1:
                    if not open_orders:
                        st.success("✅ No open back orders!")
                    else:
                        st.warning(f"📋 **{len(open_orders)}** order(s) pending fulfillment")
                        
                        for bo in open_orders:
                            bo_id = bo.get('id')
                            
                            with st.expander(f"📦 {bo.get('material', 'Unknown')[:40]}... - {bo.get('shortfall_quantity')} units | {bo.get('client_name')}"):
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    st.markdown(f"""
                                        **Material:** {bo.get('material', 'N/A')}  
                                        **Quantity Needed:** {bo.get('shortfall_quantity', 0)}  
                                        **Customer:** {bo.get('client_name', 'N/A')}  
                                        **Sales Order:** {bo.get('order_number', 'N/A')}
                                    """)
                                    
                                    if bo.get('note'):
                                        st.info(f"📝 Note: {bo.get('note')}")
                                
                                with col2:
                                    st.markdown("**Actions:**")
                                    
                                    # Fulfill button
                                    if st.button("✅ Mark as Fulfilled", key=f"fulfill_{bo_id}", type="primary", use_container_width=True):
                                        try:
                                            supabase.table("back_orders").update({
                                                "status": "Fulfilled",
                                                "fulfilled_date": datetime.now().isoformat(),
                                                "fulfilled_by": st.session_state.get('username', 'Admin')
                                            }).eq("id", bo_id).execute()
                                            
                                            # Log it
                                            log_entry = {
                                                "Item_ID": f"BO-{bo_id}",
                                                "Action": "Back Order Fulfilled",
                                                "User": st.session_state.get('username', 'Admin'),
                                                "Timestamp": datetime.now().isoformat(),
                                                "Details": f"Fulfilled back order for {bo.get('shortfall_quantity')} × {bo.get('material', 'N/A')[:30]} for {bo.get('client_name')} (SO: {bo.get('order_number')})"
                                            }
                                            supabase.table("audit_log").insert(log_entry).execute()
                                            
                                            st.success("✅ Marked as fulfilled!")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Failed: {e}")
                                    
                                    # Partial fulfill
                                    with st.form(f"partial_fulfill_{bo_id}"):
                                        st.markdown("**Partial Fulfillment:**")
                                        partial_qty = st.number_input(
                                            "Quantity fulfilled",
                                            min_value=1,
                                            max_value=int(bo.get('shortfall_quantity', 1)),
                                            value=1,
                                            key=f"partial_qty_{bo_id}"
                                        )
                                        
                                        if st.form_submit_button("📦 Partial Fulfill", use_container_width=True):
                                            try:
                                                remaining = int(bo.get('shortfall_quantity', 0)) - partial_qty
                                                
                                                if remaining <= 0:
                                                    # Fully fulfilled
                                                    supabase.table("back_orders").update({
                                                        "status": "Fulfilled",
                                                        "shortfall_quantity": 0,
                                                        "fulfilled_date": datetime.now().isoformat(),
                                                        "fulfilled_by": st.session_state.get('username', 'Admin')
                                                    }).eq("id", bo_id).execute()
                                                    st.success("✅ Fully fulfilled!")
                                                else:
                                                    # Partial - update remaining quantity
                                                    supabase.table("back_orders").update({
                                                        "shortfall_quantity": remaining
                                                    }).eq("id", bo_id).execute()
                                                    st.success(f"✅ Fulfilled {partial_qty}. Remaining: {remaining}")
                                                
                                                # Log it
                                                log_entry = {
                                                    "Item_ID": f"BO-{bo_id}",
                                                    "Action": "Back Order Partial Fulfill",
                                                    "User": st.session_state.get('username', 'Admin'),
                                                    "Timestamp": datetime.now().isoformat(),
                                                    "Details": f"Fulfilled {partial_qty} of {bo.get('shortfall_quantity')} × {bo.get('material', 'N/A')[:30]}. Remaining: {remaining}"
                                                }
                                                supabase.table("audit_log").insert(log_entry).execute()
                                                
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"Failed: {e}")
                                    
                                    # Cancel button
                                    if st.button("❌ Cancel Order", key=f"cancel_{bo_id}", use_container_width=True):
                                        try:
                                            supabase.table("back_orders").update({
                                                "status": "Cancelled",
                                                "cancelled_date": datetime.now().isoformat(),
                                                "cancelled_by": st.session_state.get('username', 'Admin')
                                            }).eq("id", bo_id).execute()
                                            
                                            # Log it
                                            log_entry = {
                                                "Item_ID": f"BO-{bo_id}",
                                                "Action": "Back Order Cancelled",
                                                "User": st.session_state.get('username', 'Admin'),
                                                "Timestamp": datetime.now().isoformat(),
                                                "Details": f"Cancelled back order for {bo.get('shortfall_quantity')} × {bo.get('material', 'N/A')[:30]} for {bo.get('client_name')}"
                                            }
                                            supabase.table("audit_log").insert(log_entry).execute()
                                            
                                            st.success("❌ Order cancelled")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Failed: {e}")
                        
                        # Bulk actions
                        st.markdown("---")
                        st.markdown("**Bulk Actions:**")
                        
                        col_bulk1, col_bulk2 = st.columns(2)
                        
                        with col_bulk1:
                            if st.button("✅ Fulfill ALL Open Orders", use_container_width=True):
                                try:
                                    for bo in open_orders:
                                        supabase.table("back_orders").update({
                                            "status": "Fulfilled",
                                            "fulfilled_date": datetime.now().isoformat(),
                                            "fulfilled_by": st.session_state.get('username', 'Admin')
                                        }).eq("id", bo.get('id')).execute()
                                    
                                    # Log bulk action
                                    log_entry = {
                                        "Item_ID": "BULK",
                                        "Action": "Bulk Back Order Fulfillment",
                                        "User": st.session_state.get('username', 'Admin'),
                                        "Timestamp": datetime.now().isoformat(),
                                        "Details": f"Fulfilled {len(open_orders)} back orders in bulk"
                                    }
                                    supabase.table("audit_log").insert(log_entry).execute()
                                    
                                    st.success(f"✅ Fulfilled {len(open_orders)} orders!")
                                    st.balloons()
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Failed: {e}")
                        
                        with col_bulk2:
                            if st.button("❌ Cancel ALL Open Orders", use_container_width=True):
                                confirm = st.checkbox("I confirm I want to cancel all open orders", key="confirm_cancel_all")
                                if confirm:
                                    try:
                                        for bo in open_orders:
                                            supabase.table("back_orders").update({
                                                "status": "Cancelled",
                                                "cancelled_date": datetime.now().isoformat(),
                                                "cancelled_by": st.session_state.get('username', 'Admin')
                                            }).eq("id", bo.get('id')).execute()
                                        
                                        st.success(f"❌ Cancelled {len(open_orders)} orders")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed: {e}")
                
                # ── FULFILLED ORDERS TAB ────────────────────────────────────────────
                with bo_tab2:
                    if not fulfilled_orders:
                        st.info("📭 No fulfilled orders yet")
                    else:
                        st.success(f"✅ **{len(fulfilled_orders)}** order(s) fulfilled")
                        
                        # Create dataframe for display
                        fulfilled_df = pd.DataFrame(fulfilled_orders)
                        
                        # Select columns to display
                        display_cols = ['material', 'shortfall_quantity', 'client_name', 'order_number', 'fulfilled_date', 'fulfilled_by']
                        available_cols = [col for col in display_cols if col in fulfilled_df.columns]
                        
                        if available_cols:
                            st.dataframe(
                                fulfilled_df[available_cols].rename(columns={
                                    'material': 'Material',
                                    'shortfall_quantity': 'Qty',
                                    'client_name': 'Customer',
                                    'order_number': 'SO #',
                                    'fulfilled_date': 'Fulfilled Date',
                                    'fulfilled_by': 'Fulfilled By'
                                }),
                                use_container_width=True,
                                hide_index=True
                            )
                        
                        # Option to reopen
                        st.markdown("---")
                        st.markdown("**Reopen a fulfilled order:**")
                        
                        reopen_options = [f"{bo.get('id')} - {bo.get('material', 'N/A')[:30]} ({bo.get('client_name')})" for bo in fulfilled_orders]
                        selected_reopen = st.selectbox("Select order to reopen", ["-- Select --"] + reopen_options, key="reopen_select")
                        
                        if selected_reopen != "-- Select --":
                            reopen_id = int(selected_reopen.split(" - ")[0])
                            
                            col1, col2 = st.columns(2)
                            with col1:
                                reopen_qty = st.number_input("Quantity to reopen", min_value=1, value=1, key="reopen_qty")
                            
                            with col2:
                                if st.button("🔄 Reopen Order", type="primary", use_container_width=True):
                                    try:
                                        supabase.table("back_orders").update({
                                            "status": "Open",
                                            "shortfall_quantity": reopen_qty,
                                            "fulfilled_date": None,
                                            "fulfilled_by": None
                                        }).eq("id", reopen_id).execute()
                                        
                                        st.success("🔄 Order reopened!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed: {e}")
                
                # ── ALL ORDERS TAB ──────────────────────────────────────────────────
                with bo_tab3:
                    if not all_back_orders:
                        st.info("📭 No back orders in system")
                    else:
                        st.markdown(f"**Total:** {len(all_back_orders)} back order(s) in history")
                        
                        # Filter by status
                        status_filter = st.multiselect(
                            "Filter by Status",
                            ["Open", "Fulfilled", "Cancelled"],
                            default=["Open", "Fulfilled", "Cancelled"],
                            key="bo_status_filter"
                        )
                        
                        filtered_bo = [bo for bo in all_back_orders if bo.get('status') in status_filter]
                        
                        if filtered_bo:
                            bo_df = pd.DataFrame(filtered_bo)
                            
                            display_cols = ['id', 'status', 'material', 'shortfall_quantity', 'client_name', 'order_number', 'note']
                            available_cols = [col for col in display_cols if col in bo_df.columns]
                            
                            st.dataframe(
                                bo_df[available_cols].rename(columns={
                                    'id': 'ID',
                                    'status': 'Status',
                                    'material': 'Material',
                                    'shortfall_quantity': 'Qty',
                                    'client_name': 'Customer',
                                    'order_number': 'SO #',
                                    'note': 'Notes'
                                }),
                                use_container_width=True,
                                hide_index=True
                            )
                        
                        # Delete old records
                        st.markdown("---")
                        st.markdown("**🗑️ Cleanup:**")
                        
                        with st.expander("Delete old fulfilled/cancelled orders"):
                            st.warning("⚠️ This will permanently delete records from the database")
                            
                            delete_status = st.multiselect(
                                "Delete orders with status:",
                                ["Fulfilled", "Cancelled"],
                                key="delete_status"
                            )
                            
                            if delete_status:
                                to_delete = [bo for bo in all_back_orders if bo.get('status') in delete_status]
                                st.write(f"This will delete **{len(to_delete)}** record(s)")
                                
                                confirm_delete = st.checkbox(f"I confirm I want to delete {len(to_delete)} records", key="confirm_delete_bo")
                                
                                if confirm_delete:
                                    if st.button("🗑️ Delete Records", type="primary"):
                                        try:
                                            for status in delete_status:
                                                supabase.table("back_orders").delete().eq("status", status).execute()
                                            
                                            st.success(f"🗑️ Deleted {len(to_delete)} records")
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"Failed: {e}")
                
                # ── GENERATE REPORT ─────────────────────────────────────────────────
                st.markdown("---")
                if open_orders and st.button("📥 Generate PDF Report", type="secondary"):
                    current_time = datetime.now().strftime('%B %d, %Y at %I:%M %p')
                    
                    html_content = f"""
                    <!DOCTYPE html>
                    <html>
                    <head>
                        <meta charset="UTF-8">
                        <title>Back Order Report</title>
                        <style>
                            @page {{ size: A4; margin: 2cm; }}
                            body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 40px; background: white; color: #333; }}
                            .header {{ text-align: center; border-bottom: 4px solid #2563eb; padding-bottom: 20px; margin-bottom: 30px; }}
                            .header h1 {{ margin: 0; color: #1e40af; font-size: 32px; font-weight: 700; }}
                            .header .subtitle {{ color: #64748b; font-size: 14px; margin-top: 8px; }}
                            .meta-info {{ background: #f1f5f9; padding: 15px 20px; border-radius: 8px; margin-bottom: 30px; display: flex; justify-content: space-between; }}
                            .order-card {{ border: 2px solid #e2e8f0; border-radius: 10px; padding: 20px; margin-bottom: 20px; background: #ffffff; page-break-inside: avoid; }}
                            .order-header {{ background: linear-gradient(135deg, #dc2626 0%, #b91c1c 100%); color: white; padding: 12px 16px; border-radius: 6px; margin: -20px -20px 15px -20px; }}
                            .detail-row {{ padding: 8px 0; border-bottom: 1px solid #f1f5f9; }}
                            .detail-label {{ color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; }}
                            .detail-value {{ color: #1e293b; font-size: 15px; font-weight: 500; margin-top: 4px; }}
                            .quantity {{ background: #fef3c7; color: #92400e; padding: 4px 12px; border-radius: 20px; font-weight: 700; }}
                            .footer {{ margin-top: 40px; text-align: center; color: #94a3b8; font-size: 12px; border-top: 2px solid #e2e8f0; padding-top: 20px; }}
                        </style>
                    </head>
                    <body>
                        <div class="header">
                            <h1>📦 OPEN BACK ORDERS</h1>
                            <div class="subtitle">Pending Fulfillment Report</div>
                        </div>
                        <div class="meta-info">
                            <div><strong>Generated:</strong> {current_time}</div>
                            <div><strong>Open Orders:</strong> {len(open_orders)}</div>
                        </div>
                    """
                    
                    for idx, bo in enumerate(open_orders, 1):
                        html_content += f"""
                        <div class="order-card">
                            <div class="order-header">Back Order #{idx}</div>
                            <div class="detail-row">
                                <div class="detail-label">Material</div>
                                <div class="detail-value">{bo.get('material', 'N/A')}</div>
                            </div>
                            <div class="detail-row">
                                <div class="detail-label">Quantity</div>
                                <div class="detail-value"><span class="quantity">{bo.get('shortfall_quantity', 0)} units</span></div>
                            </div>
                            <div class="detail-row">
                                <div class="detail-label">Customer</div>
                                <div class="detail-value">{bo.get('client_name', 'N/A')}</div>
                            </div>
                            <div class="detail-row">
                                <div class="detail-label">Sales Order</div>
                                <div class="detail-value">{bo.get('order_number', 'N/A')}</div>
                            </div>
                        """
                        if bo.get('note'):
                            html_content += f"""
                            <div class="detail-row">
                                <div class="detail-label">Notes</div>
                                <div class="detail-value">{bo.get('note')}</div>
                            </div>
                            """
                        html_content += "</div>"
                    
                    html_content += """
                        <div class="footer">
                            <p>Generated by MJP Pulse Inventory System</p>
                        </div>
                    </body>
                    </html>
                    """
                    
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    st.download_button(
                        label="📄 Download Report",
                        data=html_content,
                        file_name=f"back_orders_{timestamp}.html",
                        mime="text/html"
                    )
                    st.info("💡 Open in browser → Print → Save as PDF")
            
            except Exception as e:
                st.error(f"Error loading back orders: {e}")
            
            st.info("👆 Select a category above to start building your order")
            
with tab4:
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h1 style="color: #1e40af; margin: 0;">📦 Smart Inventory Receiver</h1>
            <p style="color: #64748b; margin-top: 8px;">Multi-line receiving with intelligent tracking and automatic PO management</p>
        </div>
    """, unsafe_allow_html=True)
    
    # ── Safe DataFrame Check ────────────────────────────────────────────────────
    if df is not None and not df.empty:
        safe_df = df.copy()
    else:
        safe_df = pd.DataFrame(columns=['Item_ID', 'Material', 'Footage', 'Location', 'Status', 'Category', 'Purchase_Order_Num'])
        st.info("📦 No inventory data found. This is your first time receiving items - let's get started!")
    
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
    
    category_icons = {
        "Coils": "🔄", "Rolls": "📜", "Elbows": "↩️", 
        "Fab Straps": "🔗", "Mineral Wool": "🧶",
        "Fiberglass Insulation": "🏠", "Wing Seals": "🔒", 
        "Wire": "➰", "Banding": "📏", "Other": "📦"
    }
    
    # Categories that require unique serial IDs (tracked individually)
    SERIALIZED_CATEGORIES = ["Coils", "Rolls"]
    
    # ── Initialize Session State for Receiving Cart ────────────────────────────
    if 'receiving_cart' not in st.session_state:
        st.session_state.receiving_cart = []
    if 'current_po' not in st.session_state:
        st.session_state.current_po = ""
    if 'receiving_operator' not in st.session_state:
        st.session_state.receiving_operator = st.session_state.get("username", "")
    
    # ── Purchase Order Header (Outside form for persistence) ───────────────────
    st.markdown("### 📋 Purchase Order Information")
    
    col_po, col_op = st.columns([2, 1])
    
    with col_po:
        st.markdown("""
            <div style="background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%); 
                        padding: 20px; border-radius: 12px; border-left: 4px solid #f59e0b;">
        """, unsafe_allow_html=True)
        
        current_po = st.text_input(
            "📄 Purchase Order Number",
            value=st.session_state.current_po,
            placeholder="e.g. PO-2026-001",
            help="All items added will be tagged with this PO",
            key="po_header"
        )
        st.session_state.current_po = current_po
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    with col_op:
        st.markdown("""
            <div style="background: linear-gradient(135deg, #e0e7ff 0%, #c7d2fe 100%); 
                        padding: 20px; border-radius: 12px; border-left: 4px solid #6366f1;">
        """, unsafe_allow_html=True)
        
        operator = st.text_input(
            "👤 Receiving Operator",
            value=st.session_state.receiving_operator,
            key="op_header"
        )
        st.session_state.receiving_operator = operator
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # ── STEP 1: Category Selection (Outside form for reactivity) ───────────────
    st.markdown("### Step 1️⃣: Select Category")
    
    raw_cat = st.selectbox(
        "What are you receiving?", 
        list(cat_mapping.keys()),
        key="cat_select"
    )
    cat_choice = cat_mapping[raw_cat]
    
    # Determine if this category needs serial IDs
    is_serialized = cat_choice in SERIALIZED_CATEGORIES
    
    if is_serialized:
        st.info(f"🏷️ **{cat_choice}** require unique Item IDs for tracking")
    else:
        st.success(f"📦 **{cat_choice}** - Bulk item (quantities will be added together automatically)")
    
    st.markdown("---")
    
    # ── STEP 2: Add Item Form ──────────────────────────────────────────────────
    with st.form("add_receiving_item_form", clear_on_submit=True):
        
        # Dynamic Material Builder
        material = ""
        qty_val = 1.0
        unit_label = "Items"
        id_prefix = ""
        
        # Material Specifications Card
        st.markdown(f"### Step 2️⃣: {category_icons.get(cat_choice, '📦')} {cat_choice} Specifications")
        
        with st.container():
            st.markdown("""
                <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); 
                            padding: 24px; border-radius: 12px; border-left: 4px solid #0284c7;">
            """, unsafe_allow_html=True)
            
            if cat_choice == "Coils":
                col1, col2 = st.columns(2)
                with col1:
                    texture = st.radio("🎨 Texture", ["Stucco", "Smooth"], horizontal=True, key="coil_texture")
                    metal = st.radio("🔩 Metal Type", ["Aluminum", "Stainless Steel"], horizontal=True, key="coil_metal")
                with col2:
                    gauge = st.selectbox("📏 Gauge", [".010", ".016", ".020", ".024", ".032", "Other"], key="coil_gauge")
                    if gauge == "Other":
                        gauge = st.text_input("Custom Gauge", placeholder="e.g. .040", key="coil_custom_gauge")
                
                clean_gauge = gauge.replace('.', '')
                texture_code = "SMP" if texture == "Smooth" else "STP"
                metal_code = "AL" if metal == "Aluminum" else "SST"
                
                material = f"{texture} {metal} Coil - {gauge} Gauge"
                qty_val = st.number_input("📐 Footage per Coil", min_value=0.1, value=3000.0, key="coil_footage")
                unit_label = "Coils"
                
                id_prefix = f"Coil-{metal_code}-{clean_gauge}-{texture_code}"
            
            elif cat_choice == "Rolls":
                col1, col2 = st.columns(2)
                with col1:
                    roll_type = st.radio("🗞️ Roll Type", ["Regular", "RPR (Reinforced)"], horizontal=True, key="roll_type")
                    texture = st.radio("🎨 Texture", ["Stucco", "Smooth"], horizontal=True, key="roll_texture")
                    metal = st.radio("🔩 Metal Type", ["Aluminum", "Stainless Steel"], horizontal=True, key="roll_metal")
                with col2:
                    gauge = st.selectbox("📏 Gauge", [".016", ".020", ".024", ".032", "Other"], key="roll_gauge")
                    if gauge == "Other":
                        gauge = st.text_input("Custom Gauge", placeholder="e.g. .040", key="roll_custom_gauge")
                
                clean_gauge = gauge.replace('.', '')
                texture_code = "SMP" if texture == "Smooth" else "STP"
                metal_code = "AL" if metal == "Aluminum" else "SST"
                roll_type_code = "RPR-" if roll_type == "RPR (Reinforced)" else ""
                
                material = f"{texture} {metal} {roll_type_code}Roll - {gauge} Gauge"
                qty_val = st.number_input("📐 Footage per Roll", min_value=0.1, value=100.0, key="roll_footage")
                unit_label = "Rolls"
                
                id_prefix = f"Roll-{roll_type_code}{metal_code}-{clean_gauge}-{texture_code}"
            
            elif cat_choice == "Elbows":
                col1, col2 = st.columns(2)
                with col1:
                    angle = st.radio("📐 Angle", ["90°", "45°", "Other"], horizontal=True, key="elbow_angle")
                    if angle == "Other":
                        angle = st.text_input("Custom Angle", placeholder="e.g. 22.5°", key="elbow_custom_angle")
                    size_num = st.number_input("🔢 Size Number", min_value=1, max_value=60, value=1, key="elbow_size")
                with col2:
                    metal = st.radio("🔩 Metal Type", ["Aluminum", "Stainless Steel", "Galvanized", "Other"], key="elbow_metal")
                
                material = f"{angle} Elbow - Size #{size_num} - {metal}"
                qty_val = st.number_input("🔢 Quantity (pieces)", min_value=1, value=1, step=1, key="elbow_qty")
                unit_label = "Pieces"
            
            elif cat_choice == "Fab Straps":
                col1, col2 = st.columns(2)
                with col1:
                    gauge = st.selectbox("📏 Gauge", [".015", ".020"], key="strap_gauge")
                    size_num = st.number_input("🔢 Size Number", min_value=1, max_value=50, value=1, key="strap_size")
                with col2:
                    metal = st.radio("🔩 Metal Type", ["Aluminum", "Stainless Steel", "Other"], key="strap_metal")
                
                material = f"Fab Strap {gauge} - #{size_num} - {metal}"
                qty_val = st.number_input("🔢 Quantity (bundles)", min_value=1, value=1, step=1, key="strap_qty")
                unit_label = "Bundles"
            
            elif cat_choice == "Mineral Wool":
                col1, col2 = st.columns(2)
                with col1:
                    pipe_size = st.selectbox("🔧 Pipe Size", ["1 in", "2 in", "3 in", "4 in", "Other"], key="mw_pipe")
                    if pipe_size == "Other":
                        pipe_size = st.text_input("Custom Pipe Size", key="mw_custom_pipe")
                with col2:
                    thickness = st.selectbox("📏 Thickness", ["0.5 in", "1 in", "1.5 in", "2 in", "Other"], key="mw_thick")
                    if thickness == "Other":
                        thickness = st.text_input("Custom Thickness", key="mw_custom_thick")
                
                material = f"Mineral Wool - Pipe Size: {pipe_size} - Thickness: {thickness}"
                qty_val = st.number_input("🔢 Quantity (sections)", min_value=1, value=1, step=1, key="mw_qty")
                unit_label = "Sections"
            
            elif cat_choice == "Fiberglass Insulation":
                col1, col2 = st.columns(2)
                with col1:
                    form_type = st.radio("📦 Form", ["Rolls", "Batts", "Pipe Wrap", "Other"], key="fg_form")
                    thickness = st.selectbox("📏 Thickness", ["0.25 in", "0.5 in", "1 in", "1.5 in", "2 in", "Other"], key="fg_thick")
                    if thickness == "Other":
                        thickness = st.text_input("Custom Thickness", placeholder="e.g. 3 in", key="fg_custom_thick")
                with col2:
                    sq_ft_per = st.number_input("📐 Sq Ft per item", min_value=1.0, value=150.0, key="fg_sqft")
                
                material = f"Fiberglass {form_type} - {thickness} Thickness"
                qty_val = st.number_input("🔢 Quantity", min_value=1, value=1, step=1, key="fg_qty")
                unit_label = form_type
            
            elif cat_choice == "Wing Seals":
                col1, col2 = st.columns(2)
                with col1:
                    seal_type = st.radio("🔐 Type", ["Open", "Closed"], horizontal=True, key="ws_type")
                    size = st.radio("📏 Size", ["1/2 in", "3/4 in"], horizontal=True, key="ws_size")
                    gauge = st.selectbox("📐 Gauge", [".028", ".032", "Other"], key="ws_gauge")
                    if gauge == "Other":
                        gauge = st.text_input("Custom Gauge", key="ws_custom_gauge")
                with col2:
                    grooves = st.radio("〰️ Grooves", ["With Grooves (Center)", "Without Grooves"], key="ws_grooves")
                    joint_pos = st.radio("📍 Joint Position", ["Bottom", "Top", "N/A"], key="ws_joint")
                
                material = f"{seal_type} Wing Seal - {size} - {gauge} Gauge - {grooves} - Joint at {joint_pos}"
                qty_val = st.number_input("🔢 Quantity (pieces)", min_value=1, value=1000, step=100, key="ws_qty")
                unit_label = "Pieces"
            
            elif cat_choice == "Wire":
                col1, col2 = st.columns(2)
                with col1:
                    gauge = st.selectbox("📏 Gauge", ["14", "16", "18", "Other"], key="wire_gauge")
                    if gauge == "Other":
                        gauge = st.text_input("Custom Gauge", key="wire_custom_gauge")
                with col2:
                    footage_per_roll = st.number_input("📐 Footage per Roll (optional)", min_value=0.0, value=0.0, key="wire_footage")
                
                material = f"Wire - {gauge} Gauge"
                qty_val = st.number_input("🔢 Number of Rolls", min_value=1, value=1, step=1, key="wire_rolls")
                unit_label = "Rolls"
            
            elif cat_choice == "Banding":
                col1, col2 = st.columns(2)
                with col1:
                    osc_type = st.radio("🌀 Type", ["Oscillated", "Non-Oscillated"], key="band_osc")
                    size = st.radio("📏 Size", ["3/4 in", "1/2 in"], key="band_size")
                with col2:
                    gauge = st.selectbox("📐 Gauge", [".015", ".020"], key="band_gauge")
                    core = st.radio("⚙️ Core", ["Metal Core", "Non-Metal Core"], key="band_core")
                
                material = f"{osc_type} Banding - {size} - {gauge} Gauge - {core}"
                qty_val = st.number_input("📐 Footage per Roll", min_value=0.1, value=100.0, key="band_footage")
                unit_label = "Rolls"
            
            elif cat_choice == "Other":
                cat_choice = st.text_input("📝 New Category Name", placeholder="e.g. Accessories", key="other_cat")
                material = st.text_input("📦 Material Description", placeholder="e.g. Custom Gaskets", key="other_mat")
                qty_val = st.number_input("🔢 Qty/Footage per item", min_value=0.1, value=1.0, key="other_qty")
                unit_label = st.text_input("🏷️ Unit Label", value="Units", key="other_unit")
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # Quantity & Storage
        st.markdown("### Step 3️⃣: 📦 Quantity & Storage")
        
        with st.container():
            st.markdown("""
                <div style="background: linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%); 
                            padding: 24px; border-radius: 12px; border-left: 4px solid #16a34a;">
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns(2)
            
            with col1:
                if is_serialized:
                    item_count = st.number_input(
                        f"📦 How many {unit_label}?", 
                        min_value=1, value=1, step=1,
                        key="item_count_serialized"
                    )
                    total_added = item_count * qty_val
                    st.success(f"**📊 Total:** {item_count} {unit_label.lower()} ({total_added:.1f} ft)")
                else:
                    # For non-serialized, qty_val IS the quantity
                    item_count = 1  # Always 1 "batch"
                    total_added = qty_val
                    st.success(f"**📊 Total:** {total_added:.0f} {unit_label.lower()}")
            
            with col2:
                loc_type = st.radio("🏢 Storage Type", ["Rack System", "Floor / Open Space"], horizontal=True, key="storage_type_radio")
            
            # Storage location input
            if loc_type == "Rack System":
                subcol1, subcol2, subcol3 = st.columns(3)
                bay = subcol1.number_input("🅱️ Bay", min_value=1, value=1, key="rack_bay")
                sec = subcol2.selectbox("🔤 Section", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), key="rack_sec")
                lvl = subcol3.number_input("⬆️ Level", min_value=1, value=1, key="rack_lvl")
                gen_loc = f"{bay}{sec}{lvl}"
            else:
                subcol1, subcol2, subcol3 = st.columns(3)
                bay = subcol1.number_input("🅱️ Bay", min_value=1, value=1, key="floor_bay")
                floor_options = [f"Floor {letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
                floor_selection = subcol2.selectbox("🔤 Floor Section", floor_options, key="floor_sec")
                lvl = subcol3.number_input("⬆️ Level", min_value=1, value=1, key="floor_lvl")
                gen_loc = f"{bay}-{floor_selection}-{lvl}"
            
            st.info(f"📍 **Location:** {gen_loc}")
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # ── STEP 4: ID Generation (Only for Serialized Items) ──────────────────
        id_list = []
        
        if is_serialized:
            st.markdown("### Step 4️⃣: 🏷️ Item Identification")
            
            with st.container():
                st.markdown("""
                    <div style="background: linear-gradient(135deg, #fdf4ff 0%, #fae8ff 100%); 
                                padding: 24px; border-radius: 12px; border-left: 4px solid #9333ea;">
                """, unsafe_allow_html=True)
                
                st.info(f"💡 **Suggested format:** `{id_prefix}-[NUMBER]` (e.g., {id_prefix}-01)")
                
                if item_count == 1:
                    custom_id = st.text_input(
                        "🏷️ Item ID",
                        value="",
                        placeholder=f"e.g., {id_prefix}-01",
                        key="custom_single_id",
                        help="Enter any ID you want. Must be unique."
                    )
                    id_list = [custom_id.strip()] if custom_id.strip() else []
                else:
                    id_method = st.radio(
                        "How do you want to assign IDs?",
                        ["Sequential (auto-increment)", "Manual (enter each)"],
                        horizontal=True,
                        key="id_method"
                    )
                    
                    if id_method == "Sequential (auto-increment)":
                        col_base, col_start = st.columns(2)
                        with col_base:
                            base_id = st.text_input(
                                "🏷️ Base ID",
                                value=id_prefix,
                                placeholder="e.g., Coil-AL-016-STP",
                                key="base_id_input"
                            )
                        with col_start:
                            start_num = st.number_input(
                                "Starting Number",
                                min_value=1,
                                value=1,
                                step=1,
                                key="start_num_input"
                            )
                        
                        id_list = [f"{base_id}-{str(start_num + i).zfill(2)}" for i in range(item_count)]
                        
                        st.markdown("**Preview IDs:**")
                        preview_text = ", ".join(id_list[:5])
                        if len(id_list) > 5:
                            preview_text += f", ... ({len(id_list)} total)"
                        st.code(preview_text)
                    
                    else:
                        st.markdown(f"Enter {item_count} IDs (one per line):")
                        manual_ids = st.text_area(
                            "🏷️ Item IDs (one per line)",
                            value="",
                            height=150,
                            placeholder=f"Example:\n{id_prefix}-01\n{id_prefix}-02\n{id_prefix}-03",
                            key="manual_ids_input"
                        )
                        id_list = [line.strip() for line in manual_ids.strip().split('\n') if line.strip()]
                        
                        if id_list and len(id_list) != item_count:
                            st.warning(f"⚠️ You entered {len(id_list)} IDs but specified {item_count} items.")
                
                # Validation for serialized items
                if id_list:
                    # Check duplicates within list
                    duplicates_in_list = [id for id in id_list if id_list.count(id) > 1]
                    if duplicates_in_list:
                        st.error(f"❌ Duplicate IDs in your list: {set(duplicates_in_list)}")
                    
                    # Check against existing inventory
                    if safe_df is not None and not safe_df.empty:
                        existing_ids = safe_df['Item_ID'].tolist()
                        clashing_ids = [id for id in id_list if id in existing_ids]
                        
                        if clashing_ids:
                            st.error(f"❌ **These IDs already exist:**")
                            for clash_id in clashing_ids[:5]:
                                existing_item = safe_df[safe_df['Item_ID'] == clash_id].iloc[0]
                                st.markdown(f"- `{clash_id}` → {existing_item['Material']} at {existing_item['Location']}")
                            if len(clashing_ids) > 5:
                                st.markdown(f"- ... and {len(clashing_ids) - 5} more")
                
                st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown("### Step 4️⃣: ✅ Ready to Add")
            st.success("📦 **Bulk item** - Will be added to existing stock or create new entry automatically. No ID conflicts possible!")
        
        # Add to Cart Button
        add_item = st.form_submit_button(
            "🛒 Add to Receiving Cart", 
            use_container_width=True, 
            type="primary"
        )

    # ── Process Add to Cart ─────────────────────────────────────────────────────
    if add_item:
        if not current_po.strip():
            st.error("⚠️ Please enter a Purchase Order Number first!")
        elif not operator.strip():
            st.error("⚠️ Please enter the Receiving Operator name!")
        elif not material:
            st.error("⚠️ Material details are required!")
        elif is_serialized and not id_list:
            st.error("⚠️ Please enter Item ID(s) for Coils/Rolls!")
        elif is_serialized and len(id_list) != item_count:
            st.error(f"⚠️ ID count mismatch: You entered {len(id_list)} IDs but specified {item_count} items.")
        else:
            # Validation for serialized items only
            has_errors = False
            
            if is_serialized:
                # Check duplicates within list
                duplicates_in_list = set([id for id in id_list if id_list.count(id) > 1])
                if duplicates_in_list:
                    st.error(f"❌ Duplicate IDs: {duplicates_in_list}")
                    has_errors = True
                
                # Check against existing inventory
                if safe_df is not None and not safe_df.empty:
                    existing_ids = safe_df['Item_ID'].tolist()
                    clashing_ids = [id for id in id_list if id in existing_ids]
                    if clashing_ids:
                        st.error(f"❌ IDs already exist: {clashing_ids[:5]}{'...' if len(clashing_ids) > 5 else ''}")
                        has_errors = True
            
            if not has_errors:
                st.session_state.receiving_cart.append({
                    'category': cat_choice,
                    'material': material,
                    'qty_val': qty_val,
                    'item_count': item_count,
                    'total_added': total_added,
                    'unit_label': unit_label,
                    'location': gen_loc,
                    'is_serialized': is_serialized,
                    'id_list': id_list if is_serialized else [],
                    'id_preview': id_list[0] if id_list else f"{cat_choice.upper()}-BULK",
                })
                
                if is_serialized:
                    st.success(f"✅ Added: {item_count} × {material}")
                    st.info(f"🏷️ IDs: {', '.join(id_list[:3])}{'...' if len(id_list) > 3 else ''}")
                else:
                    st.success(f"✅ Added: {total_added:.0f} {unit_label.lower()} of {material}")
                st.rerun()
    
    # ── Display Receiving Cart ──────────────────────────────────────────────────
    if st.session_state.receiving_cart:
        st.markdown("---")
        st.markdown("### 🛒 Current Receiving Batch")
        st.info(f"📋 **PO:** {st.session_state.current_po} | 👤 **Operator:** {st.session_state.receiving_operator}")
        
        for idx, item in enumerate(st.session_state.receiving_cart):
            col_item, col_remove = st.columns([5, 1])
            
            with col_item:
                if item['is_serialized']:
                    st.write(f"**{idx+1}.** {item['item_count']} × {item['material']} = **{item['total_added']:.1f} ft** → 📍 {item['location']}")
                    st.caption(f"🏷️ IDs: {', '.join(item['id_list'][:3])}{'...' if len(item['id_list']) > 3 else ''}")
                else:
                    st.write(f"**{idx+1}.** {item['total_added']:.0f} {item['unit_label'].lower()} of {item['material']} → 📍 {item['location']}")
            
            with col_remove:
                if st.button("🗑️", key=f"remove_receiving_{idx}"):
                    st.session_state.receiving_cart.pop(idx)
                    st.rerun()
        
        st.markdown("---")
        
        col_process, col_clear = st.columns(2)

        with col_process:
            if st.button("✅ Process All Items to Inventory", type="primary", use_container_width=True):
                if not st.session_state.current_po.strip() or not st.session_state.receiving_operator.strip():
                    st.error("⚠️ PO Number and Operator are required!")
                else:
                    # Final validation for SERIALIZED items ONLY
                    all_new_ids = []
                    for item in st.session_state.receiving_cart:
                        if item['is_serialized']:  # Only check serialized items
                            all_new_ids.extend(item['id_list'])
                    
                    has_clashes = False
                    if all_new_ids:  # Only check if there are serialized items
                        try:
                            response = supabase.table("inventory").select("Item_ID").in_("Item_ID", all_new_ids).execute()
                            if response.data:
                                existing_clashes = [row['Item_ID'] for row in response.data]
                                st.error(f"❌ **These IDs already exist:**")
                                for clash in existing_clashes[:5]:
                                    st.write(f"- `{clash}`")
                                has_clashes = True
                        except:
                            pass
                    
                    if not has_clashes:
                        with st.spinner("☁️ Processing to Cloud Database..."):
                            try:
                                items_added = 0
                                
                                for item in st.session_state.receiving_cart:
                                    if item['is_serialized']:
                                        # ═══════════════════════════════════════════════════
                                        # SERIALIZED ITEMS (Coils/Rolls) - Create individual records
                                        # ═══════════════════════════════════════════════════
                                        new_rows = []
                                        for unique_id in item['id_list']:
                                            new_rows.append({
                                                "Item_ID": unique_id,
                                                "Material": item['material'],
                                                "Footage": item['qty_val'],
                                                "Location": item['location'],
                                                "Status": "Active",
                                                "Category": item['category'],
                                                "Purchase_Order_Num": st.session_state.current_po.strip()
                                            })
                                        
                                        if new_rows:
                                            supabase.table("inventory").insert(new_rows).execute()
                                            items_added += len(new_rows)
                                    
                                    else:
                                        # ═══════════════════════════════════════════════════
                                        # BULK ITEMS - Add to existing OR create new
                                        # NO ID CLASH CHECKING - just upsert by material
                                        # ═══════════════════════════════════════════════════
                                        try:
                                            # Check if this exact category + material combo exists
                                            existing_response = supabase.table("inventory").select("*").eq("Category", item['category']).eq("Material", item['material']).execute()
                                            
                                            if existing_response.data and len(existing_response.data) > 0:
                                                # EXISTS - Add quantity to existing record
                                                existing_item = existing_response.data[0]
                                                current_qty = float(existing_item.get('Footage', 0))
                                                new_qty = current_qty + item['total_added']
                                                
                                                supabase.table("inventory").update({
                                                    "Footage": new_qty,
                                                    "Location": item['location']  # Update location too
                                                }).eq("Item_ID", existing_item['Item_ID']).execute()
                                                
                                                # Log the addition
                                                log_entry = {
                                                    "Item_ID": existing_item['Item_ID'],
                                                    "Action": "Stock Added",
                                                    "User": st.session_state.receiving_operator,
                                                    "Timestamp": datetime.now().isoformat(),
                                                    "Details": f"PO: {st.session_state.current_po} | Added {item['total_added']:.0f} {item['unit_label'].lower()} to existing stock. Previous: {current_qty:.0f}, New: {new_qty:.0f}"
                                                }
                                                supabase.table("audit_log").insert(log_entry).execute()
                                                
                                                items_added += 1
                                            else:
                                                # DOES NOT EXIST - Create new bulk entry with UUID
                                                import uuid
                                                unique_id = f"{item['category'].upper().replace(' ', '-')}-{uuid.uuid4().hex[:8].upper()}"
                                                
                                                new_data = {
                                                    "Item_ID": unique_id,
                                                    "Material": item['material'],
                                                    "Footage": item['total_added'],
                                                    "Location": item['location'],
                                                    "Status": "Active",
                                                    "Category": item['category'],
                                                    "Purchase_Order_Num": st.session_state.current_po.strip()
                                                }
                                                supabase.table("inventory").insert(new_data).execute()
                                                
                                                # Log new item
                                                log_entry = {
                                                    "Item_ID": unique_id,
                                                    "Action": "Received (New Item)",
                                                    "User": st.session_state.receiving_operator,
                                                    "Timestamp": datetime.now().isoformat(),
                                                    "Details": f"PO: {st.session_state.current_po} | {item['material']} | {item['total_added']:.0f} {item['unit_label'].lower()} | Location: {item['location']}"
                                                }
                                                supabase.table("audit_log").insert(log_entry).execute()
                                                
                                                items_added += 1
                                                
                                        except Exception as bulk_error:
                                            # If anything fails, create with UUID (guaranteed unique)
                                            import uuid
                                            unique_id = f"{item['category'].upper().replace(' ', '-')}-{uuid.uuid4().hex[:8].upper()}"
                                            
                                            new_data = {
                                                "Item_ID": unique_id,
                                                "Material": item['material'],
                                                "Footage": item['total_added'],
                                                "Location": item['location'],
                                                "Status": "Active",
                                                "Category": item['category'],
                                                "Purchase_Order_Num": st.session_state.current_po.strip()
                                            }
                                            supabase.table("inventory").insert(new_data).execute()
                                            
                                            log_entry = {
                                                "Item_ID": unique_id,
                                                "Action": "Received",
                                                "User": st.session_state.receiving_operator,
                                                "Timestamp": datetime.now().isoformat(),
                                                "Details": f"PO: {st.session_state.current_po} | {item['material']} | {item['total_added']:.0f} {item['unit_label'].lower()}"
                                            }
                                            supabase.table("audit_log").insert(log_entry).execute()
                                            
                                            items_added += 1
                                
                                st.cache_data.clear()
                                st.session_state.force_refresh = True
                                
                                st.success(f"✅ Successfully processed {items_added} item(s) for PO: {st.session_state.current_po}!")
                                st.balloons()
                                
                                st.session_state.receiving_cart = []
                                time.sleep(1)
                                st.rerun()
                            
                            except Exception as e:
                                st.error(f"❌ Failed to process: {e}")
                                import traceback
                                st.code(traceback.format_exc())
        with col_clear:
            if st.button("🗑️ Clear Cart", use_container_width=True):
                st.session_state.receiving_cart = []
                st.rerun()
    
    elif not st.session_state.receiving_cart:
        st.info("👆 Add items to start building your receiving batch")
    
    # ══════════════════════════════════════════════════════════════════════════════
    # REVERSE RECEIVED ORDER SECTION
    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h2 style="color: #dc2626; margin: 0;">🔄 Reverse Received Order</h2>
            <p style="color: #64748b; margin-top: 8px;">Undo items received under a specific Purchase Order</p>
        </div>
    """, unsafe_allow_html=True)
    
    with st.expander("🔄 Reverse a Received PO", expanded=False):
        st.warning("⚠️ **Use with caution!** This will remove items from inventory.")
        
        # Input PO number to reverse
        reverse_po = st.text_input(
            "📄 Enter PO Number to Reverse",
            placeholder="e.g. PO-2026-001",
            key="reverse_po_input"
        )
        
        if reverse_po.strip():
            # Fetch items with this PO
            try:
                response = supabase.table("inventory").select("*").eq("Purchase_Order_Num", reverse_po.strip()).execute()
                
                if not response.data:
                    st.info(f"📭 No items found for PO: {reverse_po}")
                else:
                    po_items = response.data
                    po_df = pd.DataFrame(po_items)
                    
                    st.markdown(f"### 📋 Items under PO: {reverse_po}")
                    st.info(f"Found **{len(po_items)}** item(s)")
                    
                    # Summary by category
                    summary = po_df.groupby('Category').agg({
                        'Footage': 'sum',
                        'Item_ID': 'count'
                    }).reset_index()
                    summary.columns = ['Category', 'Total Footage/Qty', 'Item Count']
                    
                    st.dataframe(summary, use_container_width=True, hide_index=True)
                    
                    # Show details
                    with st.expander("📋 View All Items"):
                        st.dataframe(
                            po_df[['Item_ID', 'Category', 'Material', 'Footage', 'Location']],
                            use_container_width=True,
                            hide_index=True
                        )
                    
                    st.markdown("---")
                    
                    # Reversal options
                    reversal_type = st.radio(
                        "What do you want to reverse?",
                        ["All items under this PO", "Select specific items"],
                        key="reversal_type"
                    )
                    
                    items_to_remove = []
                    
                    if reversal_type == "All items under this PO":
                        items_to_remove = [item['Item_ID'] for item in po_items]
                        st.warning(f"⚠️ This will remove **{len(items_to_remove)}** item(s) from inventory")
                    
                    else:
                        # Multi-select specific items
                        item_options = [f"{item['Item_ID']} - {item['Material'][:30]}... ({item['Footage']})" for item in po_items]
                        selected_items = st.multiselect(
                            "Select items to remove",
                            item_options,
                            key="select_items_to_remove"
                        )
                        
                        items_to_remove = [opt.split(" - ")[0] for opt in selected_items]
                        
                        if items_to_remove:
                            st.warning(f"⚠️ This will remove **{len(items_to_remove)}** item(s)")
                    
                    if items_to_remove:
                        reversal_reason = st.text_input(
                            "Reason for Reversal *",
                            placeholder="e.g. Wrong PO, duplicate entry, returned to supplier",
                            key="reversal_reason_input"
                        )
                        
                        confirm_reversal = st.checkbox(
                            f"I confirm I want to remove {len(items_to_remove)} item(s) from inventory",
                            key="confirm_po_reversal"
                        )
                        
                        if st.button("🗑️ Reverse Selected Items", type="primary", use_container_width=True):
                            if not reversal_reason.strip():
                                st.error("⚠️ Please provide a reason for the reversal")
                            elif not confirm_reversal:
                                st.error("⚠️ Please confirm the reversal")
                            else:
                                with st.spinner("Reversing..."):
                                    try:
                                        removed_count = 0
                                        
                                        for item_id in items_to_remove:
                                            # Get item details for logging
                                            item_data = next((item for item in po_items if item['Item_ID'] == item_id), None)
                                            
                                            if item_data:
                                                # Delete from inventory
                                                supabase.table("inventory").delete().eq("Item_ID", item_id).execute()
                                                removed_count += 1
                                                
                                                # Log the reversal
                                                log_entry = {
                                                    "Item_ID": item_id,
                                                    "Action": "Receiving Reversed",
                                                    "User": st.session_state.get('username', 'Admin'),
                                                    "Timestamp": datetime.now().isoformat(),
                                                    "Details": f"Reversed PO: {reverse_po} | {item_data['Material'][:30]} | {item_data['Footage']} | Reason: {reversal_reason}"
                                                }
                                                supabase.table("audit_log").insert(log_entry).execute()
                                        
                                        # Log overall reversal
                                        summary_log = {
                                            "Item_ID": reverse_po,
                                            "Action": "PO Reversal",
                                            "User": st.session_state.get('username', 'Admin'),
                                            "Timestamp": datetime.now().isoformat(),
                                            "Details": f"Reversed {removed_count} items from PO {reverse_po}. Reason: {reversal_reason}"
                                        }
                                        supabase.table("audit_log").insert(summary_log).execute()
                                        
                                        st.success(f"✅ Reversed {removed_count} item(s) from PO: {reverse_po}")
                                        st.balloons()
                                        
                                        st.cache_data.clear()
                                        st.session_state.force_refresh = True
                                        time.sleep(1)
                                        st.rerun()
                                        
                                    except Exception as e:
                                        st.error(f"❌ Error: {e}")
            
            except Exception as e:
                st.error(f"Error fetching PO items: {e}")
    
    # ══════════════════════════════════════════════════════════════════════════════
    # RECEIPT REPORT SECTION
    # ══════════════════════════════════════════════════════════════════════════════
    st.markdown("---")
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h2 style="color: #1e40af; margin: 0;">📄 Receipt Report Generator</h2>
            <p style="color: #64748b; margin-top: 8px;">Generate PDF reports for items received under specific Purchase Orders</p>
        </div>
    """, unsafe_allow_html=True)

    with st.container():
        st.markdown("""
            <div style="background: linear-gradient(135deg, #fff7ed 0%, #ffedd5 100%); 
                        padding: 24px; border-radius: 12px; border: 2px solid #fb923c;">
        """, unsafe_allow_html=True)
        
        with st.form("export_report_form"):
            col1, col2 = st.columns([2, 1])
            
            with col1:
                report_po_num = st.text_input(
                    "📄 Purchase Order Number",
                    placeholder="e.g. PO-2026-001",
                    key="report_po"
                )
            
            with col2:
                export_mode = st.radio(
                    "📤 Action",
                    ["Download Only", "Download & Email"],
                    help="Choose whether to download or also email to admin"
                )
            
            submitted_report = st.form_submit_button(
                "🚀 Generate PDF Report", 
                use_container_width=True, 
                type="primary"
            )
        
        st.markdown("</div>", unsafe_allow_html=True)

    if submitted_report and report_po_num.strip():
        with st.spinner(f"🔍 Fetching items for PO: {report_po_num}..."):
            try:
                response = supabase.table("inventory").select("*").eq("Purchase_Order_Num", report_po_num.strip()).execute()
                
                if not response.data:
                    st.warning(f"⚠️ No items found for PO: {report_po_num}")
                else:
                    report_df = pd.DataFrame(response.data)
                    
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
                        key=f"dl_{report_po_num}",
                        type="secondary"
                    )
                    
                    if export_mode == "Download & Email":
                        with st.spinner("📧 Sending email..."):
                            pdf_buffer.seek(0)
                            
                            email_success = send_receipt_email(
                                admin_email="tmilazi@gmail.com",
                                po_num=report_po_num,
                                pdf_buffer=pdf_buffer,
                                operator=st.session_state.get('username', 'Operator')
                            )
                            
                            if email_success:
                                st.success(f"✅ PDF emailed to admin!")
                            else:
                                st.warning("⚠️ PDF generated but email failed.")
                    else:
                        st.success("✅ PDF generated!")
                        
            except Exception as e:
                st.error(f"❌ Error: {e}")
                
with tab5:
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h1 style="color: #dc2626; margin: 0;">⚙️ Admin Actions</h1>
            <p style="color: #64748b; margin-top: 8px;">Edit footage, locations, Item IDs, or remove items from inventory</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Check if user is admin (optional - add your admin usernames here)
    admin_users = ["admin", "manager", "tmilazi"]  # Add your admin usernames
    current_user = st.session_state.get('username', '')
    
    # For now, allow all logged-in users (remove this if you want admin-only)
    is_admin = True  # Change to: current_user.lower() in [u.lower() for u in admin_users]
    
    if not is_admin:
        st.error("🔒 Access Denied. Admin privileges required.")
    else:
        # Safe DataFrame check
        if df is not None and not df.empty:
            
            # Search/Filter Section
            st.markdown("### 🔍 Find Item to Edit")
            
            col_search, col_cat_filter = st.columns([2, 1])
            
            with col_search:
                search_term = st.text_input(
                    "Search by Item ID or Material",
                    placeholder="e.g. Coil-AL-016 or Stucco Aluminum",
                    key="admin_search"
                )
            
            with col_cat_filter:
                admin_categories = ["All"] + sorted(df['Category'].unique().tolist())
                selected_cat = st.selectbox("Filter by Category", admin_categories, key="admin_cat_filter")
            
            # Filter the dataframe
            admin_df = df.copy()
            
            if selected_cat != "All":
                admin_df = admin_df[admin_df['Category'] == selected_cat]
            
            if search_term:
                mask = (
                    admin_df['Item_ID'].str.contains(search_term, case=False, na=False) |
                    admin_df['Material'].str.contains(search_term, case=False, na=False)
                )
                admin_df = admin_df[mask]
            
            # Display filtered inventory
            if not admin_df.empty:
                st.markdown(f"### 📋 Inventory Items ({len(admin_df)} found)")
                
                # Show the data
                st.dataframe(
                    admin_df[['Item_ID', 'Category', 'Material', 'Footage', 'Location', 'Status']],
                    use_container_width=True,
                    hide_index=True
                )
                
                st.markdown("---")
                
                # Select item to edit
                st.markdown("### ✏️ Edit Item")
                
                item_options = admin_df['Item_ID'].tolist()
                selected_item = st.selectbox(
                    "Select Item to Edit",
                    item_options,
                    key="admin_select_item"
                )
                
                if selected_item:
                    # Get current item data
                    item_data = admin_df[admin_df['Item_ID'] == selected_item].iloc[0]
                    
                    st.markdown(f"""
                        <div style="background: #f0f9ff; padding: 15px; border-radius: 8px; margin: 10px 0; border-left: 4px solid #3b82f6;">
                            <strong>📦 Current Item Details:</strong><br><br>
                            <strong>Item ID:</strong> {selected_item}<br>
                            <strong>Material:</strong> {item_data['Material']}<br>
                            <strong>Category:</strong> {item_data['Category']}<br>
                            <strong>Current Footage:</strong> {item_data['Footage']}<br>
                            <strong>Current Location:</strong> {item_data['Location']}<br>
                            <strong>Status:</strong> {item_data.get('Status', 'N/A')}
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Edit options in tabs
                    edit_tab1, edit_tab2, edit_tab3, edit_tab4 = st.tabs(["🏷️ Edit Item ID", "📏 Edit Footage", "📍 Edit Location", "🗑️ Remove Item"])
                    
                    # ── Edit Item ID Tab ────────────────────────────────────────────
                    with edit_tab1:
                        st.markdown("#### 🏷️ Change Item ID")
                        
                        st.warning("⚠️ Changing Item IDs affects tracking and audit history. Use with caution!")
                        
                        with st.form("edit_item_id_form", clear_on_submit=True):
                            
                            # Show current ID format info
                            if item_data['Category'] == 'Coils':
                                st.info("💡 **Coil ID Format:** `Coil-[Metal]-[Gauge]-[Texture]-[Footage]-[Number]`\n\nExample: `Coil-AL-016-STP-3000-01`")
                            elif item_data['Category'] == 'Rolls':
                                st.info("💡 **Roll ID Format:** `Roll-[Metal]-[Gauge]-[Texture]-[Footage]-[Number]`\n\nExample: `Roll-AL-020-SMP-100-01`")
                            
                            new_item_id = st.text_input(
                                "New Item ID",
                                value=selected_item,
                                placeholder="Enter new Item ID",
                                key="new_item_id_input"
                            )
                            
                            # Check if new ID already exists
                            if new_item_id != selected_item:
                                existing_ids = df['Item_ID'].tolist()
                                if new_item_id in existing_ids:
                                    st.error(f"❌ Item ID '{new_item_id}' already exists! Choose a different ID.")
                                    id_is_valid = False
                                else:
                                    st.success(f"✅ Item ID '{new_item_id}' is available.")
                                    id_is_valid = True
                            else:
                                st.info("No change to Item ID")
                                id_is_valid = True
                            
                            id_change_reason = st.text_input(
                                "Reason for ID Change *",
                                placeholder="e.g. Correcting typo, updating format, label reprint",
                                key="id_change_reason"
                            )
                            
                            submit_item_id = st.form_submit_button("🏷️ Update Item ID", type="primary", use_container_width=True)
                        
                        if submit_item_id:
                            if new_item_id == selected_item:
                                st.info("No changes made - Item ID is the same.")
                            elif not id_change_reason.strip():
                                st.error("⚠️ Please provide a reason for the ID change.")
                            elif not id_is_valid:
                                st.error("⚠️ Cannot use an Item ID that already exists.")
                            elif not new_item_id.strip():
                                st.error("⚠️ Item ID cannot be empty.")
                            else:
                                try:
                                    # Update Item ID in inventory table
                                    supabase.table("inventory").update({
                                        "Item_ID": new_item_id.strip()
                                    }).eq("Item_ID", selected_item).execute()
                                    
                                    # Log the change
                                    log_entry = {
                                        "Item_ID": new_item_id.strip(),
                                        "Action": "Admin Edit - Item ID Changed",
                                        "User": st.session_state.get('username', 'Admin'),
                                        "Timestamp": datetime.now().isoformat(),
                                        "Details": f"Item ID changed from '{selected_item}' to '{new_item_id.strip()}'. Reason: {id_change_reason}"
                                    }
                                    supabase.table("audit_log").insert(log_entry).execute()
                                    
                                    st.success(f"✅ Item ID updated: {selected_item} → {new_item_id.strip()}")
                                    st.cache_data.clear()
                                    time.sleep(1)
                                    st.rerun()
                                    
                                except Exception as e:
                                    st.error(f"❌ Failed to update Item ID: {e}")
                    
                    # ── Edit Footage/Quantity Tab ────────────────────────────────────────────
                    with edit_tab2:
                        st.markdown("#### 📏 Adjust Stock Quantity")
                        
                        # Determine what type of item this is
                        item_category = item_data.get('Category', 'Other')
                        current_footage = float(item_data['Footage'])
                        
                        # Different UI based on category
                        if item_category == "Rolls":
                            st.info("🗞️ **Roll Inventory** - Edit footage per roll and/or manage roll count")
                            
                            # Get all rolls of same material
                            same_material_rolls = df[(df['Material'] == item_data['Material']) & (df['Category'] == 'Rolls')]
                            current_roll_count = len(same_material_rolls)
                            
                            st.markdown(f"**Current Inventory:** {current_roll_count} roll(s) of this material")
                            
                            # Show all rolls of this material
                            with st.expander(f"📋 View all {current_roll_count} roll(s) of {item_data['Material'][:40]}..."):
                                st.dataframe(
                                    same_material_rolls[['Item_ID', 'Footage', 'Location']].sort_values('Item_ID'),
                                    use_container_width=True,
                                    hide_index=True
                                )
                            
                            st.markdown("---")
                            
                            # Tab for different roll operations
                            roll_op1, roll_op2, roll_op3 = st.tabs(["✏️ Edit This Roll", "➕ Add Rolls", "➖ Remove Rolls"])
                            
                            # ── Edit single roll footage ──
                            with roll_op1:
                                with st.form("edit_single_roll_form", clear_on_submit=True):
                                    st.markdown(f"**Editing:** {selected_item}")
                                    
                                    new_footage = st.number_input(
                                        "Footage for this roll",
                                        min_value=0.0,
                                        value=current_footage,
                                        step=10.0,
                                        key="edit_roll_footage",
                                        help="The length of this roll in feet"
                                    )
                                    
                                    footage_diff = new_footage - current_footage
                                    if footage_diff > 0:
                                        st.success(f"📈 Adding {footage_diff:.1f} ft to this roll")
                                    elif footage_diff < 0:
                                        st.warning(f"📉 Removing {abs(footage_diff):.1f} ft from this roll")
                                    
                                    edit_roll_reason = st.text_input(
                                        "Reason for change *",
                                        placeholder="e.g. Physical measurement, partial use",
                                        key="edit_roll_reason"
                                    )
                                    
                                    submit_edit_roll = st.form_submit_button("💾 Update This Roll", type="primary", use_container_width=True)
                                
                                if submit_edit_roll:
                                    if not edit_roll_reason.strip():
                                        st.error("⚠️ Please provide a reason")
                                    elif new_footage == current_footage:
                                        st.info("No changes made")
                                    else:
                                        try:
                                            supabase.table("inventory").update({
                                                "Footage": new_footage
                                            }).eq("Item_ID", selected_item).execute()
                                            
                                            log_entry = {
                                                "Item_ID": selected_item,
                                                "Action": "Admin Edit - Roll Footage",
                                                "User": st.session_state.get('username', 'Admin'),
                                                "Timestamp": datetime.now().isoformat(),
                                                "Details": f"Changed footage from {current_footage:.1f} to {new_footage:.1f} ft. Reason: {edit_roll_reason}"
                                            }
                                            supabase.table("audit_log").insert(log_entry).execute()
                                            
                                            st.success(f"✅ Updated {selected_item}: {current_footage:.1f} → {new_footage:.1f} ft")
                                            st.cache_data.clear()
                                            st.session_state.force_refresh = True
                                            time.sleep(1)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ Failed: {e}")
                            
                            # ── Add more rolls ──
                            with roll_op2:
                                with st.form("add_rolls_form", clear_on_submit=True):
                                    st.markdown("**Add more rolls of the same material**")
                                    
                                    add_roll_count = st.number_input(
                                        "Number of rolls to add",
                                        min_value=1,
                                        value=1,
                                        step=1,
                                        key="add_roll_count"
                                    )
                                    
                                    add_roll_footage = st.number_input(
                                        "Footage per roll",
                                        min_value=0.1,
                                        value=current_footage,
                                        step=10.0,
                                        key="add_roll_footage"
                                    )
                                    
                                    add_roll_location = st.text_input(
                                        "Location",
                                        value=item_data.get('Location', ''),
                                        key="add_roll_location"
                                    )
                                    
                                    st.info(f"📦 Will add {add_roll_count} roll(s) × {add_roll_footage} ft = {add_roll_count * add_roll_footage:,.1f} ft total")
                                    
                                    add_roll_reason = st.text_input(
                                        "Reason *",
                                        placeholder="e.g. New shipment received, inventory correction",
                                        key="add_roll_reason"
                                    )
                                    
                                    submit_add_rolls = st.form_submit_button("➕ Add Rolls", type="primary", use_container_width=True)
                                
                                if submit_add_rolls:
                                    if not add_roll_reason.strip():
                                        st.error("⚠️ Please provide a reason")
                                    else:
                                        try:
                                            # Generate new IDs
                                            base_id = selected_item.rsplit('-', 1)[0] if '-' in selected_item else selected_item
                                            
                                            # Find highest existing number
                                            existing_ids = df[df['Item_ID'].str.startswith(base_id)]['Item_ID'].tolist()
                                            max_num = 0
                                            for eid in existing_ids:
                                                try:
                                                    num = int(eid.split('-')[-1])
                                                    max_num = max(max_num, num)
                                                except:
                                                    pass
                                            
                                            new_rolls_data = []
                                            new_ids = []
                                            for i in range(add_roll_count):
                                                new_id = f"{base_id}-{str(max_num + i + 1).zfill(2)}"
                                                new_ids.append(new_id)
                                                new_rolls_data.append({
                                                    "Item_ID": new_id,
                                                    "Material": item_data['Material'],
                                                    "Footage": add_roll_footage,
                                                    "Location": add_roll_location,
                                                    "Status": "Active",
                                                    "Category": "Rolls",
                                                    "Purchase_Order_Num": item_data.get('Purchase_Order_Num', '')
                                                })
                                            
                                            supabase.table("inventory").insert(new_rolls_data).execute()
                                            
                                            log_entry = {
                                                "Item_ID": base_id,
                                                "Action": "Admin - Added Rolls",
                                                "User": st.session_state.get('username', 'Admin'),
                                                "Timestamp": datetime.now().isoformat(),
                                                "Details": f"Added {add_roll_count} roll(s) of {item_data['Material'][:30]}... at {add_roll_footage} ft each. IDs: {', '.join(new_ids[:3])}{'...' if len(new_ids) > 3 else ''}. Reason: {add_roll_reason}"
                                            }
                                            supabase.table("audit_log").insert(log_entry).execute()
                                            
                                            st.success(f"✅ Added {add_roll_count} roll(s)")
                                            st.cache_data.clear()
                                            st.session_state.force_refresh = True
                                            time.sleep(1)
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ Failed: {e}")
                            
                            # ── Remove rolls ──
                            with roll_op3:
                                st.markdown("**Remove rolls of this material**")
                                st.warning("⚠️ This will permanently delete selected rolls from inventory")
                                
                                # Let user select which rolls to remove
                                roll_options = same_material_rolls['Item_ID'].tolist()
                                
                                rolls_to_remove = st.multiselect(
                                    "Select roll(s) to remove",
                                    options=roll_options,
                                    key="rolls_to_remove",
                                    help="Select one or more rolls to delete"
                                )
                                
                                if rolls_to_remove:
                                    # Show what will be removed
                                    remove_df = same_material_rolls[same_material_rolls['Item_ID'].isin(rolls_to_remove)]
                                    total_footage_removing = remove_df['Footage'].sum()
                                    
                                    st.markdown(f"**Removing {len(rolls_to_remove)} roll(s):**")
                                    st.dataframe(
                                        remove_df[['Item_ID', 'Footage', 'Location']],
                                        use_container_width=True,
                                        hide_index=True
                                    )
                                    st.error(f"🗑️ Total footage to remove: {total_footage_removing:,.1f} ft")
                                    
                                    with st.form("remove_rolls_form"):
                                        remove_reason = st.text_input(
                                            "Reason for removal *",
                                            placeholder="e.g. Damaged, sold externally, inventory correction",
                                            key="remove_rolls_reason"
                                        )
                                        
                                        confirm_remove = st.checkbox(
                                            f"I confirm I want to permanently delete {len(rolls_to_remove)} roll(s)",
                                            key="confirm_remove_rolls"
                                        )
                                        
                                        submit_remove_rolls = st.form_submit_button("🗑️ Remove Selected Rolls", type="primary", use_container_width=True)
                                    
                                    if submit_remove_rolls:
                                        if not remove_reason.strip():
                                            st.error("⚠️ Please provide a reason")
                                        elif not confirm_remove:
                                            st.error("⚠️ Please confirm the removal")
                                        else:
                                            try:
                                                # Log before deleting
                                                log_entry = {
                                                    "Item_ID": item_data['Material'][:30],
                                                    "Action": "Admin - Removed Rolls",
                                                    "User": st.session_state.get('username', 'Admin'),
                                                    "Timestamp": datetime.now().isoformat(),
                                                    "Details": f"Removed {len(rolls_to_remove)} roll(s): {', '.join(rolls_to_remove[:5])}{'...' if len(rolls_to_remove) > 5 else ''} ({total_footage_removing:,.1f} ft total). Reason: {remove_reason}"
                                                }
                                                supabase.table("audit_log").insert(log_entry).execute()
                                                
                                                # Delete the rolls
                                                for roll_id in rolls_to_remove:
                                                    supabase.table("inventory").delete().eq("Item_ID", roll_id).execute()
                                                
                                                st.success(f"✅ Removed {len(rolls_to_remove)} roll(s)")
                                                st.cache_data.clear()
                                                st.session_state.force_refresh = True
                                                time.sleep(1)
                                                st.rerun()
                                            except Exception as e:
                                                st.error(f"❌ Failed: {e}")
                                else:
                                    st.info("👆 Select rolls above to remove them")
                        
                        elif item_category == "Coils":
                            st.info("🔄 **Coil Inventory** - Edit footage for this coil")
                            
                            with st.form("edit_coil_form", clear_on_submit=True):
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    new_footage = st.number_input(
                                        "New Footage Value",
                                        min_value=0.0,
                                        value=current_footage,
                                        step=50.0,
                                        key="new_footage_input",
                                        help="Total footage remaining on this coil"
                                    )
                                
                                with col2:
                                    footage_diff = new_footage - current_footage
                                    if footage_diff > 0:
                                        st.success(f"📈 Adding {footage_diff:.1f} ft")
                                    elif footage_diff < 0:
                                        st.warning(f"📉 Removing {abs(footage_diff):.1f} ft")
                                    else:
                                        st.info("No change")
                                
                                footage_reason = st.text_input(
                                    "Reason for Change *",
                                    placeholder="e.g. Physical count adjustment, damaged material",
                                    key="footage_reason"
                                )
                                
                                submit_footage = st.form_submit_button("💾 Update Footage", type="primary", use_container_width=True)
                            
                            if submit_footage:
                                if not footage_reason.strip():
                                    st.error("⚠️ Please provide a reason for the change.")
                                else:
                                    try:
                                        supabase.table("inventory").update({
                                            "Footage": new_footage
                                        }).eq("Item_ID", selected_item).execute()
                                        
                                        log_entry = {
                                            "Item_ID": selected_item,
                                            "Action": "Admin Edit - Footage",
                                            "User": st.session_state.get('username', 'Admin'),
                                            "Timestamp": datetime.now().isoformat(),
                                            "Details": f"Changed footage from {current_footage:.1f} to {new_footage:.1f} ft. Reason: {footage_reason}"
                                        }
                                        supabase.table("audit_log").insert(log_entry).execute()
                                        
                                        st.success(f"✅ Footage updated: {current_footage:.1f} → {new_footage:.1f} ft")
                                        st.cache_data.clear()
                                        st.session_state.force_refresh = True
                                        time.sleep(1)
                                        st.rerun()
                                        
                                    except Exception as e:
                                        st.error(f"❌ Failed to update: {e}")
                        
                        elif item_category in ["Elbows", "Fab Straps", "Wing Seals"]:
                            st.info(f"📦 **{item_category}** - Edit piece count")
                            
                            with st.form("edit_pieces_form", clear_on_submit=True):
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    new_qty = st.number_input(
                                        "Quantity (pieces)",
                                        min_value=0,
                                        value=int(current_footage),
                                        step=1,
                                        key="new_qty_input",
                                        help=f"Number of {item_category.lower()} in stock"
                                    )
                                
                                with col2:
                                    qty_diff = new_qty - int(current_footage)
                                    if qty_diff > 0:
                                        st.success(f"📈 Adding {qty_diff} pcs")
                                    elif qty_diff < 0:
                                        st.warning(f"📉 Removing {abs(qty_diff)} pcs")
                                    else:
                                        st.info("No change")
                                
                                qty_reason = st.text_input(
                                    "Reason for Change *",
                                    placeholder="e.g. Physical count, used in production",
                                    key="qty_reason"
                                )
                                
                                submit_qty = st.form_submit_button("💾 Update Quantity", type="primary", use_container_width=True)
                            
                            if submit_qty:
                                if not qty_reason.strip():
                                    st.error("⚠️ Please provide a reason for the change.")
                                else:
                                    try:
                                        supabase.table("inventory").update({
                                            "Footage": float(new_qty)
                                        }).eq("Item_ID", selected_item).execute()
                                        
                                        log_entry = {
                                            "Item_ID": selected_item,
                                            "Action": "Admin Edit - Quantity",
                                            "User": st.session_state.get('username', 'Admin'),
                                            "Timestamp": datetime.now().isoformat(),
                                            "Details": f"Changed quantity from {int(current_footage)} to {new_qty} pcs. Reason: {qty_reason}"
                                        }
                                        supabase.table("audit_log").insert(log_entry).execute()
                                        
                                        st.success(f"✅ Quantity updated: {int(current_footage)} → {new_qty} pcs")
                                        st.cache_data.clear()
                                        st.session_state.force_refresh = True
                                        time.sleep(1)
                                        st.rerun()
                                        
                                    except Exception as e:
                                        st.error(f"❌ Failed to update: {e}")
                        
                        else:
                            # Generic fallback for other categories
                            st.info(f"📦 **{item_category}** - Edit quantity/footage")
                            
                            with st.form("edit_generic_form", clear_on_submit=True):
                                col1, col2 = st.columns(2)
                                
                                with col1:
                                    new_value = st.number_input(
                                        "Quantity/Footage",
                                        min_value=0.0,
                                        value=current_footage,
                                        step=1.0,
                                        key="new_value_input"
                                    )
                                
                                with col2:
                                    diff = new_value - current_footage
                                    if diff > 0:
                                        st.success(f"📈 Adding {diff:.1f}")
                                    elif diff < 0:
                                        st.warning(f"📉 Removing {abs(diff):.1f}")
                                    else:
                                        st.info("No change")
                                
                                generic_reason = st.text_input(
                                    "Reason for Change *",
                                    placeholder="e.g. Inventory adjustment",
                                    key="generic_reason"
                                )
                                
                                submit_generic = st.form_submit_button("💾 Update", type="primary", use_container_width=True)
                            
                            if submit_generic:
                                if not generic_reason.strip():
                                    st.error("⚠️ Please provide a reason for the change.")
                                else:
                                    try:
                                        supabase.table("inventory").update({
                                            "Footage": new_value
                                        }).eq("Item_ID", selected_item).execute()
                                        
                                        log_entry = {
                                            "Item_ID": selected_item,
                                            "Action": "Admin Edit - Quantity",
                                            "User": st.session_state.get('username', 'Admin'),
                                            "Timestamp": datetime.now().isoformat(),
                                            "Details": f"Changed from {current_footage:.1f} to {new_value:.1f}. Reason: {generic_reason}"
                                        }
                                        supabase.table("audit_log").insert(log_entry).execute()
                                        
                                        st.success(f"✅ Updated: {current_footage:.1f} → {new_value:.1f}")
                                        st.cache_data.clear()
                                        st.session_state.force_refresh = True
                                        time.sleep(1)
                                        st.rerun()
                                        
                                    except Exception as e:
                                        st.error(f"❌ Failed to update: {e}")
                                        
                    # ── Edit Location Tab ───────────────────────────────────────────
                    with edit_tab3:
                        st.markdown("#### 📍 Move Item to New Location")
                        
                        with st.form("edit_location_form", clear_on_submit=True):
                            
                            loc_type = st.radio(
                                "🏢 Storage Type",
                                ["Rack System", "Floor / Open Space"],
                                horizontal=True,
                                key="edit_loc_type"
                            )
                            
                            if loc_type == "Rack System":
                                col1, col2, col3 = st.columns(3)
                                bay = col1.number_input("🅱️ Bay", min_value=1, value=1, key="edit_rack_bay")
                                sec = col2.selectbox("🔤 Section", list("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), key="edit_rack_sec")
                                lvl = col3.number_input("⬆️ Level", min_value=1, value=1, key="edit_rack_lvl")
                                new_location = f"{bay}{sec}{lvl}"
                            else:
                                col1, col2, col3 = st.columns(3)
                                bay = col1.number_input("🅱️ Bay", min_value=1, value=1, key="edit_floor_bay")
                                floor_options = [f"Floor {letter}" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]
                                floor_selection = col2.selectbox("🔤 Floor Section", floor_options, key="edit_floor_sec")
                                lvl = col3.number_input("⬆️ Level", min_value=1, value=1, key="edit_floor_lvl")
                                new_location = f"{bay}-{floor_selection}-{lvl}"
                            
                            st.info(f"📍 **New Location:** {new_location} (Currently: {item_data['Location']})")
                            
                            location_reason = st.text_input(
                                "Reason for Move *",
                                placeholder="e.g. Reorganizing warehouse, better accessibility, consolidation",
                                key="location_reason"
                            )
                            
                            submit_location = st.form_submit_button("📍 Update Location", type="primary", use_container_width=True)
                        
                        if submit_location:
                            if not location_reason.strip():
                                st.error("⚠️ Please provide a reason for the move.")
                            else:
                                try:
                                    # Update location in database
                                    supabase.table("inventory").update({
                                        "Location": new_location
                                    }).eq("Item_ID", selected_item).execute()
                                    
                                    # Log the change
                                    log_entry = {
                                        "Item_ID": selected_item,
                                        "Action": "Admin Edit - Location",
                                        "User": st.session_state.get('username', 'Admin'),
                                        "Timestamp": datetime.now().isoformat(),
                                        "Details": f"Moved from {item_data['Location']} to {new_location}. Reason: {location_reason}"
                                    }
                                    supabase.table("audit_log").insert(log_entry).execute()
                                    
                                    st.success(f"✅ Location updated: {item_data['Location']} → {new_location}")
                                    st.cache_data.clear()
                                    time.sleep(1)
                                    st.rerun()
                                    
                                except Exception as e:
                                    st.error(f"❌ Failed to update: {e}")
                    
                    # ── Remove Item Tab ─────────────────────────────────────────────
                    with edit_tab4:
                        st.markdown("#### 🗑️ Permanently Remove Item")
                        
                        st.error("⚠️ **Warning:** This action cannot be undone!")
                        
                        with st.form("remove_item_form"):
                            st.markdown(f"""
                                <div style="background: #fef2f2; padding: 15px; border-radius: 8px; border-left: 4px solid #dc2626;">
                                    <strong>🚨 You are about to permanently delete:</strong><br><br>
                                    <table style="width: 100%;">
                                        <tr><td><strong>Item ID:</strong></td><td>{selected_item}</td></tr>
                                        <tr><td><strong>Material:</strong></td><td>{item_data['Material']}</td></tr>
                                        <tr><td><strong>Footage:</strong></td><td>{item_data['Footage']}</td></tr>
                                        <tr><td><strong>Location:</strong></td><td>{item_data['Location']}</td></tr>
                                    </table>
                                </div>
                            """, unsafe_allow_html=True)
                            
                            removal_reason = st.text_input(
                                "Reason for Removal *",
                                placeholder="e.g. Damaged beyond use, incorrect entry, sold externally",
                                key="removal_reason"
                            )
                            
                            confirm_text = st.text_input(
                                f"Type '{selected_item}' to confirm deletion",
                                placeholder="Type the Item ID exactly to confirm",
                                key="confirm_delete_text"
                            )
                            
                            submit_remove = st.form_submit_button("🗑️ Permanently Remove Item", type="primary", use_container_width=True)
                        
                        if submit_remove:
                            if not removal_reason.strip():
                                st.error("⚠️ Please provide a reason for removal.")
                            elif confirm_text != selected_item:
                                st.error(f"⚠️ Please type '{selected_item}' exactly to confirm deletion.")
                            else:
                                try:
                                    # Log BEFORE deleting
                                    log_entry = {
                                        "Item_ID": selected_item,
                                        "Action": "Admin - Item Removed",
                                        "User": st.session_state.get('username', 'Admin'),
                                        "Timestamp": datetime.now().isoformat(),
                                        "Details": f"Permanently removed {selected_item} ({item_data['Material']}, {item_data['Footage']} ft at {item_data['Location']}). Reason: {removal_reason}"
                                    }
                                    supabase.table("audit_log").insert(log_entry).execute()
                                    
                                    # Delete from database
                                    supabase.table("inventory").delete().eq("Item_ID", selected_item).execute()
                                    
                                    st.success(f"✅ Item {selected_item} has been permanently removed.")
                                    st.cache_data.clear()
                                    time.sleep(1)
                                    st.rerun()
                                    
                                except Exception as e:
                                    st.error(f"❌ Failed to remove: {e}")
            
            else:
                st.info("🔍 No items match your search criteria.")
        
        else:
            st.info("📦 No inventory to manage yet. Add items in the Receive tab first.")
                    
import openai
import plotly.express as px
import plotly.graph_objects as go

with tab6:
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h1 style="color: #7c3aed; margin: 0;">📈 Inventory Analytics & AI Insights</h1>
            <p style="color: #64748b; margin-top: 8px;">Real-time analytics and intelligent recommendations powered by AI</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Configure Grok AI (xAI) with better error handling
    GROK_API_KEY = st.secrets.get("GROK_API_KEY", "")
    ai_configured = False
    
    # Debug info (remove after testing)
    with st.expander("🔧 API Configuration Debug", expanded=False):
        if GROK_API_KEY:
            st.write(f"✅ Key found: `{GROK_API_KEY[:10]}...`")
            st.write(f"Key starts with 'xai-': {GROK_API_KEY.startswith('xai-')}")
        else:
            st.error("❌ No GROK_API_KEY found in secrets")
            st.code("""
# Add to .streamlit/secrets.toml:
GROK_API_KEY = "xai-your-key-here"
            """)
    
    if GROK_API_KEY and GROK_API_KEY.startswith("xai-"):
        try:
            import openai
            
            # Configure for Grok API
            grok_client = openai.OpenAI(
                api_key=GROK_API_KEY,
                base_url="https://api.x.ai/v1"
            )
            ai_configured = True
        except ImportError:
            st.error("❌ OpenAI library not installed. Add 'openai' to requirements.txt")
            ai_configured = False
        except Exception as e:
            st.warning(f"⚠️ AI Configuration Issue: {e}")
            ai_configured = False
    else:
        if GROK_API_KEY:
            st.warning("⚠️ API Key format looks incorrect. Grok keys should start with 'xai-'")
        else:
            st.info("💡 Add GROK_API_KEY to your secrets to enable AI features")
    
    if not df.empty:
        # ── Analytics Dashboard ─────────────────────────────────────────────────
        st.markdown("### 📊 Warehouse Overview")
        
        # Key Metrics Cards
        col1, col2, col3, col4 = st.columns(4)
        
        total_footage = df['Footage'].sum()
        total_items = len(df)
        total_categories = df['Category'].nunique()
        active_items = len(df[df['Status'] == 'Active'])
        
        with col1:
            st.markdown("""
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                            padding: 20px; border-radius: 12px; text-align: center; color: white;">
                    <h3 style="margin: 0; font-size: 32px; font-weight: bold;">{:,.0f}</h3>
                    <p style="margin: 8px 0 0 0; font-size: 14px; opacity: 0.9;">Total Footage</p>
                </div>
            """.format(total_footage), unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
                <div style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%); 
                            padding: 20px; border-radius: 12px; text-align: center; color: white;">
                    <h3 style="margin: 0; font-size: 32px; font-weight: bold;">{}</h3>
                    <p style="margin: 8px 0 0 0; font-size: 14px; opacity: 0.9;">Total Items</p>
                </div>
            """.format(total_items), unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
                <div style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%); 
                            padding: 20px; border-radius: 12px; text-align: center; color: white;">
                    <h3 style="margin: 0; font-size: 32px; font-weight: bold;">{}</h3>
                    <p style="margin: 8px 0 0 0; font-size: 14px; opacity: 0.9;">Categories</p>
                </div>
            """.format(total_categories), unsafe_allow_html=True)
        
        with col4:
            st.markdown("""
                <div style="background: linear-gradient(135deg, #43e97b 0%, #38f9d7 100%); 
                            padding: 20px; border-radius: 12px; text-align: center; color: white;">
                    <h3 style="margin: 0; font-size: 32px; font-weight: bold;">{}</h3>
                    <p style="margin: 8px 0 0 0; font-size: 14px; opacity: 0.9;">Active Items</p>
                </div>
            """.format(active_items), unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # ── Capacity Gauge ──────────────────────────────────────────────────────
        st.markdown("### 📏 Warehouse Capacity")
        
        with st.container():
            st.markdown("""
                <div style="background: linear-gradient(135deg, #ffecd2 0%, #fcb69f 100%); 
                            padding: 24px; border-radius: 12px; border-left: 4px solid #f97316;">
            """, unsafe_allow_html=True)
            
            target_capacity = 50000.0
            utilization_pct = (total_footage / target_capacity) * 100
            
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number+delta",
                value=total_footage,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': "Total Warehouse Footage", 'font': {'size': 20, 'color': '#1e293b'}},
                delta={'reference': target_capacity * 0.8, 'increasing': {'color': "#dc2626"}},
                gauge={
                    'axis': {'range': [None, target_capacity], 'tickwidth': 1, 'tickcolor': "#64748b"},
                    'bar': {'color': "#7c3aed"},
                    'bgcolor': "white",
                    'borderwidth': 2,
                    'bordercolor': "#e2e8f0",
                    'steps': [
                        {'range': [0, target_capacity * 0.5], 'color': '#dcfce7'},
                        {'range': [target_capacity * 0.5, target_capacity * 0.8], 'color': '#fef9c3'},
                        {'range': [target_capacity * 0.8, target_capacity], 'color': '#fee2e2'}
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': target_capacity * 0.9
                    }
                }
            ))
            
            fig_gauge.update_layout(
                height=300,
                margin=dict(l=20, r=20, t=60, b=20),
                paper_bgcolor='rgba(0,0,0,0)',
                font={'color': "#1e293b", 'family': "Arial"}
            )
            
            st.plotly_chart(fig_gauge, use_container_width=True)
            
            # Capacity warning
            if utilization_pct > 90:
                st.error(f"⚠️ **Critical:** Warehouse at {utilization_pct:.1f}% capacity!")
            elif utilization_pct > 80:
                st.warning(f"⚠️ **Warning:** Warehouse at {utilization_pct:.1f}% capacity")
            else:
                st.success(f"✅ **Healthy:** Warehouse at {utilization_pct:.1f}% capacity")
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # ── Visual Analytics (Flexible & User-Controlled) ──────────────────────
        st.markdown("### 📊 Custom Analytics Dashboard")
        st.caption("Customize your view to focus on what matters most")
        
        # Analytics Control Panel
        with st.expander("⚙️ Customize Analytics View", expanded=False):
            col_ctrl1, col_ctrl2 = st.columns(2)
            
            with col_ctrl1:
                chart1_metric = st.selectbox(
                    "📈 Left Chart - Group By:",
                    ["Category", "Location", "Status", "Material Type"],
                    key="chart1_metric"
                )
                chart1_type = st.radio(
                    "Chart Type:",
                    ["Pie Chart", "Bar Chart", "Treemap"],
                    horizontal=True,
                    key="chart1_type"
                )
            
            with col_ctrl2:
                chart2_metric = st.selectbox(
                    "📊 Right Chart - Show:",
                    ["Top 10 Materials", "Items by Location", "Low Stock Alert", 
                     "Recent Activity", "PO Summary", "Top 10 Clients", "Material Velocity"],
                    key="chart2_metric"
                )
                show_value = st.checkbox("Show exact values on charts", value=True)
        
        col1, col2 = st.columns(2)
        
        # ── LEFT CHART (Dynamic) ────────────────────────────────────────────────
        with col1:
            st.markdown("""
                <div style="background: white; padding: 20px; border-radius: 12px; 
                            box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            """, unsafe_allow_html=True)
            
            # Prepare data based on selection
            if chart1_metric == "Category":
                chart1_data = df.groupby('Category')['Footage'].sum().reset_index()
                chart1_title = "Inventory by Category"
                names_col, values_col = 'Category', 'Footage'
            
            elif chart1_metric == "Location":
                chart1_data = df.groupby('Location')['Footage'].sum().nlargest(10).reset_index()
                chart1_title = "Top 10 Locations by Footage"
                names_col, values_col = 'Location', 'Footage'
            
            elif chart1_metric == "Status":
                chart1_data = df.groupby('Status')['Footage'].sum().reset_index()
                chart1_title = "Inventory by Status"
                names_col, values_col = 'Status', 'Footage'
            
            else:  # Material Type
                # Extract material type (e.g., "Aluminum" from "Smooth Aluminum Coil")
                df['Material_Type'] = df['Material'].str.extract(r'(Aluminum|Stainless Steel|Galvanized|Steel)')[0].fillna('Other')
                chart1_data = df.groupby('Material_Type')['Footage'].sum().reset_index()
                chart1_title = "Inventory by Material Type"
                names_col, values_col = 'Material_Type', 'Footage'
            
            st.markdown(f"<h4 style='color: #1e293b; margin-top: 0;'>{chart1_title}</h4>", unsafe_allow_html=True)
            
            # Render selected chart type
            if chart1_type == "Pie Chart":
                fig1 = px.pie(
                    chart1_data, 
                    names=names_col, 
                    values=values_col, 
                    hole=0.5,
                    color_discrete_sequence=px.colors.qualitative.Bold
                )
                fig1.update_traces(
                    textposition='inside', 
                    textinfo='percent+label' if show_value else 'label',
                    hovertemplate=f'<b>%{{label}}</b><br>Footage: %{{value:,.0f}}<br>Percent: %{{percent}}<extra></extra>'
                )
            
            elif chart1_type == "Bar Chart":
                fig1 = px.bar(
                    chart1_data.sort_values(values_col, ascending=True).tail(10),
                    x=values_col,
                    y=names_col,
                    orientation='h',
                    color=names_col,
                    color_discrete_sequence=px.colors.qualitative.Bold
                )
                fig1.update_traces(
                    texttemplate='%{x:,.0f}' if show_value else None,
                    textposition='outside',
                    hovertemplate=f'<b>%{{y}}</b><br>Footage: %{{x:,.0f}}<extra></extra>'
                )
            
            else:  # Treemap
                fig1 = px.treemap(
                    chart1_data,
                    path=[names_col],
                    values=values_col,
                    color=values_col,
                    color_continuous_scale='Blues'
                )
                fig1.update_traces(
                    texttemplate='<b>%{label}</b><br>%{value:,.0f} ft' if show_value else '<b>%{label}</b>',
                    hovertemplate='<b>%{label}</b><br>Footage: %{value:,.0f}<extra></extra>'
                )
            
            fig1.update_layout(
                margin=dict(l=20, r=20, t=20, b=20),
                height=400,
                showlegend=chart1_type != "Treemap"
            )
            
            st.plotly_chart(fig1, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
        
        # ── RIGHT CHART (Dynamic) ───────────────────────────────────────────────
        with col2:
            st.markdown("""
                <div style="background: white; padding: 20px; border-radius: 12px; 
                            box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            """, unsafe_allow_html=True)
            
            if chart2_metric == "Top 10 Materials":
                mat_sum = df.groupby(['Material', 'Category'])['Footage'].sum().nlargest(10).reset_index()
                st.markdown("<h4 style='color: #1e293b; margin-top: 0;'>Top 10 Materials by Stock</h4>", unsafe_allow_html=True)
                
                fig2 = px.bar(
                    mat_sum.sort_values('Footage'),
                    x='Footage', 
                    y='Material', 
                    orientation='h', 
                    color='Category',
                    color_discrete_sequence=px.colors.qualitative.Bold
                )
                fig2.update_traces(
                    texttemplate='%{x:,.0f}' if show_value else None,
                    textposition='outside',
                    hovertemplate='<b>%{y}</b><br>Footage: %{x:,.0f}<br>Category: %{fullData.name}<extra></extra>'
                )
                fig2.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=400)
                st.plotly_chart(fig2, use_container_width=True)
            
            elif chart2_metric == "Items by Location":
                loc_sum = df.groupby('Location').agg({'Item_ID': 'count', 'Footage': 'sum'}).reset_index()
                loc_sum.columns = ['Location', 'Item_Count', 'Total_Footage']
                loc_sum = loc_sum.nlargest(10, 'Total_Footage')
                
                st.markdown("<h4 style='color: #1e293b; margin-top: 0;'>Busiest Storage Locations</h4>", unsafe_allow_html=True)
                
                fig2 = px.scatter(
                    loc_sum,
                    x='Item_Count',
                    y='Total_Footage',
                    size='Total_Footage',
                    color='Location',
                    hover_data=['Location'],
                    color_discrete_sequence=px.colors.qualitative.Bold
                )
                fig2.update_traces(
                    hovertemplate='<b>%{customdata[0]}</b><br>Items: %{x}<br>Footage: %{y:,.0f}<extra></extra>'
                )
                fig2.update_layout(
                    margin=dict(l=20, r=20, t=20, b=20),
                    height=400,
                    xaxis_title="Number of Items",
                    yaxis_title="Total Footage"
                )
                st.plotly_chart(fig2, use_container_width=True)
            
            elif chart2_metric == "Low Stock Alert":
                st.markdown("<h4 style='color: #1e293b; margin-top: 0;'>⚠️ Low Stock Items</h4>", unsafe_allow_html=True)
                
                # Define low stock threshold by category
                low_stock_threshold = {
                    'Coils': 5000,
                    'Rolls': 1000,
                    'Elbows': 50,
                    'Fab Straps': 100,
                    'Mineral Wool': 50,
                    'Wing Seals': 500,
                    'Wire': 200,
                    'Banding': 500
                }
                
                low_stock_items = []
                for cat, threshold in low_stock_threshold.items():
                    cat_data = df[df['Category'] == cat].groupby('Material')['Footage'].sum()
                    low_items = cat_data[cat_data < threshold]
                    for material, footage in low_items.items():
                        low_stock_items.append({
                            'Category': cat,
                            'Material': material,
                            'Current_Stock': footage,
                            'Threshold': threshold,
                            'Shortage': threshold - footage
                        })
                
                if low_stock_items:
                    low_df = pd.DataFrame(low_stock_items).nlargest(10, 'Shortage')
                    
                    fig2 = px.bar(
                        low_df,
                        x='Shortage',
                        y='Material',
                        orientation='h',
                        color='Category',
                        color_discrete_sequence=px.colors.qualitative.Set1,
                        hover_data=['Current_Stock', 'Threshold']
                    )
                    fig2.update_traces(
                        hovertemplate='<b>%{y}</b><br>Shortage: %{x:,.0f}<br>Current: %{customdata[0]:,.0f}<br>Target: %{customdata[1]:,.0f}<extra></extra>'
                    )
                    fig2.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=400)
                    st.plotly_chart(fig2, use_container_width=True)
                    
                    st.warning(f"⚠️ {len(low_stock_items)} items below threshold!")
                else:
                    st.success("✅ All items above minimum stock levels!")
                    st.markdown("<div style='height: 300px; display: flex; align-items: center; justify-content: center;'><h3 style='color: #64748b;'>No low stock alerts</h3></div>", unsafe_allow_html=True)
            
            elif chart2_metric == "Recent Activity":
                st.markdown("<h4 style='color: #1e293b; margin-top: 0;'>📅 Recent Inventory Changes</h4>", unsafe_allow_html=True)
                
                try:
                    # Fetch recent audit logs
                    recent_logs = supabase.table("audit_log").select("*").order("Timestamp", desc=True).limit(10).execute()
                    
                    if recent_logs.data:
                        for log in recent_logs.data:
                            action_color = "#16a34a" if log['Action'] == "Received" else "#dc2626"
                            st.markdown(f"""
                                <div style="padding: 12px; margin: 8px 0; background: #f9fafb; border-radius: 8px; border-left: 4px solid {action_color};">
                                    <div style="display: flex; justify-content: space-between;">
                                        <strong style="color: {action_color};">{log['Action']}</strong>
                                        <span style="color: #64748b; font-size: 12px;">{log.get('Timestamp', 'N/A')[:16]}</span>
                                    </div>
                                    <div style="color: #1e293b; margin-top: 4px;">{log.get('Details', 'No details')}</div>
                                    <div style="color: #64748b; font-size: 12px; margin-top: 4px;">By: {log.get('User', 'Unknown')}</div>
                                </div>
                            """, unsafe_allow_html=True)
                    else:
                        st.info("No recent activity recorded")
                except Exception as e:
                    st.error(f"Could not load activity: {e}")
            
            else:  # PO Summary
                st.markdown("<h4 style='color: #1e293b; margin-top: 0;'>📦 Purchase Order Summary</h4>", unsafe_allow_html=True)
                
                po_data = df[df['Purchase_Order_Num'].notna()].groupby('Purchase_Order_Num').agg({
                    'Item_ID': 'count',
                    'Footage': 'sum',
                    'Category': lambda x: ', '.join(x.unique()[:3])
                }).reset_index()
                po_data.columns = ['PO_Number', 'Items', 'Total_Footage', 'Categories']
                po_data = po_data.nlargest(10, 'Total_Footage')
                
                if not po_data.empty:
                    fig2 = px.bar(
                        po_data.sort_values('Total_Footage'),
                        x='Total_Footage',
                        y='PO_Number',
                        orientation='h',
                        color='Items',
                        color_continuous_scale='Viridis',
                        hover_data=['Categories']
                    )
                    fig2.update_traces(
                        hovertemplate='<b>%{y}</b><br>Footage: %{x:,.0f}<br>Items: %{marker.color}<br>Categories: %{customdata[0]}<extra></extra>'
                    )
                    fig2.update_layout(margin=dict(l=20, r=20, t=20, b=20), height=400)
                    st.plotly_chart(fig2, use_container_width=True)
                else:
                    st.info("No PO data available")
            
            # ── NEW: Top 10 Clients ────────────────────────────────────────────
            if chart2_metric == "Top 10 Clients":
                st.markdown("<h4 style='color: #1e293b; margin-top: 0;'>👥 Top 10 Clients by Sales</h4>", unsafe_allow_html=True)
                
                try:
                    # Fetch sales data from audit logs
                    sales_logs = supabase.table("audit_log").select("*").ilike("Action", "%Sold%").execute()
                    
                    if sales_logs.data:
                        clients_data = []
                        for log in sales_logs.data:
                            details = log.get('Details', '')
                            # Extract client name from details like "Removed X for ClientName (SO: ...)"
                            if 'for ' in details and ' (SO:' in details:
                                client = details.split('for ')[1].split(' (SO:')[0].strip()
                                # Extract quantity
                                if 'Removed' in details:
                                    qty_str = details.split('Removed ')[1].split(' ')[0]
                                    try:
                                        qty = float(qty_str)
                                        clients_data.append({'Client': client, 'Quantity': qty})
                                    except:
                                        pass
                        
                        if clients_data:
                            clients_df = pd.DataFrame(clients_data)
                            top_clients = clients_df.groupby('Client')['Quantity'].sum().nlargest(10).reset_index()
                            top_clients.columns = ['Client', 'Total_Sold']
                            
                            fig2 = px.bar(
                                top_clients.sort_values('Total_Sold'),
                                x='Total_Sold',
                                y='Client',
                                orientation='h',
                                color='Total_Sold',
                                color_continuous_scale='Sunset',
                                text='Total_Sold' if show_value else None
                            )
                            fig2.update_traces(
                                texttemplate='%{text:,.0f}' if show_value else None,
                                textposition='outside',
                                hovertemplate='<b>%{y}</b><br>Total Sold: %{x:,.0f} units<extra></extra>'
                            )
                            fig2.update_layout(
                                margin=dict(l=20, r=20, t=20, b=20),
                                height=400,
                                showlegend=False
                            )
                            st.plotly_chart(fig2, use_container_width=True)
                            
                            # Show stats
                            total_sales = top_clients['Total_Sold'].sum()
                            st.metric("Total Sales (Top 10)", f"{total_sales:,.0f} units")
                        else:
                            st.info("No client sales data found")
                    else:
                        st.info("No sales records available")
                except Exception as e:
                    st.error(f"Could not load client data: {e}")
            
            # ── NEW: Material Velocity (How fast items move) ───────────────────
            elif chart2_metric == "Material Velocity":
                st.markdown("<h4 style='color: #1e293b; margin-top: 0;'>⚡ Material Turnover Rate</h4>", unsafe_allow_html=True)
                
                try:
                    # Get sales activity from last 30 days
                    from datetime import timedelta
                    thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
                    
                    velocity_logs = supabase.table("audit_log").select("*").ilike("Action", "%Removed%").gte("Timestamp", thirty_days_ago).execute()
                    
                    if velocity_logs.data:
                        material_moves = {}
                        for log in velocity_logs.data:
                            details = log.get('Details', '')
                            # Extract quantity and material
                            if 'Removed' in details:
                                parts = details.split('(')
                                if len(parts) > 0:
                                    item_info = parts[0]
                                    # Try to extract quantity
                                    try:
                                        qty = float(item_info.split('Removed ')[1].split(' ')[0])
                                        # Get material type
                                        for cat in ['Coil', 'Roll', 'Elbow', 'Fab Strap', 'Mineral Wool']:
                                            if cat in item_info:
                                                material_moves[cat] = material_moves.get(cat, 0) + qty
                                    except:
                                        pass
                        
                        if material_moves:
                            velocity_df = pd.DataFrame(list(material_moves.items()), columns=['Material', 'Units_Moved'])
                            velocity_df = velocity_df.sort_values('Units_Moved', ascending=True)
                            
                            fig2 = px.bar(
                                velocity_df,
                                x='Units_Moved',
                                y='Material',
                                orientation='h',
                                color='Units_Moved',
                                color_continuous_scale='Turbo',
                                text='Units_Moved' if show_value else None
                            )
                            fig2.update_traces(
                                texttemplate='%{text:,.0f}' if show_value else None,
                                textposition='outside',
                                hovertemplate='<b>%{y}</b><br>Moved in 30 days: %{x:,.0f} units<extra></extra>'
                            )
                            fig2.update_layout(
                                margin=dict(l=20, r=20, t=20, b=20),
                                height=400,
                                showlegend=False
                            )
                            st.plotly_chart(fig2, use_container_width=True)
                            
                            st.caption("📊 Units sold/removed in the last 30 days")
                        else:
                            st.info("No movement data in last 30 days")
                    else:
                        st.info("No recent activity to analyze")
                except Exception as e:
                    st.error(f"Could not calculate velocity: {e}")
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # ── AI Assistant Section ────────────────────────────────────────────────
        st.markdown("""
            <div style="text-align: center; padding: 20px 0;">
                <h2 style="color: #7c3aed; margin: 0;">🤖 MJP Pulse AI Assistant</h2>
                <p style="color: #64748b; margin-top: 8px;">Ask intelligent questions about your inventory</p>
            </div>
        """, unsafe_allow_html=True)
        
        # Show AI status
        if ai_configured:
            st.success("✅ AI Assistant is ready!", icon="🤖")
        else:
            st.warning("⚠️ AI Assistant not configured - see instructions below", icon="⚙️")
        
        with st.container():
            st.markdown("""
                <div style="background: linear-gradient(135deg, #e0e7ff 0%, #f3e8ff 100%); 
                            padding: 30px; border-radius: 12px; border-left: 4px solid #7c3aed;">
            """, unsafe_allow_html=True)
            
            # Example questions
            st.markdown("**💡 Example Questions:**")
            examples = [
                "What items are running low and need reordering?",
                "Show me a summary of all Coils in stock",
                "Which category has the most inventory?",
                "What's the total value of Aluminum items?",
                "Recommend optimal reorder quantities"
            ]
            
            cols = st.columns(3)
            for idx, example in enumerate(examples):
                with cols[idx % 3]:
                    if st.button(f"💬 {example}", key=f"example_{idx}", use_container_width=True):
                        st.session_state.ai_question = example
            
            st.markdown("<br>", unsafe_allow_html=True)
            
            # User input
            user_q = st.text_area(
                "✍️ Your Question:",
                value=st.session_state.get('ai_question', ''),
                placeholder="e.g., What materials need reordering based on current stock levels?",
                height=100,
                key="ai_input_final"
            )
            
            if st.button("🚀 Ask AI Assistant", type="primary", use_container_width=True):
                if not user_q:
                    st.warning("⚠️ Please enter a question!")
                elif not ai_configured:
                    st.error("⚠️ AI Assistant is not configured. Please check your API key.")
                    st.markdown("""
                    **🔧 Setup Instructions for Grok:**
                    1. Go to [xAI Console](https://console.x.ai/)
                    2. Sign in and navigate to API Keys
                    3. Click "Create API Key"
                    4. Copy the key (starts with `xai-...`)
                    5. Add to Streamlit secrets as `GROK_API_KEY`
                    
                    **In `.streamlit/secrets.toml`:**
                    ```toml
                    GROK_API_KEY = "xai-..."
                    ```
                    
                    **Or in Streamlit Cloud:**
                    - Go to App Settings → Secrets
                    - Add: `GROK_API_KEY = "xai-..."`
                    """)
                else:
                    with st.spinner("🤖 Grok AI is analyzing your inventory data..."):
                        try:
                            # Prepare inventory context
                            inventory_summary = df.groupby('Category').agg({
                                'Footage': 'sum',
                                'Item_ID': 'count'
                            }).reset_index()
                            inventory_summary.columns = ['Category', 'Total_Footage', 'Item_Count']
                            
                            material_details = df[['Material', 'Footage', 'Category', 'Location']].head(50).to_string()
                            
                            prompt = f"""You are an intelligent warehouse management assistant for MJP Pulse.

Current Inventory Summary:
{inventory_summary.to_string()}

Sample Material Details (first 50 items):
{material_details}

Business Rules:
- RPR (Rolls Per Reel) = 200 ft/roll
- Standard items = 100 ft/roll
- Reorder threshold = 20% of normal capacity

User Question: {user_q}

Please provide a clear, actionable response with specific recommendations and data-backed insights."""
                            
                            # Call Grok API
                            response = grok_client.chat.completions.create(
                                model="grok-beta",
                                messages=[
                                    {"role": "system", "content": "You are a helpful warehouse management AI assistant. Provide clear, actionable insights based on inventory data."},
                                    {"role": "user", "content": prompt}
                                ],
                                temperature=0.7,
                                max_tokens=1500
                            )
                            
                            if response.choices and response.choices[0].message.content:
                                ai_response = response.choices[0].message.content
                                
                                st.markdown("### 🎯 Grok AI Response")
                                st.markdown("""
                                    <div style="background: white; padding: 20px; border-radius: 8px; 
                                                border-left: 4px solid #7c3aed; margin: 20px 0;">
                                """, unsafe_allow_html=True)
                                
                                st.markdown(ai_response)
                                
                                st.markdown("</div>", unsafe_allow_html=True)
                                
                                # Download button
                                st.download_button(
                                    "📥 Download AI Report",
                                    ai_response,
                                    file_name=f"MJP_Grok_Report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                                    mime="text/plain",
                                    key="download_ai_report"
                                )
                                
                                st.success("✅ Analysis complete!")
                            
                        except Exception as e:
                            st.error(f"❌ Grok AI Error: {e}")
                            st.markdown("""
                            **🔧 Troubleshooting:**
                            1. Verify your API key at [xAI Console](https://console.x.ai/)
                            2. Ensure you have API credits/billing enabled
                            3. Check if the key has proper permissions
                            4. Try regenerating the API key
                            """)
            
            st.markdown("</div>", unsafe_allow_html=True)
    
    else:
        st.info("📊 No inventory data available. Add items to view analytics.")
        st.markdown("""
            <div style="text-align: center; padding: 40px;">
                <h3 style="color: #64748b;">Get Started</h3>
                <p>Navigate to the <strong>Smart Inventory Receiver</strong> tab to add your first items!</p>
            </div>
        """, unsafe_allow_html=True)
        
with tab7:
    st.subheader("📜 System Audit Log")
    st.caption("Complete history of material movements, production runs, and admin submissions.")
    
    try:
        # Fetch audit logs from Supabase
        response = supabase.table("audit_log").select("*").order("Timestamp", desc=True).execute()
        
        if not response.data:
            st.info("No audit logs recorded yet. Logs will appear here as materials are picked or produced.")
        else:
            audit_df = pd.DataFrame(response.data)
            
            # Ensure Timestamp is handled correctly
            audit_df['Timestamp'] = pd.to_datetime(audit_df['Timestamp'], errors='coerce')
            
            # FILTER & SEARCH BAR
            search_col, filter_col = st.columns([2, 1])
            with search_col:
                query = st.text_input("🔍 Search Logs", placeholder="Search Order #, Operator, or Action...", key="audit_search")
            with filter_col:
                # Allows you to quickly see only Production submissions
                actions = ["All"] + sorted(audit_df['Action'].dropna().unique().tolist())
                selected_action = st.selectbox("Filter by Action", actions, key="audit_filter")
            
            # Apply Filters
            if selected_action != "All":
                audit_df = audit_df[audit_df['Action'] == selected_action]
            
            if query:
                audit_df = audit_df[audit_df.astype(str).apply(lambda x: x.str.contains(query, case=False)).any(axis=1)]
            
            # Sorting so newest is at the top
            audit_df = audit_df.sort_values('Timestamp', ascending=False)
            
            # Display the log
            st.dataframe(
                audit_df[['Timestamp', 'Action', 'User', 'Details']], 
                use_container_width=True, 
                hide_index=True
            )

    except Exception as e:
        st.error(f"Audit Log Display Error: {e}")

with tab8:
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h1 style="color: #0ea5e9; margin: 0;">📊 Inventory Reports</h1>
            <p style="color: #64748b; margin-top: 8px;">Generate detailed inventory reports by category</p>
        </div>
    """, unsafe_allow_html=True)
    
    if df is None or df.empty:
        st.info("📦 No inventory data available. Add items first.")
    else:
        # Report Options
        st.markdown("### 📋 Report Settings")
        
        col_cat, col_format = st.columns(2)
        
        with col_cat:
            report_categories = ["All Categories"] + sorted(df['Category'].unique().tolist())
            selected_report_cat = st.selectbox(
                "Select Category",
                report_categories,
                key="report_category_select"
            )
        
        with col_format:
            report_format = st.radio(
                "Report Format",
                ["View on Screen", "Download PDF", "Download Excel"],
                horizontal=True,
                key="report_format"
            )
        
        # Date for report
        report_date = datetime.now().strftime('%B %d, %Y at %I:%M %p')
        
        st.markdown("---")
        
        # Generate Report Button
        if st.button("📊 Generate Report", type="primary", use_container_width=True):
            
            # Filter data
            if selected_report_cat == "All Categories":
                report_df = df.copy()
            else:
                report_df = df[df['Category'] == selected_report_cat].copy()
            
            if report_df.empty:
                st.warning("No data found for selected category.")
            else:
                # ══════════════════════════════════════════════════════════════
                # BUILD REPORT DATA
                # ══════════════════════════════════════════════════════════════
                
                report_data = []
                categories_to_process = report_df['Category'].unique().tolist()
                
                for category in categories_to_process:
                    cat_df = report_df[report_df['Category'] == category]
                    
                    # Group by Material
                    material_summary = cat_df.groupby('Material').agg({
                        'Footage': ['sum', 'count', 'mean', 'min', 'max'],
                        'Location': lambda x: ', '.join(sorted(x.unique())[:3]) + ('...' if len(x.unique()) > 3 else '')
                    }).reset_index()
                    
                    material_summary.columns = ['Material', 'Total_Footage', 'Item_Count', 'Avg_Footage', 'Min_Footage', 'Max_Footage', 'Locations']
                    
                    for _, row in material_summary.iterrows():
                        report_data.append({
                            'Category': category,
                            'Material': row['Material'],
                            'Total_Footage': row['Total_Footage'],
                            'Item_Count': row['Item_Count'],
                            'Avg_Footage': row['Avg_Footage'],
                            'Min_Footage': row['Min_Footage'],
                            'Max_Footage': row['Max_Footage'],
                            'Locations': row['Locations']
                        })
                
                report_summary_df = pd.DataFrame(report_data)
                
                # ══════════════════════════════════════════════════════════════
                # DISPLAY ON SCREEN
                # ══════════════════════════════════════════════════════════════
                
                if report_format == "View on Screen":
                    st.markdown(f"""
                        <div style="background: linear-gradient(135deg, #0ea5e9 0%, #0284c7 100%); 
                                    padding: 20px; border-radius: 12px; color: white; margin-bottom: 20px;">
                            <h2 style="margin: 0;">📊 Inventory Report</h2>
                            <p style="margin: 5px 0 0 0; opacity: 0.9;">
                                Category: <strong>{selected_report_cat}</strong> | Generated: {report_date}
                            </p>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    # Overall Summary
                    st.markdown("### 📈 Overall Summary")
                    
                    sum1, sum2, sum3, sum4 = st.columns(4)
                    sum1.metric("Total Footage", f"{report_df['Footage'].sum():,.1f} ft")
                    sum2.metric("Total Items", len(report_df))
                    sum3.metric("Material Types", len(report_summary_df))
                    sum4.metric("Locations", report_df['Location'].nunique())
                    
                    st.markdown("---")
                    
                    # Detailed breakdown by category
                    for category in categories_to_process:
                        cat_data = report_summary_df[report_summary_df['Category'] == category]
                        cat_df_raw = report_df[report_df['Category'] == category]
                        
                        st.markdown(f"""
                            <div style="background: #f8fafc; padding: 15px; border-radius: 8px; 
                                        border-left: 4px solid #0ea5e9; margin: 20px 0 10px 0;">
                                <h3 style="margin: 0; color: #0ea5e9;">{category}</h3>
                                <p style="margin: 5px 0 0 0; color: #64748b;">
                                    {len(cat_df_raw)} items | {cat_df_raw['Footage'].sum():,.1f} ft total
                                </p>
                            </div>
                        """, unsafe_allow_html=True)
                        
                        # Material breakdown
                        for _, mat_row in cat_data.iterrows():
                            material = mat_row['Material']
                            total_ft = mat_row['Total_Footage']
                            count = int(mat_row['Item_Count'])
                            avg_ft = mat_row['Avg_Footage']
                            locations = mat_row['Locations']
                            
                            # Build description based on category
                            if category == "Coils":
                                desc = f"{count} Coil{'s' if count != 1 else ''} @ ~{avg_ft:,.0f} ft each"
                            elif category == "Rolls":
                                desc = f"{count} Roll{'s' if count != 1 else ''} @ ~{avg_ft:,.0f} ft each"
                            elif category in ["Elbows", "Fab Straps", "Wing Seals"]:
                                desc = f"{count} item{'s' if count != 1 else ''}"
                            else:
                                desc = f"{count} item{'s' if count != 1 else ''} @ ~{avg_ft:,.0f} units each"
                            
                            st.markdown(f"""
                                <div style="background: white; padding: 15px; border-radius: 8px; 
                                            margin: 8px 0; border: 1px solid #e2e8f0;">
                                    <div style="display: flex; justify-content: space-between; align-items: center;">
                                        <div>
                                            <strong style="color: #1e293b; font-size: 15px;">{material}</strong><br>
                                            <span style="color: #64748b; font-size: 13px;">{desc}</span><br>
                                            <span style="color: #94a3b8; font-size: 11px;">📍 {locations}</span>
                                        </div>
                                        <div style="text-align: right;">
                                            <span style="color: #0ea5e9; font-size: 24px; font-weight: bold;">{total_ft:,.1f}</span><br>
                                            <span style="color: #64748b; font-size: 12px;">feet total</span>
                                        </div>
                                    </div>
                                </div>
                            """, unsafe_allow_html=True)
                        
                        # Show individual items in expander
                        with st.expander(f"📋 View all {category} items"):
                            st.dataframe(
                                cat_df_raw[['Item_ID', 'Material', 'Footage', 'Location']].sort_values(['Material', 'Item_ID']),
                                use_container_width=True,
                                hide_index=True
                            )
                
                # ══════════════════════════════════════════════════════════════
                # DOWNLOAD PDF
                # ══════════════════════════════════════════════════════════════
                
                elif report_format == "Download PDF":
                    with st.spinner("Generating PDF report..."):
                        try:
                            from reportlab.lib import colors
                            from reportlab.lib.pagesizes import letter
                            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
                            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
                            from reportlab.lib.units import inch
                            from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
                            from io import BytesIO
                            
                            buffer = BytesIO()
                            doc = SimpleDocTemplate(buffer, pagesize=letter,
                                                   rightMargin=0.5*inch, leftMargin=0.5*inch,
                                                   topMargin=0.75*inch, bottomMargin=0.5*inch)
                            
                            elements = []
                            styles = getSampleStyleSheet()
                            
                            # Custom styles
                            title_style = ParagraphStyle(
                                'CustomTitle',
                                parent=styles['Heading1'],
                                fontSize=24,
                                textColor=colors.HexColor('#0ea5e9'),
                                spaceAfter=12,
                                alignment=TA_CENTER,
                                fontName='Helvetica-Bold'
                            )
                            
                            subtitle_style = ParagraphStyle(
                                'CustomSubtitle',
                                parent=styles['Normal'],
                                fontSize=10,
                                textColor=colors.HexColor('#64748b'),
                                spaceAfter=20,
                                alignment=TA_CENTER
                            )
                            
                            heading_style = ParagraphStyle(
                                'CustomHeading',
                                parent=styles['Heading2'],
                                fontSize=14,
                                textColor=colors.HexColor('#0ea5e9'),
                                spaceAfter=10,
                                spaceBefore=15
                            )
                            
                            # Title
                            elements.append(Paragraph("INVENTORY REPORT", title_style))
                            elements.append(Paragraph(f"Category: {selected_report_cat} | Generated: {report_date}", subtitle_style))
                            
                            # Overall Summary Table
                            summary_data = [
                                ['Total Footage', 'Total Items', 'Material Types', 'Locations'],
                                [f"{report_df['Footage'].sum():,.1f} ft", str(len(report_df)), str(len(report_summary_df)), str(report_df['Location'].nunique())]
                            ]
                            
                            summary_table = Table(summary_data, colWidths=[1.8*inch]*4)
                            summary_table.setStyle(TableStyle([
                                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0ea5e9')),
                                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                ('FONTSIZE', (0, 0), (-1, -1), 10),
                                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                                ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                                ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f0f9ff')),
                                ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
                                ('PADDING', (0, 0), (-1, -1), 8),
                            ]))
                            elements.append(summary_table)
                            elements.append(Spacer(1, 0.3*inch))
                            
                            # Detailed breakdown by category
                            for category in categories_to_process:
                                cat_data = report_summary_df[report_summary_df['Category'] == category]
                                cat_df_raw = report_df[report_df['Category'] == category]
                                
                                elements.append(Paragraph(f"{category}", heading_style))
                                elements.append(Paragraph(f"{len(cat_df_raw)} items | {cat_df_raw['Footage'].sum():,.1f} ft total", styles['Normal']))
                                elements.append(Spacer(1, 0.1*inch))
                                
                                # Material table
                                table_data = [['Material', 'Items', 'Total Footage', 'Avg/Item', 'Locations']]
                                
                                for _, mat_row in cat_data.iterrows():
                                    table_data.append([
                                        mat_row['Material'][:40] + ('...' if len(mat_row['Material']) > 40 else ''),
                                        str(int(mat_row['Item_Count'])),
                                        f"{mat_row['Total_Footage']:,.1f} ft",
                                        f"{mat_row['Avg_Footage']:,.0f} ft",
                                        mat_row['Locations'][:20] + ('...' if len(mat_row['Locations']) > 20 else '')
                                    ])
                                
                                mat_table = Table(table_data, colWidths=[2.2*inch, 0.7*inch, 1.2*inch, 0.9*inch, 1.5*inch])
                                mat_table.setStyle(TableStyle([
                                    ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0ea5e9')),
                                    ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                                    ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                                    ('FONTSIZE', (0, 0), (-1, 0), 9),
                                    ('FONTSIZE', (0, 1), (-1, -1), 8),
                                    ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
                                    ('ALIGN', (0, 0), (0, -1), 'LEFT'),
                                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
                                    ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
                                    ('PADDING', (0, 0), (-1, -1), 6),
                                ]))
                                elements.append(mat_table)
                                elements.append(Spacer(1, 0.2*inch))
                            
                            # Footer
                            elements.append(Spacer(1, 0.3*inch))
                            footer_style = ParagraphStyle(
                                'Footer',
                                parent=styles['Normal'],
                                fontSize=8,
                                textColor=colors.HexColor('#94a3b8'),
                                alignment=TA_CENTER
                            )
                            elements.append(Paragraph(
                                "This report was automatically generated by MJP Pulse Inventory System.",
                                footer_style
                            ))
                            
                            doc.build(elements)
                            buffer.seek(0)
                            
                            # Download button
                            file_name = f"Inventory_Report_{selected_report_cat.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                            
                            st.download_button(
                                label="📥 Download PDF Report",
                                data=buffer.getvalue(),
                                file_name=file_name,
                                mime="application/pdf",
                                type="primary",
                                use_container_width=True
                            )
                            
                            st.success("✅ PDF report generated successfully!")
                            
                        except Exception as e:
                            st.error(f"❌ Error generating PDF: {e}")
                
                # ══════════════════════════════════════════════════════════════
                # DOWNLOAD EXCEL
                # ══════════════════════════════════════════════════════════════
                
                elif report_format == "Download Excel":
                    with st.spinner("Generating Excel report..."):
                        try:
                            from io import BytesIO
                            
                            buffer = BytesIO()
                            
                            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                                # Summary sheet
                                summary_sheet_data = []
                                summary_sheet_data.append({'Metric': 'Report Date', 'Value': report_date})
                                summary_sheet_data.append({'Metric': 'Category', 'Value': selected_report_cat})
                                summary_sheet_data.append({'Metric': 'Total Footage', 'Value': f"{report_df['Footage'].sum():,.1f} ft"})
                                summary_sheet_data.append({'Metric': 'Total Items', 'Value': len(report_df)})
                                summary_sheet_data.append({'Metric': 'Material Types', 'Value': len(report_summary_df)})
                                summary_sheet_data.append({'Metric': 'Locations', 'Value': report_df['Location'].nunique()})
                                
                                pd.DataFrame(summary_sheet_data).to_excel(writer, sheet_name='Summary', index=False)
                                
                                # Material Summary sheet
                                report_summary_df.to_excel(writer, sheet_name='Material Summary', index=False)
                                
                                # Detailed items sheet
                                report_df[['Item_ID', 'Category', 'Material', 'Footage', 'Location', 'Status']].to_excel(
                                    writer, sheet_name='All Items', index=False
                                )
                                
                                # Separate sheet for each category
                                for category in categories_to_process:
                                    cat_df_raw = report_df[report_df['Category'] == category]
                                    sheet_name = category[:30]  # Excel sheet names max 31 chars
                                    cat_df_raw[['Item_ID', 'Material', 'Footage', 'Location']].to_excel(
                                        writer, sheet_name=sheet_name, index=False
                                    )
                            
                            buffer.seek(0)
                            
                            file_name = f"Inventory_Report_{selected_report_cat.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                            
                            st.download_button(
                                label="📥 Download Excel Report",
                                data=buffer.getvalue(),
                                file_name=file_name,
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                type="primary",
                                use_container_width=True
                            )
                            
                            st.success("✅ Excel report generated successfully!")
                            
                        except Exception as e:
                            st.error(f"❌ Error generating Excel: {e}")
        
        st.markdown("---")
        
        # ══════════════════════════════════════════════════════════════════════
        # QUICK CATEGORY REPORTS
        # ══════════════════════════════════════════════════════════════════════
        
        st.markdown("### 🚀 Quick Reports")
        st.caption("Click to view instant summaries")
        
        # Get categories that have data
        categories_with_data = df['Category'].unique().tolist()
        
        # Create columns for quick report buttons
        num_cols = min(4, len(categories_with_data))
        if num_cols > 0:
            cols = st.columns(num_cols)
            
            for idx, category in enumerate(categories_with_data[:8]):  # Max 8 categories
                with cols[idx % num_cols]:
                    cat_df = df[df['Category'] == category]
                    total_ft = cat_df['Footage'].sum()
                    item_count = len(cat_df)
                    
                    # Category icon
                    cat_icons = {
                        "Coils": "🔄", "Rolls": "📜", "Elbows": "↩️",
                        "Fab Straps": "🔗", "Mineral Wool": "🧶",
                        "Fiberglass Insulation": "🏠", "Wing Seals": "🔒",
                        "Wire": "➰", "Banding": "📏"
                    }
                    icon = cat_icons.get(category, "📦")
                    
                    with st.expander(f"{icon} {category}"):
                        st.metric("Total Footage", f"{total_ft:,.1f} ft")
                        st.metric("Items", item_count)
                        
                        # Quick material breakdown
                        mat_summary = cat_df.groupby('Material').agg({
                            'Footage': 'sum',
                            'Item_ID': 'count'
                        }).reset_index()
                        mat_summary.columns = ['Material', 'Footage', 'Count']
                        mat_summary = mat_summary.sort_values('Footage', ascending=False)
                        
                        st.markdown("**Top Materials:**")
                        for _, row in mat_summary.head(5).iterrows():
                            if category in ["Coils", "Rolls"]:
                                st.write(f"• {row['Material'][:30]}...")
                                st.write(f"  {row['Footage']:,.1f} ft ({int(row['Count'])} items)")
                            else:
                                st.write(f"• {row['Material'][:30]}: {int(row['Footage'])} pcs")
