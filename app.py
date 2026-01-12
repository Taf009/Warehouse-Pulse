# ── TAB 2: Production Log ────────────────────────────────────────────────────────
with tab2:
    st.subheader("📋 Production Log - Multi-Size Orders")

    # Guard rails
    if df.empty:
        st.warning("⚠️ No inventory data found. Please add items first.")
        st.stop()

    category_col = next((c for c in df.columns if c.lower() == 'category'), None)
    if not category_col:
        st.error("Column 'Category' not found in inventory data.")
        st.stop()

    # Initialize session state
    if "coil_lines" not in st.session_state:
        st.session_state.coil_lines = []
    if "roll_lines" not in st.session_state:
        st.session_state.roll_lines = []

    # Helper to check if a line is "active" (worth showing)
    def is_active_line(line):
        return (
            line.get("pieces", 0) > 0 or
            len(line.get("items", [])) > 0 or
            line.get("use_custom", False)
        )

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
    coil_extra = st.number_input("Extra Inch Allowance per piece (Coils)", min_value=0.0, value=0.5, step=0.1, key="coil_extra")

    last_coil_selected = None
    active_coil_indices = []
    for i, line in enumerate(st.session_state.coil_lines):
        if is_active_line(line):
            active_coil_indices.append(i)
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 1.2, 1.2, 0.4])
                with c1:
                    line["display_size"] = st.selectbox("Size", list(SIZE_DISPLAY.keys()), key=f"c_size_{i}")
                with c2:
                    line["pieces"] = st.number_input("Pieces", min_value=0, step=1, key=f"c_pcs_{i}")
                with c3:
                    line["waste"] = st.number_input("Waste (ft)", min_value=0.0, step=0.5, key=f"c_waste_{i}")
                with c4:
                    if st.button("🗑", key=f"del_coil_{i}"):
                        st.session_state.coil_lines.pop(i)
                        st.rerun()

                line["use_custom"] = st.checkbox("Use custom inches instead of standard size", value=line.get("use_custom", False), key=f"c_custom_chk_{i}")

                current_custom = line.get("custom_inches")
                safe_value = 12.0 if current_custom is None else max(0.1, float(current_custom))

                if line["use_custom"]:
                    line["custom_inches"] = st.number_input("Custom length per piece (inches)", min_value=0.1, value=safe_value, step=0.25, key=f"c_custom_in_{i}")
                else:
                    line["custom_inches"] = 0.0

                current_defaults = [opt for opt in line["items"] if opt in coil_options]
                if not current_defaults and last_coil_selected and last_coil_selected in coil_options:
                    current_defaults = [last_coil_selected]

                line["items"] = st.multiselect("Select source coil(s)", options=coil_options, default=current_defaults, key=f"c_source_{i}")

                if line["items"]:
                    last_coil_selected = line["items"][0]

    if st.button("➕ Add coil size", use_container_width=True):
        st.session_state.coil_lines.append({"display_size": "#2", "pieces": 0, "waste": 0.0, "items": [], "use_custom": False, "custom_inches": 12.0})
        st.rerun()

    st.divider()

    # ── ROLLS SECTION ───────────────────────────────────────────────────────────────
    st.markdown("### 🗞️ Rolls Production")
    roll_extra = st.number_input("Extra Inch Allowance per piece (Rolls)", min_value=0.0, value=0.5, step=0.1, key="roll_extra")

    last_roll_selected = None
    for i, line in enumerate(st.session_state.roll_lines):
        if is_active_line(line):
            with st.container(border=True):
                r1, r2, r3, r4 = st.columns([3, 1.2, 1.2, 0.4])
                with r1:
                    line["display_size"] = st.selectbox("Size", list(SIZE_DISPLAY.keys()), key=f"r_size_{i}")
                with r2:
                    line["pieces"] = st.number_input("Pieces", min_value=0, step=1, key=f"r_pcs_{i}")
                with r3:
                    line["waste"] = st.number_input("Waste (ft)", min_value=0.0, step=0.5, key=f"r_waste_{i}")
                with r4:
                    if st.button("🗑", key=f"del_roll_{i}"):
                        st.session_state.roll_lines.pop(i)
                        st.rerun()

                line["use_custom"] = st.checkbox("Use custom inches instead of standard size", value=line.get("use_custom", False), key=f"r_custom_chk_{i}")

                current_custom = line.get("custom_inches")
                safe_value = 12.0 if current_custom is None else max(0.1, float(current_custom))

                if line["use_custom"]:
                    line["custom_inches"] = st.number_input("Custom length per piece (inches)", min_value=0.1, value=safe_value, step=0.25, key=f"r_custom_in_{i}")
                else:
                    line["custom_inches"] = 0.0

                current_defaults = [opt for opt in line["items"] if opt in roll_options]
                if not current_defaults and last_roll_selected and last_roll_selected in roll_options:
                    current_defaults = [last_roll_selected]

                line["items"] = st.multiselect("Select source roll(s)", options=roll_options, default=current_defaults, key=f"r_source_{i}")

                if line["items"]:
                    last_roll_selected = line["items"][0]

    if st.button("➕ Add roll size", use_container_width=True):
        st.session_state.roll_lines.append({"display_size": "#2", "pieces": 0, "waste": 0.0, "items": [], "use_custom": False, "custom_inches": 12.0})
        st.rerun()

    st.divider()

    # ... (the rest remains the same: helper function + submission form + processing logic)
    # Make sure to keep your existing process_production_line function and form/submit block here
