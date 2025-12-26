import streamlit as st
import pandas as pd
import datetime
import os

# --- DATABASE SETUP ---
DB_FILE = "coil_inventory.csv"
LOG_FILE = "action_log.csv" # New file for history

if not os.path.exists(LOG_FILE):
    log_df = pd.DataFrame(columns=["Timestamp", "Action", "Coil_ID", "Material", "Value", "Waste_FT", "Location"])
    log_df.to_csv(LOG_FILE, index=False)

# Helper function to record history
def record_action(action, coil_id, material, value, waste=0, loc=""):
    new_log = pd.DataFrame([{
        "Timestamp": datetime.datetime.now(),
        "Action": action,
        "Coil_ID": coil_id,
        "Material": material,
        "Value": value,
        "Waste_FT": waste,
        "Location": loc
    }])
    new_log.to_csv(LOG_FILE, mode='a', header=False, index=False)

# ... (Previous Tabs 1, 2, and 3 logic remains here) ...

# --- NEW TAB 4: REPORTS & SUMMARY ---
with st.tabs(["Dashboard", "Production Log", "Warehouse Management", "Daily Summary"])[3]:
    st.subheader("📊 End-of-Day Pulse Check")
    
    log_data = pd.read_csv(LOG_FILE)
    log_data['Timestamp'] = pd.to_datetime(log_data['Timestamp'])
    
    # Filter for today only
    today = datetime.datetime.now().date()
    today_logs = log_data[log_data['Timestamp'].dt.date == today]
    
    if today_logs.empty:
        st.info("No activity recorded yet today.")
    else:
        # 1. High-Level Stats
        col1, col2, col3 = st.columns(3)
        total_used = today_logs[today_logs['Action'] == "Cut"]['Value'].sum()
        total_waste = today_logs[today_logs['Action'] == "Cut"]['Waste_FT'].sum()
        
        col1.metric("Total Footage Used", f"{total_used:.2f} ft")
        col2.metric("Total Waste Recorded", f"{total_waste:.2f} ft")
        
        # Calculate Efficiency percentage using LaTeX for clarity
        # $$ \text{Efficiency} = \frac{\text{Total Used} - \text{Waste}}{\text{Total Used}} \times 100 $$
        if total_used > 0:
            eff = ((total_used - total_waste) / total_used) * 100
            col3.metric("Material Efficiency", f"{eff:.1f}%")

        # 2. Material Breakdown
        st.write("### Usage by Material")
        usage_summary = today_logs[today_logs['Action'] == "Cut"].groupby("Material")['Value'].sum()
        st.bar_chart(usage_summary)

        # 3. The "Pick List" for Tomorrow
        st.write("### Low Stock Alert (Order List)")
        low_stock = df[df['Footage'] < 500] # Assuming 500ft is the alert level
        if not low_stock.empty:
            st.warning("The following coils are nearly empty and should be replaced on the line:")
            st.table(low_stock[['Coil_ID', 'Material', 'Location', 'Footage']])
