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
@st.cache_data(ttl=30)
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
        
# Initialize df
if 'df' not in st.session_state or 'df_audit' not in st.session_state:
    st.session_state.df, st.session_state.df_audit = load_all_tables()

df = st.session_state.df
df_audit = st.session_state.df_audit

# Normalize categories in the dataframe
if df is not None and not df.empty and 'Category' in df.columns:
    df['Category'] = df['Category'].apply(normalize_category)
    st.session_state.df = df
    
# Paste update_stock here
def update_stock(item_id, new_footage, user_name, action_type):
    try:
        supabase.table("inventory").update({"Footage": new_footage}).eq("Item_ID", item_id).execute()
        
        log_entry = {
            "Item_ID": item_id,
            "Action": action_type,
            "User": user_name,
            "Timestamp": datetime.now().isoformat(),
            "Details": f"Updated Item {item_id} to {new_footage:.2f} ft via {action_type}"
        }
        supabase.table("audit_log").insert(log_entry).execute()
        
        st.cache_data.clear()
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
            check_and_alert_low_stock()
            
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
    st.cache_data.clear()
    st.toast("Pulling fresh data from Supabase...")
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
        inches_per_piece = line["custom_inches"]
    else:
        inches_per_piece = SIZE_DISPLAY.get(line["display_size"], 12.0)
    
    total_inches = (inches_per_piece + extra_allowance) * line["pieces"]
    total_footage_needed = total_inches / 12.0
    total_footage_needed += line["waste"]
    
    # Get source items
    source_items = []
    for item_str in line["items"]:
        item_id = item_str.split(" - ")[0]
        mask = df['Item_ID'] == item_id
        if mask.any():
            source_items.append({
                'id': item_id,
                'footage': df.loc[mask, 'Footage'].values[0],
                'material': df.loc[mask, 'Material'].values[0]
            })
    
    if not source_items:
        feedback.append(f"✗ No valid sources found for {material_type} {line['display_size']}")
        return False, 0.0
    
    # Calculate available footage
    available_footage = sum(item['footage'] for item in source_items)
    
    if available_footage < total_footage_needed:
        feedback.append(f"✗ Insufficient stock for {material_type} {line['display_size']}: need {total_footage_needed:.2f} ft, have {available_footage:.2f} ft")
        return False, 0.0
    
    # Deduct from sources
    remaining_needed = total_footage_needed
    
    for item in source_items:
        if remaining_needed <= 0:
            break
        
        deduct_amount = min(item['footage'], remaining_needed)
        new_footage = item['footage'] - deduct_amount
        
        # Update database
        try:
            action_details = f"Production: {line['pieces']} pcs of {line['display_size']} ({deduct_amount:.2f} ft used) for {client_name} (Order: {order_number})"
            
            success_update = update_stock(
                item_id=item['id'],
                new_footage=new_footage,
                user_name=operator_name,
                action_type=action_details
            )
            
            if not success_update:
                feedback.append(f"✗ Failed to update {item['id']}")
                return False, 0.0
            
            # Record for PDF
            deduction_details.append({
                'source_id': item['id'],
                'material': item['material'],
                'size': line['display_size'],
                'pieces': line['pieces'],
                'footage_used': deduct_amount,
                'waste': line['waste'],
                'material_type': material_type
            })
            
            remaining_needed -= deduct_amount
            
        except Exception as e:
            feedback.append(f"✗ Error updating {item['id']}: {e}")
            return False, 0.0
    
    feedback.append(f"✓ {material_type} {line['display_size']}: {line['pieces']} pieces produced ({total_footage_needed:.2f} ft used)")
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
    elements.append(Paragraph("📋 MJP PRODUCTION ORDER LOG", title_style))
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
    
    # Table data - more compact columns
    table_data = [['Type', 'Source ID', 'Size', 'Pcs', 'Footage', 'Waste', 'Extra"']]
    
    for detail in deduction_details:
        extra_allowance = coil_extra if detail['material_type'] == 'Coil' else roll_extra
        table_data.append([
            detail['material_type'][:4],  # Coil/Roll
            str(detail['source_id'])[:15],  # Truncate if needed
            detail['size'],
            str(detail['pieces']),
            f"{detail['footage_used']:.1f}",
            f"{detail['waste']:.1f}",
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
    
    # TOTALS SECTION - Group by material
    elements.append(Paragraph("📊 TOTALS BY MATERIAL", heading_style))
    
    # Calculate totals by material
    material_totals = {}
    for detail in deduction_details:
        material_key = detail['material']
        if material_key not in material_totals:
            material_totals[material_key] = {
                'footage': 0,
                'waste': 0,
                'pieces': 0,
                'type': detail['material_type']
            }
        material_totals[material_key]['footage'] += detail['footage_used']
        material_totals[material_key]['waste'] += detail['waste']
        material_totals[material_key]['pieces'] += detail['pieces']
    
    # Create totals table
    totals_data = [['Material', 'Type', 'Total Pieces', 'Total Footage Used', 'Total Waste']]
    
    grand_footage = 0
    grand_waste = 0
    grand_pieces = 0
    
    for material, totals in material_totals.items():
        totals_data.append([
            material[:35],  # Truncate long names
            totals['type'],
            str(totals['pieces']),
            f"{totals['footage']:.2f} ft",
            f"{totals['waste']:.2f} ft"
        ])
        grand_footage += totals['footage']
        grand_waste += totals['waste']
        grand_pieces += totals['pieces']
    
    # Grand total row
    totals_data.append([
        'GRAND TOTAL',
        '',
        str(grand_pieces),
        f"{grand_footage:.2f} ft",
        f"{grand_waste:.2f} ft"
    ])
    
    totals_table = Table(totals_data, colWidths=[2*inch, 0.7*inch, 1.1*inch, 1.4*inch, 1.1*inch])
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
    
    # Extra allowance summary
    allowance_note = ParagraphStyle(
        'AllowanceNote',
        parent=styles['Normal'],
        fontSize=8,
        textColor=colors.HexColor('#64748b'),
        alignment=TA_CENTER,
        spaceAfter=10
    )
    
    elements.append(Paragraph(
        f"<b>Note:</b> Extra allowance included - Coils: {coil_extra}\" per piece | Rolls: {roll_extra}\" per piece",
        allowance_note
    ))
    
    # Box usage section (if any)
    if any(box_usage.values()):
        elements.append(Spacer(1, 0.1*inch))
        elements.append(Paragraph("📦 Box Usage", heading_style))
        
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
# Your tabs code starts right here:
# tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Dashboard", "Production Log", "Stock Picking", "Manage", "Insights", "Audit Trail"])
# --- TABS ---
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Dashboard", "Production Log", "Stock Picking", "Manage", "Insights", "Audit Trail"])

with tab1:
    # Refresh button (optional but super useful)
    col_refresh, _ = st.columns([1, 3])
    with col_refresh:
        if st.button("🔄 Refresh Dashboard", use_container_width=False):
            st.cache_data.clear()
            st.toast("Dashboard refreshed from cloud!", icon="🛰️")
            st.rerun()

    # Optional last updated time
    st.caption(f"Data last refreshed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    if not df.empty:
        # Available categories (sorted)
        available_categories = sorted(df['Category'].unique().tolist())
        view_options = ["All Materials"] + available_categories

        # Sidebar filter - clean and scales to any number of categories
        with st.sidebar:
            st.subheader("Dashboard Filter")
            selected_view = st.selectbox(
                "Category",
                view_options,
                index=0,  # Default: All Materials
                placeholder="Select category...",
                help="Choose what to show on the dashboard",
                key="dashboard_category_filter"
            )

        # Filter data based on sidebar selection
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

        # 4. THE PULSE GRID (your original cards)
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
                        <span style="color: #888; font-size: 11px;">{units} IDs</span>
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

    # Safe column name handling
    category_col = next((c for c in df.columns if c.lower() == 'category'), None)
    if not category_col:
        st.error("Column 'Category' not found in inventory data.")
       # st.stop()

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

    available_coils = filter_materials(df[(df[category_col] == "Coils") & (df['Footage'] > 0)])
    available_rolls = filter_materials(df[(df[category_col] == "Rolls") & (df['Footage'] > 0)])    if available_coils.empty and available_rolls.empty:
        st.info("No available stock matching the selected texture.")
       # st.stop()

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
    
    # DEBUG
    if df is not None and not df.empty:
        st.write("**Categories available:**", df['Category'].unique().tolist())
        st.write("**Sample data:**")
        st.dataframe(df[['Item_ID', 'Category', 'Material', 'Footage']].head())

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

        category_options = ["Fab Straps", "Rolls", "Elbows", "Mineral Wool", "Coils"]
        
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
                key="pick_customer_persist"
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
                key="pick_sales_order_persist"
            )
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.divider()

        # ── Add Items to Cart Form ──────────────────────────────────────────────────
        st.markdown("#### ➕ Add Items to Order")
        
        # Category selection OUTSIDE form so it can update dynamically
        pick_cat = st.selectbox(
            "Category",
            category_options,
            key="pick_cat_add"
        )
        
        filtered_df = pick_df[pick_df['Category'] == pick_cat].copy() if not pick_df.empty else pd.DataFrame()
        
        with st.form("add_to_cart_form", clear_on_submit=True):
            col1, col2 = st.columns(2)
            
            with col1:
                if filtered_df.empty:
                    st.warning(f"⚠️ No items in stock for {pick_cat}")
                    selected_mat = None
                else:
                    mat_options = sorted(filtered_df['Material'].unique())
                    selected_mat = st.selectbox("Size / Material", mat_options, key="mat_add")
            
            with col2:
                if selected_mat:
                    if pick_cat in ["Rolls", "Coils"]:
                        specific_ids = filtered_df[filtered_df['Material'] == selected_mat]['Item_ID'].tolist()
                        pick_id = st.selectbox("Select Serial #", specific_ids or ["No items available"], key="id_add")
                        pick_qty = 1
                    else:
                        pick_id = "BULK"
                        pick_qty = st.number_input("Quantity", min_value=1, step=1, key="qty_add")
                else:
                    pick_id = None
                    pick_qty = 0

            add_to_cart = st.form_submit_button("🛒 Add to Cart", use_container_width=True)

        # ── Process Add to Cart ─────────────────────────────────────────────────────
        if add_to_cart and selected_mat:
            # Check current stock
            if pick_cat in ["Rolls", "Coils"]:
                available = pick_id in filtered_df['Item_ID'].values
                if available:
                    st.session_state.pick_cart.append({
                        'category': pick_cat,
                        'material': selected_mat,
                        'item_id': pick_id,
                        'quantity': 1,
                        'available': 1,
                        'shortfall': 0
                    })
                    st.success(f"✅ Added {pick_cat[:-1]} {selected_mat} (#{pick_id})")
                    st.rerun()
                else:
                    st.error("Item not available")
            else:
                mask = (pick_df['Category'] == pick_cat) & (pick_df['Material'] == selected_mat)
                if mask.any():
                    current_stock = pick_df.loc[mask, 'Footage'].values[0]
                    bulk_item_id = pick_df.loc[mask, 'Item_ID'].values[0]
                    
                    # Calculate what's actually available
                    available = min(current_stock, pick_qty)
                    shortfall = max(0, pick_qty - current_stock)
                    
                    st.session_state.pick_cart.append({
                        'category': pick_cat,
                        'material': selected_mat,
                        'item_id': bulk_item_id,
                        'quantity': pick_qty,
                        'available': available,
                        'shortfall': shortfall
                    })
                    
                    if shortfall > 0:
                        st.warning(f"⚠️ Added to cart: {available} available, {shortfall} will be back ordered")
                    else:
                        st.success(f"✅ Added {pick_qty} × {selected_mat}")
                    st.rerun()

        # ── Display Cart ────────────────────────────────────────────────────────────
        if st.session_state.pick_cart:
            st.markdown("---")
            st.markdown("#### 🛒 Current Order")
            
            for idx, item in enumerate(st.session_state.pick_cart):
                col_item, col_remove = st.columns([5, 1])
                
                with col_item:
                    status = ""
                    if item['shortfall'] > 0:
                        status = f" ⚠️ ({item['available']} available, {item['shortfall']} back order)"
                    
                    if item['category'] in ["Rolls", "Coils"]:
                        st.write(f"**{item['category'][:-1]}** - {item['material']} (#{item['item_id']}){status}")
                    else:
                        st.write(f"**{item['quantity']}x {item['material']}** ({item['category']}){status}")
                
                with col_remove:
                    if st.button("🗑️", key=f"remove_{idx}"):
                        st.session_state.pick_cart.pop(idx)
                        st.rerun()
            
            st.divider()
            
            # Authorized By
            picker_name = st.text_input(
                "Authorized By",
                value=st.session_state.get("username", "Admin"),
                key="pick_authorized"
            )
            
            col_process, col_clear = st.columns(2)
            
            with col_process:
                if st.button("📤 Process All Items", type="primary", use_container_width=True):
                    if not customer.strip():
                        st.error("⚠️ Please enter Customer / Job Name.")
                    elif not sales_order.strip():
                        st.error("⚠️ Please enter Sales Order Number.")
                    else:
                        # Save for back orders
                        st.session_state.last_customer = customer.strip()
                        st.session_state.last_sales_order = sales_order.strip()
                        st.session_state.back_order_items = []
                        
                        action_suffix = f" (SO: {sales_order})"
                        all_success = True
                        
                        with st.spinner("Processing all items..."):
                            for item in st.session_state.pick_cart:
                                if item['category'] in ["Rolls", "Coils"]:
                                    success = update_stock(
                                        item_id=item['item_id'],
                                        new_footage=0,
                                        user_name=picker_name,
                                        action_type=f"Sold {item['category'][:-1]} to {customer}{action_suffix}"
                                    )
                                    all_success = all_success and success
                                else:
                                    # Get current stock
                                    mask = (pick_df['Category'] == item['category']) & (pick_df['Item_ID'] == item['item_id'])
                                    if mask.any():
                                        current_stock = pick_df.loc[mask, 'Footage'].values[0]
                                        deduct_amount = min(current_stock, item['quantity'])
                                        new_total = current_stock - deduct_amount
                                        
                                        action_msg = f"Removed {deduct_amount} {item['category'][:-1]}(s) - {item['material']} for {customer}{action_suffix}"
                                        if item['shortfall'] > 0:
                                            action_msg += f" (shortfall: {item['shortfall']})"
                                        
                                        success = update_stock(
                                            item_id=item['item_id'],
                                            new_footage=new_total,
                                            user_name=picker_name,
                                            action_type=action_msg
                                        )
                                        all_success = all_success and success
                                        
                                        # Track back orders
                                        if item['shortfall'] > 0:
                                            st.session_state.back_order_items.append(item)
                        
                        if all_success:
                            st.success(f"✅ All items processed for {customer} ({sales_order})!")
                            
                            if st.session_state.back_order_items:
                                st.session_state.show_back_order = True
                            else:
                                st.balloons()
                                st.snow()
                                st.toast("Order complete! 🎉", icon="🎉")
                                st.session_state.pick_cart = []
                                st.cache_data.clear()
                                st.rerun()
                        else:
                            st.error("Some items failed to process. Check logs.")
            
            with col_clear:
                if st.button("🗑️ Clear Cart", use_container_width=True, key="clear_pick_cart"):
                    st.session_state.pick_cart = []
                    st.rerun()

        # ── Back Order UI ───────────────────────────────────────────────────────────
        if st.session_state.show_back_order and st.session_state.back_order_items:
            st.markdown("---")
            st.markdown("### 📦 Back Orders Required")
            
            st.info(f"**Customer:** {st.session_state.last_customer}  \n**Order:** {st.session_state.last_sales_order}")
            
            for item in st.session_state.back_order_items:
                st.write(f"- **{item['material']}** ({item['category']}): {item['shortfall']} units short")
            
            back_order_note = st.text_area(
                "Optional note for all back orders",
                placeholder="e.g. Urgent for client - ship when restocked",
                key="back_order_note"
            )
            
            col_confirm, col_skip = st.columns(2)
            
            with col_confirm:
                if st.button("✅ Create Back Orders", type="primary", use_container_width=True):
                    try:
                        for item in st.session_state.back_order_items:
                            back_order_data = {
                                "material": item['material'],
                                "shortfall_quantity": item['shortfall'],
                                "client_name": st.session_state.last_customer,
                                "order_number": st.session_state.last_sales_order,
                                "status": "Open",
                                "note": back_order_note.strip() or None
                            }
                            supabase.table("back_orders").insert(back_order_data).execute()
                        
                        st.success(f"✅ Created {len(st.session_state.back_order_items)} back order(s)!")
                        st.balloons()
                    except Exception as e:
                        st.error(f"Failed to create back orders: {e}")
                    
                    # Clear everything
                    st.session_state.show_back_order = False
                    st.session_state.back_order_items = []
                    st.session_state.pick_cart = []
                    st.cache_data.clear()
                    st.rerun()
            
            with col_skip:
                if st.button("❌ Skip Back Orders", use_container_width=True):
                    st.session_state.show_back_order = False
                    st.session_state.back_order_items = []
                    st.session_state.pick_cart = []
                    st.cache_data.clear()
                    st.rerun()
        
        # ── Back Order Report Section ──────────────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 📄 Back Order Reports")
        
        try:
            # Fetch all open back orders
            response = supabase.table("back_orders").select("*").eq("status", "Open").execute()
            back_orders = response.data
            
            if back_orders:
                st.info(f"📋 **{len(back_orders)}** open back order(s) in system")
                
                # Display back orders in expandable section
                with st.expander("View Open Back Orders"):
                    for bo in back_orders:
                        st.write(f"**{bo.get('material')}** - Qty: {bo.get('shortfall_quantity')} | Customer: {bo.get('client_name')} | Order: {bo.get('order_number')}")
                
                # Generate PDF Report Button
                if st.button("📥 Generate PDF Report", type="secondary", key="generate_backorder_pdf"):
                    from datetime import datetime
                    
                    # Create HTML report
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
                            .meta-info div {{ font-size: 14px; }}
                            .meta-info strong {{ color: #1e40af; }}
                            .order-card {{ border: 2px solid #e2e8f0; border-radius: 10px; padding: 20px; margin-bottom: 20px; background: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.05); page-break-inside: avoid; }}
                            .order-header {{ background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%); color: white; padding: 12px 16px; border-radius: 6px; margin: -20px -20px 15px -20px; font-size: 16px; font-weight: 600; }}
                            .order-details {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
                            .detail-row {{ padding: 8px 0; border-bottom: 1px solid #f1f5f9; }}
                            .detail-label {{ color: #64748b; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }}
                            .detail-value {{ color: #1e293b; font-size: 15px; font-weight: 500; margin-top: 4px; }}
                            .quantity {{ background: #fef3c7; color: #92400e; padding: 4px 12px; border-radius: 20px; font-weight: 700; display: inline-block; }}
                            .note {{ background: #eff6ff; border-left: 4px solid #2563eb; padding: 12px; margin-top: 15px; font-size: 13px; color: #1e40af; border-radius: 4px; }}
                            .footer {{ margin-top: 40px; text-align: center; color: #94a3b8; font-size: 12px; border-top: 2px solid #e2e8f0; padding-top: 20px; }}
                            @media print {{ body {{ padding: 20px; }} .no-print {{ display: none; }} }}
                        </style>
                    </head>
                    <body>
                        <div class="header">
                            <h1>📦 BACK ORDER REPORT</h1>
                            <div class="subtitle">Warehouse Management System</div>
                        </div>
                        <div class="meta-info">
                            <div><strong>Generated:</strong> {current_time}</div>
                            <div><strong>Total Open Orders:</strong> {len(back_orders)}</div>
                            <div><strong>Status:</strong> Open</div>
                        </div>
                    """
                    
                    # Add each back order
                    for idx, bo in enumerate(back_orders, 1):
                        html_content += f"""
                        <div class="order-card">
                            <div class="order-header">Order #{idx}</div>
                            <div class="order-details">
                                <div class="detail-row">
                                    <div class="detail-label">Material / Item</div>
                                    <div class="detail-value">{bo.get('material', 'N/A')}</div>
                                </div>
                                <div class="detail-row">
                                    <div class="detail-label">Quantity Needed</div>
                                    <div class="detail-value"><span class="quantity">{bo.get('shortfall_quantity', 'N/A')} units</span></div>
                                </div>
                                <div class="detail-row">
                                    <div class="detail-label">Customer / Job</div>
                                    <div class="detail-value">{bo.get('client_name', 'N/A')}</div>
                                </div>
                                <div class="detail-row">
                                    <div class="detail-label">Sales Order #</div>
                                    <div class="detail-value">{bo.get('order_number', 'N/A')}</div>
                                </div>
                            </div>
                        """
                        
                        if bo.get('note'):
                            html_content += f"""
                            <div class="note">
                                <strong>📝 Note:</strong> {bo.get('note')}
                            </div>
                            """
                        
                        html_content += """
                        </div>
                        """
                    
                    html_content += """
                        <div class="footer">
                            <p>This report was automatically generated by the Warehouse Management System.</p>
                            <p>For questions or updates, please contact the warehouse administrator.</p>
                        </div>
                    </body>
                    </html>
                    """
                    
                    # Create download button for HTML
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    st.download_button(
                        label="📄 Download HTML Report (Print to PDF)",
                        data=html_content,
                        file_name=f"back_orders_report_{timestamp}.html",
                        mime="text/html",
                        help="Download and open in browser, then use 'Print to PDF' (Ctrl+P)"
                    )
                    
                    # Preview the report
                    with st.expander("📋 Preview Report", expanded=True):
                        st.components.v1.html(html_content, height=600, scrolling=True)
                    
                    st.success("✅ Report generated! Download the HTML file and print to PDF using your browser.")
                    st.info("💡 **Tip:** Open the downloaded HTML file → Press Ctrl+P (or Cmd+P on Mac) → Select 'Save as PDF'")
            else:
                st.success("✅ No open back orders at this time!")
        
        except Exception as e:
            st.error(f"Failed to fetch back orders: {e}")
        
        if not st.session_state.pick_cart and not st.session_state.show_back_order:
            st.info("👆 Add items to start building your order")
        
with tab4:
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h1 style="color: #1e40af; margin: 0;">📦 Smart Inventory Receiver</h1>
            <p style="color: #64748b; margin-top: 8px;">Multi-line receiving with intelligent tracking and automatic PO management</p>
        </div>
    """, unsafe_allow_html=True)
    
    # ── Safe DataFrame Check ────────────────────────────────────────────────────
    # ... rest of your code continues
    
    # ── Safe DataFrame Check ────────────────────────────────────────────────────
    # Create a safe working copy - even if df is empty
    if df is not None and not df.empty:
        safe_df = df.copy()
    else:
        # Create empty DataFrame with expected structure
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
    
    st.markdown("---")
    
    # ── STEP 2: Add Item Form ──────────────────────────────────────────────────
    with st.form("add_receiving_item_form", clear_on_submit=True):
        
        # Dynamic Material Builder
        material = ""
        qty_val = 1.0
        unit_label = "Items"
        is_serialized = cat_choice in ["Coils", "Rolls", "Wire"]
        
        # Material Specifications Card
        st.markdown(f"### Step 2️⃣: {category_icons.get(cat_choice, '📦')} {cat_choice} Specifications")
        
        with st.container():
            st.markdown("""
                <div style="background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); 
                            padding: 24px; border-radius: 12px; border-left: 4px solid #0284c7;">
            """, unsafe_allow_html=True)
            
            if cat_choice == "Coils" or cat_choice == "Rolls":
                col1, col2 = st.columns(2)
                with col1:
                    texture = st.radio("🎨 Texture", ["Stucco", "Smooth"], horizontal=True)
                    metal = st.radio("🔩 Metal Type", ["Aluminum", "Stainless Steel"], horizontal=True)
                with col2:
                    gauge = st.selectbox("📏 Gauge", [".010", ".016", ".020", ".024", ".032", "Other"])
                    if gauge == "Other":
                        gauge = st.text_input("Custom Gauge", placeholder="e.g. .040")
                
                clean_gauge = gauge.replace('.', '')
                texture_code = "SMP" if texture == "Smooth" else "STP"
                metal_code = "AL" if metal == "Aluminum" else "SST"
                
                material = f"{texture} {metal} {cat_choice[:-1]} - {gauge} Gauge"
                qty_val = st.number_input("📐 Footage per Item", min_value=0.1, value=3000.0 if cat_choice == "Coils" else 100.0)
                unit_label = cat_choice  # "Coils" or "Rolls"
                
                id_prefix = f"{cat_choice[:-1]}-{metal_code}-{clean_gauge}-{texture_code}-{int(qty_val)}"
            
            elif cat_choice == "Fiberglass Insulation":
                col1, col2 = st.columns(2)
                with col1:
                    form_type = st.radio("📦 Form", ["Rolls", "Batts", "Pipe Wrap", "Other"])
                    thickness = st.selectbox("📏 Thickness", ["0.25 in", "0.5 in", "1 in", "1.5 in", "2 in", "Other"])
                    if thickness == "Other":
                        thickness = st.text_input("Custom Thickness", placeholder="e.g. 3 in")
                with col2:
                    sq_ft_per_roll = st.number_input("📐 Sq Ft per Roll", min_value=1.0, value=150.0)
                
                material = f"Fiberglass {form_type} - {thickness} Thickness - {sq_ft_per_roll} sq ft/roll"
                qty_val = sq_ft_per_roll
                unit_label = form_type  # "Rolls", "Batts", etc.
                is_serialized = form_type == "Rolls"
                
                id_prefix = f"FG-{thickness.replace(' ', '')}-{int(sq_ft_per_roll)}"
            
            elif cat_choice == "Elbows":
                col1, col2 = st.columns(2)
                with col1:
                    angle = st.radio("📐 Angle", ["45°", "90°", "Other"], horizontal=True)
                    if angle == "Other":
                        angle = st.text_input("Custom Angle", placeholder="e.g. 22.5°")
                    size_num = st.number_input("🔢 Size Number", min_value=1, max_value=60, value=1)
                with col2:
                    metal = st.radio("🔩 Metal Type", ["Aluminum", "Stainless Steel", "Galvanized", "Other"])
                
                material = f"{angle} Elbow - Size #{size_num} - {metal}"
                qty_val = 1.0
                unit_label = "Elbows"
                id_prefix = f"ELB-{angle.replace('°', '')}-S{size_num}"
            
            elif cat_choice == "Mineral Wool":
                col1, col2 = st.columns(2)
                with col1:
                    pipe_size = st.selectbox("🔧 Pipe Size", ["1 in", "2 in", "3 in", "4 in", "Other"])
                    if pipe_size == "Other":
                        pipe_size = st.text_input("Custom Pipe Size")
                with col2:
                    thickness = st.selectbox("📏 Thickness", ["0.5 in", "1 in", "1.5 in", "2 in", "Other"])
                    if thickness == "Other":
                        thickness = st.text_input("Custom Thickness")
                
                material = f"Mineral Wool - Pipe Size: {pipe_size} - Thickness: {thickness}"
                qty_val = 1.0
                unit_label = "Sections"
                id_prefix = f"MW-PS{pipe_size.replace(' ', '')}-THK{thickness.replace(' ', '')}"
            
            elif cat_choice == "Wing Seals":
                col1, col2 = st.columns(2)
                with col1:
                    seal_type = st.radio("🔐 Type", ["Open", "Closed"], horizontal=True)
                    size = st.radio("📏 Size", ["1/2 in", "3/4 in"], horizontal=True)
                    gauge = st.selectbox("📐 Gauge", [".028", ".032", "Other"])
                    if gauge == "Other":
                        gauge = st.text_input("Custom Gauge")
                with col2:
                    grooves = st.radio("〰️ Grooves", ["With Grooves (Center)", "Without Grooves"])
                    joint_pos = st.radio("📍 Joint Position", ["Bottom", "Top", "N/A"])
                    box_qty = st.number_input("📦 Pieces per Box", min_value=1, value=1000, step=100)
                
                material = f"{seal_type} Wing Seal - {size} - {gauge} Gauge - {grooves} - Joint at {joint_pos}"
                qty_val = box_qty
                unit_label = "Pieces"
                id_prefix = f"WS-{seal_type[0]}-{size.replace('/','').replace(' ','')}-{gauge.replace('.', '')}"
            
            elif cat_choice == "Wire":
                col1, col2 = st.columns(2)
                with col1:
                    gauge = st.selectbox("📏 Gauge", ["14", "16", "18", "Other"])
                    if gauge == "Other":
                        gauge = st.text_input("Custom Gauge")
                    rolls_count = st.number_input("🔢 Number of Rolls", min_value=1, value=1, step=1)
                with col2:
                    footage_per_roll = st.number_input("📐 Footage per Roll (optional)", min_value=0.0, value=0.0)
                    is_serialized = st.checkbox("🏷️ Assign unique ID to each roll?", value=False)
                
                material = f"Wire - {gauge} Gauge - {rolls_count} Roll(s)"
                qty_val = rolls_count if footage_per_roll == 0 else footage_per_roll * rolls_count
                unit_label = "Rolls"  # Always "Rolls" for wire
                
                id_prefix = f"WIRE-{gauge}"
            
            elif cat_choice == "Banding":
                col1, col2 = st.columns(2)
                with col1:
                    osc_type = st.radio("🌀 Type", ["Oscillated", "Non-Oscillated"])
                    size = st.radio("📏 Size", ["3/4 in", "1/2 in"])
                with col2:
                    gauge = st.selectbox("📐 Gauge", [".015", ".020"])
                    core = st.radio("⚙️ Core", ["Metal Core", "Non-Metal Core"])
                
                material = f"{osc_type} Banding - {size} - {gauge} Gauge - {core}"
                qty_val = st.number_input("📐 Footage per Item", min_value=0.1, value=100.0)
                unit_label = "Rolls"  # Changed from "Footage" to "Rolls"
                is_serialized = True
                
                id_prefix = f"BAND-{osc_type[0]}-{size.replace('/','').replace(' ','')}-{gauge.replace('.', '')}"
            
            elif cat_choice == "Fab Straps":
                col1, col2 = st.columns(2)
                with col1:
                    gauge = st.selectbox("📏 Gauge", [".015", ".020"])
                    size_num = st.number_input("🔢 Size Number", min_value=1, max_value=50, value=1)
                with col2:
                    metal = st.radio("🔩 Metal Type", ["Aluminum", "Stainless Steel", "Other"])
                
                material = f"Fab Strap {gauge} - #{size_num} - {metal}"
                qty_val = 1.0
                unit_label = "Fab Straps"  # More specific
                id_prefix = f"FS-{gauge.replace('.', '')}-S{size_num}"
            
            elif cat_choice == "Other":
                cat_choice = st.text_input("📝 New Category Name", placeholder="e.g. Accessories")
                material = st.text_input("📦 Material Description", placeholder="e.g. Custom Gaskets")
                qty_val = st.number_input("🔢 Qty/Footage per item", min_value=0.1, value=1.0)
                unit_label = st.text_input("🏷️ Unit Label", value="Units")
                id_prefix = f"OTH-{cat_choice.upper()[:3]}" if cat_choice else "OTH-UNK"
            
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
                item_count = st.number_input(
                    f"📦 How many {unit_label}?", 
                    min_value=1, value=1, step=1
                )
                
                total_added = item_count * qty_val
                st.success(f"**📊 Total:** {total_added} {unit_label.lower()}")
            
            with col2:
                loc_type = st.radio("🏢 Storage Type", ["Rack System", "Floor / Open Space"], horizontal=True, key="storage_type_radio")
            
            # Storage location input (moved outside columns for better layout)
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
                # Extract just the letter from "Floor A" -> "Floor A"
                floor_letter = floor_selection  # Keep it as "Floor A" format
                lvl = subcol3.number_input("⬆️ Level", min_value=1, value=1, key="floor_lvl")
                gen_loc = f"{bay}-{floor_letter}-{lvl}"
            
            st.info(f"📍 **Location:** {gen_loc}")
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("---")
        
        # ID Generation
        st.markdown("### Step 4️⃣: 🏷️ Identification")
        
        with st.container():
            st.markdown("""
                <div style="background: linear-gradient(135deg, #fdf4ff 0%, #fae8ff 100%); 
                            padding: 24px; border-radius: 12px; border-left: 4px solid #9333ea;">
            """, unsafe_allow_html=True)
            
            # ID Generation Logic
            if cat_choice == "Coils" and is_serialized:
                st.info(f"💡 **ID Format:** `{id_prefix}-##` (e.g. {id_prefix}-01)")
                starting_id = st.text_input("🏷️ Starting Coil ID", value=f"{id_prefix}-01", placeholder=f"{id_prefix}-01")
                id_preview = starting_id
                st.success(f"🏷️ **First ID:** `{id_preview}`")
            
            elif cat_choice == "Rolls" and is_serialized:
                st.info(f"💡 **ID Format:** `{id_prefix}-##` (e.g. {id_prefix}-01)")
                starting_id = st.text_input("🏷️ Starting Roll/Pallet ID", value=f"{id_prefix}-01", placeholder=f"{id_prefix}-01")
                id_preview = starting_id
                st.success(f"🏷️ **Pallet ID:** `{id_preview}` (Total: {total_added} footage)")
                is_serialized = False
            
            elif is_serialized:
                starting_id = st.text_input("🏷️ Starting ID", value=f"{id_prefix}-1001")
                id_preview = starting_id
                st.info(f"🏷️ **ID Preview:** `{id_preview}`")
            
            else:
                id_preview = f"{cat_choice.upper()}-BULK"
                st.info("📦 **Bulk item** - No unique IDs needed")
            
            st.markdown("</div>", unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Add to Cart Button
        add_item = st.form_submit_button(
            "🛒 Add to Receiving Cart", 
            use_container_width=True, 
            type="secondary"
        )
    
    # ── Process Add to Cart ─────────────────────────────────────────────────────
    if add_item:
        if not current_po.strip():
            st.error("⚠️ Please enter a Purchase Order Number first!")
        elif not operator.strip():
            st.error("⚠️ Please enter the Receiving Operator name!")
        elif not material:
            st.error("⚠️ Material details are required!")
        else:
            # Add to cart
            st.session_state.receiving_cart.append({
                'category': cat_choice,
                'material': material,
                'qty_val': qty_val,
                'item_count': item_count,
                'total_added': total_added,
                'unit_label': unit_label,
                'location': gen_loc,
                'is_serialized': is_serialized,
                'id_prefix': id_prefix if 'id_prefix' in locals() else cat_choice.upper(),
                'id_preview': id_preview if 'id_preview' in locals() else f"{cat_choice}-BULK",
                'starting_id': starting_id if 'starting_id' in locals() else None,
            })
            
            st.success(f"✅ Added: {item_count} × {material} ({total_added} {unit_label.lower()})")
            st.rerun()
    
    # ── Display Receiving Cart ──────────────────────────────────────────────────
    if st.session_state.receiving_cart:
        st.markdown("---")
        st.markdown("### 🛒 Current Receiving Batch")
        st.info(f"📋 **PO:** {st.session_state.current_po} | 👤 **Operator:** {st.session_state.receiving_operator}")
        
        for idx, item in enumerate(st.session_state.receiving_cart):
            col_item, col_remove = st.columns([5, 1])
            
            with col_item:
                st.write(f"**{idx+1}.** {item['item_count']} × {item['material']} = **{item['total_added']} {item['unit_label'].lower()}** → 📍 {item['location']}")
            
            with col_remove:
                if st.button("🗑️", key=f"remove_receiving_item_{idx}_{item['material'][:10]}"):
                    st.session_state.receiving_cart.pop(idx)
                    st.rerun()
        
        st.markdown("---")
        
        col_process, col_clear = st.columns(2)
        
        with col_process:
            if st.button("✅ Process All Items to Inventory", type="primary", use_container_width=True, key="process_all_receiving"):
                if not st.session_state.current_po.strip() or not st.session_state.receiving_operator.strip():
                    st.error("⚠️ PO Number and Operator are required!")
                else:
                    with st.spinner("☁️ Processing all items to Cloud Database..."):
                        try:
                            all_success = True
                            items_added = 0
                            items_skipped = 0
                            
                            for item in st.session_state.receiving_cart:
                                if item['is_serialized']:
                                    new_rows = []
                                    for i in range(item['item_count']):
                                        if item['starting_id']:
                                            # Parse the starting ID and increment
                                            parts = item['starting_id'].split('-')
                                            base = '-'.join(parts[:-1])
                                            num = int(parts[-1]) + i
                                            unique_id = f"{base}-{num:02d}"
                                        else:
                                            unique_id = f"{item['id_preview']}-{i+1:04d}"
                                        
                                        # Check if this ID already exists
                                        existing = supabase.table("inventory").select("Item_ID").eq("Item_ID", unique_id).execute()
                                        if existing.data:
                                            st.warning(f"⚠️ Skipped {unique_id} - already exists in inventory")
                                            items_skipped += 1
                                            continue
                                        
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
                                    # Bulk item - check if exists in current inventory
                                    if not safe_df.empty:
                                        mask = (safe_df['Category'] == item['category']) & (safe_df['Material'] == item['material'])
                                        if mask.any():
                                            current_qty = safe_df.loc[mask, 'Footage'].values[0]
                                            new_qty = current_qty + item['total_added']
                                            bulk_id = safe_df.loc[mask, 'Item_ID'].values[0]
                                            update_stock(bulk_id, new_qty, st.session_state.receiving_operator, 
                                                       f"Received {item['total_added']} {item['unit_label'].lower()} (PO: {st.session_state.current_po})")
                                        else:
                                            # Create new bulk item
                                            unique_id = f"{item['category'].upper()}-BULK-{datetime.now().strftime('%Y%m%d')}"
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
                                            items_added += 1
                                    else:
                                        # No inventory yet - create first bulk item
                                        unique_id = f"{item['category'].upper()}-BULK-{datetime.now().strftime('%Y%m%d')}"
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
                                        items_added += 1
                                
                                # Audit log for each item
                                log_entry = {
                                    "Item_ID": item['id_preview'],
                                    "Action": "Received",
                                    "User": st.session_state.receiving_operator,
                                    "Timestamp": datetime.now().isoformat(),
                                    "Details": f"PO: {st.session_state.current_po} | {item['item_count']} × {item['material']} ({item['total_added']} {item['unit_label'].lower()})"
                                }
                                supabase.table("audit_log").insert(log_entry).execute()
                            
                            st.cache_data.clear()
                            
                            # Summary message
                            if items_added > 0 and items_skipped == 0:
                                st.success(f"✅ Successfully received {items_added} item(s) for PO: {st.session_state.current_po}!")
                                st.balloons()
                            elif items_added > 0 and items_skipped > 0:
                                st.warning(f"⚠️ Partially completed: {items_added} added, {items_skipped} skipped (duplicates)")
                            else:
                                st.error(f"❌ No items added - all {items_skipped} were duplicates!")
                            
                            # Clear cart
                            st.session_state.receiving_cart = []
                            st.rerun()
                        
                        except Exception as e:
                            st.error(f"❌ Failed to process items: {e}")
        
        with col_clear:
            if st.button("🗑️ Clear Cart", use_container_width=True, key="clear_receiving_cart"):
                st.session_state.receiving_cart = []
                st.rerun()
    
    elif not st.session_state.receiving_cart:
        st.info("👆 Add items to start building your receiving batch")
    
    # ── Receipt Report Section ─────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("""
        <div style="text-align: center; padding: 20px 0;">
            <h2 style="color: #1e40af; margin: 0;">📄 Receipt Report Generator</h2>
            <p style="color: #64748b; margin-top: 8px;">Generate professional PDF reports for items received under specific Purchase Orders</p>
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
                    
                    # Generate PDF
                    pdf_buffer = generate_receipt_pdf(
                        po_num=report_po_num,
                        df=report_df,
                        operator=st.session_state.get('username', 'Operator')
                    )
                    
                    file_name = f"Receipt_{report_po_num.replace(' ', '_')}.pdf"
                    
                    # Download button
                    st.download_button(
                        label="📥 Download PDF Report",
                        data=pdf_buffer.getvalue(),
                        file_name=file_name,
                        mime="application/pdf",
                        key=f"dl_{report_po_num}",
                        type="secondary"
                    )
                    
                    # Email functionality
                    if export_mode == "Download & Email":
                        with st.spinner("📧 Sending email to admin..."):
                            pdf_buffer.seek(0)
                            
                            email_success = send_receipt_email(
                                admin_email="tmilazi@gmail.com",
                                po_num=report_po_num,
                                pdf_buffer=pdf_buffer,
                                operator=st.session_state.get('username', 'Operator')
                            )
                            
                            if email_success:
                                st.success(f"✅ PDF report emailed to admin!")
                            else:
                                st.warning("⚠️ PDF generated but email failed.")
                    else:
                        st.success("✅ PDF report generated successfully!")
                        
            except Exception as e:
                st.error(f"❌ Error generating report: {e}")
                    
import openai
import plotly.express as px
import plotly.graph_objects as go

with tab5:
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
        
with tab6:
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
        st.error(f"Audit Log Display Error: {e}")
