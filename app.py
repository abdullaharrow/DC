import streamlit as st
import math
from collections import defaultdict
from config import items, packing_mode, boxes_pp_heading_name, amount_per_dozen
from db import (
    init_db,
    create_dc_entry,
    fetch_dc_entry,
    add_dc_delivery_details,
    get_dc_delivery_details,
    get_dc_cumulative_delivery_details,
    get_dc_delivery_details_with_date_filter,
    update_dc_row,
    update_dc_delivery_entry,
    get_invoice_delivery_details,
    create_invoice,
    get_uncompleted_dcs,
    get_all_invoices,
    delete_dc_delivery_entry,
    delete_dc_row,
    delete_dc_entry
)
import pandas as pd
from datetime import datetime, date

# --- Wide Layout ---
st.set_page_config(page_title="DC Management", layout="wide")

# --- Initialize DB ---
init_db()

# --- Compute Boxes ---
def compute_boxes(item, dozens):
    total_units = dozens * 12
    return round(total_units / packing_mode.get(item, 1), 2)

# --- Tabs ---
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "➕ New DC Entry",
    "📋 View DC Details",
    "✏️ Update DC Details",
    "📋 Create Invoice Details",
    "🔍 View Invoice Details",
    "🕒 Pending DC Details",
    "🖨️ Print Invoice",
    "📊 Statistics"
])


# ============== TAB 1: NEW DC ENTRY ==============
with tab1:
    st.title("📋 Enter DC Details")

    # Top-level input
    dc_entry = st.text_input("DC_Entry_Number")

    # Initialize a placeholder container for dynamic rows
    if "temp_rows" not in st.session_state:
        st.session_state.temp_rows = [{"item": items[0], "dozen": 1}]

    rows = st.session_state.temp_rows
    st.markdown("### 📝 Item Entries")
    header = st.columns([2, 2, 2, 1])
    header[0].markdown("**Item**")
    header[1].markdown("**No. of Dozen**")
    header[2].markdown(f"**{boxes_pp_heading_name}**")
    header[3].markdown("")

    # Track rows to delete
    rows_to_delete = []

    for i, row in enumerate(rows):
        cols = st.columns([2, 2, 2, 1])
        row["item"] = cols[0].selectbox("Item", items, index=items.index(row["item"]), key=f"item_{i}", label_visibility="collapsed")
        row["dozen"] = cols[1].number_input("dozen", min_value=1, value=row["dozen"], step=1, key=f"dozen_{i}", label_visibility="collapsed")
        boxes = compute_boxes(row["item"], row["dozen"])
        cols[2].number_input("boxes", value=boxes, disabled=True, key=f"box_{i}", label_visibility="collapsed")

        if cols[3].button("❌", key=f"del_{i}"):
            rows_to_delete.append(i)

    for i in sorted(rows_to_delete, reverse=True):
        del rows[i]

    if rows_to_delete:
        st.rerun()
    
    if st.button("➕ Add Row"):
        rows.append({"item": items[0], "dozen": 1})
        st.rerun()

    if st.button("💾 Save"):
        if not dc_entry:
            st.warning("⚠️ Please enter a DC Entry Number.")
        elif not rows:
            st.warning("⚠️ No rows to save.")
        else:
            try:
                create_dc_entry(
                    dc_entry,
                    [
                        {
                            "Item": row["item"],
                            "Dozen": row["dozen"],
                            "Boxes": compute_boxes(row["item"], row["dozen"])
                        }
                        for row in rows
                    ]
                )
                st.success("✅ Saved successfully to database!")
                st.session_state.temp_rows = [{"item": items[0], "dozen": 1}]
            except Exception as e:
                st.error(f"❌ Error saving entry: {e}")

# ============== TAB 2: VIEW EXISTING DC ==============
with tab2:
    st.title("📋 View DC Entry")

    dc_input = st.text_input("Enter DC_Entry_Number to view:")

    if st.button("🔍 Search"):
        st.session_state.search_dc = dc_input  # Persist search

    if "search_dc" in st.session_state and st.session_state.search_dc:  
        search_dc = st.session_state.search_dc 
        dc_data, created_at = fetch_dc_entry(search_dc)
        if not dc_data:
            st.warning("❌ No entry found with that DC number.")
        else:
            # Display created_at date
            if created_at:
                created_at_dt = datetime.fromisoformat(created_at)
                st.info(f"📅 Created at: {created_at_dt.strftime('%d-%m-%Y %H:%M:%S')}")
            
            df = pd.DataFrame(dc_data)

            # Add Sl.no column at the beginning
            df.insert(0, "Sl.no", range(1, len(df) + 1))

            # Fetch total delivered
            delivered_df = get_dc_cumulative_delivery_details(search_dc)

            # Merge on item
            df = df.merge(delivered_df, on="Item", how="left")

             # Fill NaN in total_boxes with 0 (in case no delivery yet)
            df["total_delivered"] = df["total_delivered"].fillna(0)

            # Calculate delivery completion status
            df["is_delivery_completed"] = df["total_delivered"] >= df["Boxes"]

                        # Styling function
            # Replace boolean with icons
            df["is_delivery_completed"] = df["is_delivery_completed"].map({True: "✅", False: "❌"})

            # Optional: Add styling for the icons column (make it bold or center)
            def style_icon(val):
                return "text-align: center; font-weight: bold;"

            styled_df = df.style.set_properties(
                subset=["is_delivery_completed"], **{"text-align": "center", "font-weight": "bold"}
            ).format({
                "total_delivered": "{:.2f}",
                "Boxes": "{:.2f}"
            }) 

            all_delivered = df["is_delivery_completed"].eq("✅").all()

            # Show DC Number with status icon
            status_icon = "✅ Completed" if all_delivered else "❌ Not Completed"

            st.markdown(f"### DC Number: `{search_dc}` {status_icon}")
            st.dataframe(styled_df, hide_index=True, use_container_width=True)

            with st.expander("Add Delivery Details to This DC"):
                # 📥 Form to append new box entry
                st.markdown("### Add Delivery Details to This DC")
                with st.form(key="add_box_form"):
                    col1, col2, col3 = st.columns(3)
                    date = col1.date_input("Date", value=date.today())
                    filtered_items = [row["Item"] for row in dc_data]
                    item = col2.selectbox("Item", filtered_items)
                    boxes = col3.number_input(boxes_pp_heading_name, min_value=1, step=1)
                    
                    submitted = st.form_submit_button("💾 Save Entry")
                    if submitted:
                        try:
                            add_dc_delivery_details(search_dc, date, item, boxes)
                            st.success("✅ Entry added successfully!")
                            # st.rerun()  # Refresh the page to show updated data
                        except Exception as e:
                            st.error(f"❌ Error adding entry: {e}")

            with st.expander("Existing Delivery Details of the DC"):
                st.markdown("### 📦 Delivery Summary for DC: `" + search_dc + "`") 
                summary_df = get_dc_delivery_details(search_dc)
                if not summary_df.empty:
                    st.dataframe(summary_df, hide_index=True, use_container_width=True)
                else:
                    st.info("No delivery entries found for this DC.")       

# ============== TAB 3: UPDATE DC DETAILS ==============
with tab3:
    st.title("✏️ Update DC Details")

    update_dc = st.text_input("Enter DC_Entry_Number to update")

    if st.button("🔍 Load DC Details"):
        st.session_state.update_dc = update_dc
        
    if st.button("🗑️ Delete DC"):
        delete_dc_entry(update_dc)
        st.session_state.update_dc = None
        st.success(f"✅ DC Deleted Successfully")

    if "update_dc" in st.session_state and st.session_state.update_dc:
        update_dc = st.session_state.update_dc
        
        # FIX: Unpack the tuple correctly (dc_row_data, created_at)
        dc_row_data, created_at = fetch_dc_entry(update_dc)
        
        if dc_row_data:
            with st.expander("🗃 Update Master Row (Planned Quantities)", expanded=True):
                row_df = pd.DataFrame(dc_row_data)
                st.write("Current Planned Totals:")
                st.dataframe(row_df, use_container_width=True, hide_index=True)

                # Select item to update
                filtered_items = [row["Item"] for row in dc_row_data]
                selected_item = st.selectbox("Select Item to Update in DC Rows", filtered_items)

                # Get existing data for the selected item
                selected_row = next(row for row in dc_row_data if row["Item"] == selected_item)

                col1, col2 = st.columns(2)
                with col1:
                    new_dozen = st.number_input("New Dozen", min_value=0, step=1, value=int(selected_row["Dozen"]))
                with col2:
                    # Auto-compute boxes based on dozens
                    new_boxes = compute_boxes(selected_item, new_dozen)
                    st.number_input("New calculated boxes", value=new_boxes, disabled=True)

                if st.button("💾 Update Planned Quantity"):
                    try:
                        update_dc_row(update_dc, selected_item, new_dozen, new_boxes)
                        st.success(f"✅ Master row for '{selected_item}' updated successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to update dc_rows: {e}")
                
                if st.button("🗑️ Delete Selected Item From DC"):
                    try:
                        delete_dc_row(update_dc, selected_item)
                        st.success(f"✅ Deleted the selected item '{selected_item}'")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to update dc_rows: {e}")
        else:
            st.warning("❌ No DC found with that number.")

        st.markdown("---")

        with st.expander("🚚 Update Specific Delivery Entry (Delivery History)"):
            delivery_df = get_dc_delivery_details(update_dc)

            if not delivery_df.empty:
                st.write("Select a delivery record to modify:")
                st.dataframe(delivery_df, use_container_width=True, hide_index=True)

                # Create a unique list of identifiers for selectbox
                # We combine Date and Item to help the user pick the right row
                delivery_df['selection_label'] = delivery_df['date'] + " | " + delivery_df['Item_Name']
                selected_label = st.selectbox("Select Delivery Record", delivery_df['selection_label'])

                # Filter data for the selected record
                target_row = delivery_df[delivery_df['selection_label'] == selected_label].iloc[0]
                
                old_date_str = target_row["date"]
                selected_item_name = target_row["Item_Name"]
                old_box_val = float(target_row["Delivered_Boxes"])
                
                # Convert string date back to date object for the input
                old_date_obj = datetime.strptime(old_date_str, "%Y-%m-%d").date()

                col1, col2 = st.columns(2)
                with col1:
                    new_box_val = st.number_input("Update Boxes Delivered", min_value=0.0, step=1.0, value=old_box_val)
                with col2:
                    change_date = st.checkbox("Change Delivery Date?")
                    new_date = None
                    if change_date:
                        new_date = st.date_input("New Delivery Date", value=old_date_obj)

                if st.button("💾 Update Delivery Record"):
                    try:
                        # Call db function
                        update_dc_delivery_entry(update_dc, old_date_obj, selected_item_name, new_box_val, new_date)
                        st.success("✅ Delivery history updated successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to update delivery entry: {e}")
                
                if st.button("🗑️ Delete Delivery Record"):
                    try:
                        delete_dc_delivery_entry(update_dc, old_date_obj, selected_item_name)
                        st.success("✅ Delivery history updated successfully.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Failed to delete delivery entry: {e}")
            else:
                st.info("No delivery records found for this DC.")
# ============== TAB 4: Create Invoice Details ==============
with tab4:
    st.title("📋 Create Invoice Details")

    # --- Date range selection ---
    col1, col2 = st.columns(2)
    with col1:
        from_date = st.date_input("📅 From Date", value=date.today().replace(day=1))
    with col2:
        to_date = st.date_input("📅 To Date", value=date.today())
    
    # Validate date range
    if from_date > to_date:
        st.error("❌ 'From Date' cannot be after 'To Date'")
    else:
        df = get_dc_delivery_details_with_date_filter(from_date, to_date)
        if df.empty:
            st.warning("⚠️ No delivery entries found for this date range.")
        else:
            # 🔹 Add Packing Mode
            df["Packing Mode"] = df["item"].apply(lambda x: packing_mode.get(x, 0))

            # 🔹 Add Dozens = (Boxes × Packing Mode) / 12
            df["Dozens"] = df.apply(
                lambda row: (row["boxes"] * packing_mode.get(row["item"], 0)) / 12, axis=1
            )

            st.dataframe(df, hide_index=True, use_container_width=True)
            invoice_no = st.text_input("📦 Invoice Number (e.g., INV_001)")
            if st.button("✅ Create Invoice"):
                if not invoice_no.strip():
                    st.error("❌ Invoice number cannot be empty")
                else:
                    try:
                        create_invoice(invoice_no.strip(), from_date, to_date)
                        st.success(f"✅ Invoice '{invoice_no}' created!")
                    except sqlite3.IntegrityError:
                        st.error(f"❌ Invoice '{invoice_no}' already exists!")

# ============== TAB 5: View Invoice Details ==============
with tab5:
    st.title("🔍 View Invoice Details")

    invoice_search = st.text_input("Enter Invoice Number (e.g., INV_001)")

    if st.button("🔎 Fetch Invoice"):
        from_date, to_date, df, created_at = get_invoice_delivery_details(invoice_search.strip())

        if from_date is None:
            st.error(f"❌ No invoice found with number: {invoice_search}")
        else:
            st.info(f"📅 Invoice covers deliveries from **{from_date}** to **{to_date}**")
            if df.empty:
                st.warning("⚠️ No delivery records found in this invoice range.")
            else:
                df.insert(0, "Sl.no", range(1, len(df) + 1))

                # 🔹 Add Packing Mode
                df["Packing Mode"] = df["item"].apply(lambda x: packing_mode.get(x, 0))

                # 🔹 Add Dozens (rounded to 2 decimals)
                df["Dozens"] = df.apply(
                    lambda row: (row["boxes"] * packing_mode.get(row["item"], 0)) / 12, axis=1
                ).round(2)

                # Compute Amount using packing_mode & amount_per_dozen
                def compute_amount(row):
                    pieces = row["boxes"] * packing_mode.get(row["item"], 0)   # total pieces
                    dozens = pieces / 12                                       # convert to dozens
                    rate = amount_per_dozen.get(row["item"], 0)                # rate per dozen
                    return dozens * rate

                df["Amount"] = df.apply(compute_amount, axis=1)

                # Format nicely
                styled_df = df.style.format({
                    "boxes": "{:.2f}",
                    "Amount": "₹{:.2f}",
                    "Dozens": "{:.2f}"
                })

                st.dataframe(styled_df, hide_index=True, use_container_width=True)

                # Show Total Amount at bottom
                total_amount = df["Amount"].sum()
                st.subheader(f"💰 Total Invoice Amount: ₹{total_amount:,.2f}")

with tab6:
    st.title("🕒 Pending DC Details")

    uncompleted_df = get_uncompleted_dcs()

    if uncompleted_df.empty:
        st.success("🎉 All DCs are completed!")
    else:
        # Group by DC number
        for dc_num, group in uncompleted_df.groupby("dc_entry_number"):
            with st.expander(f"📋 DC Number: {dc_num} (Pending Items: {len(group)})"):
                # Add Sl.no
                group = group.reset_index(drop=True)
                group.insert(0, "Sl.no", range(1, len(group) + 1))

                # Add Pending Boxes column
                group["Pending_Boxes"] = group["planned_boxes"] - group["delivered_boxes"]

                # Display with formatting
                styled_group = group.style.format({
                    "planned_boxes": "{:.2f}",
                    "delivered_boxes": "{:.2f}",
                    "Pending_Boxes": "{:.2f}"
                })

                st.dataframe(styled_group, hide_index=True, use_container_width=True)

# ================= TAB 7: PRINT OUT =================
# ================= TAB 7: PRINT OUT =================
# ================= TAB 7: PRINT OUT =================
# ================= TAB 7: PRINT OUT =================
with tab7:
    st.title("🖨️ Print Invoice")

    invoice_numbers = [inv['invoice_number'] for inv in get_all_invoices()]
    if not invoice_numbers:
        st.info("⚠️ No invoices available to print.")
    else:
        invoice_search = st.selectbox("Select Invoice Number for Print Out", options=invoice_numbers)

        if invoice_search:
            from_date, to_date, df, created_at = get_invoice_delivery_details(invoice_search.strip())
            if from_date is None or df.empty:
                st.warning("⚠️ No invoice found or no data available for this invoice.")
            else:
                # --- Prepare dataframe fields ---
                invoice_date_str = created_at.strftime("%d-%m-%Y")
                df.insert(0, "Sl.no", range(1, len(df) + 1))

                # Compute Packing Mode, Dozens, Rate, Amount
                df["Pack Mode"] = df["item"].apply(lambda x: packing_mode.get(x, 0))
                df["Dozens"] = df.apply(lambda row: round((row["boxes"] * packing_mode.get(row["item"], 0)) / 12, 2), axis=1)
                df["Rate"] = df["item"].apply(lambda x: amount_per_dozen.get(x, 0))
                df["Amount"] = (df["Dozens"] * df["Rate"]).round(0).astype(int)

                # Units: convert to int when whole numbers (remove .0)
                def display_units(u):
                    try:
                        if isinstance(u, float) and u.is_integer():
                            return int(u)
                        return u
                    except:
                        return u
                df["Units"] = df["boxes"].apply(lambda x: display_units(x))

                # Rename for print
                df.rename(columns={
                    "dc_entry_number": "DC No",
                    "date": "Date",
                    "item": "Particular"
                }, inplace=True)

                print_cols = ["Sl.no", "DC No", "Date", "Pack Mode", "Units", "Particular", "Dozens", "Rate", "Amount"]

                # --- ReportLab and PDF setup ---
                from io import BytesIO
                from reportlab.lib.pagesizes import A4
                from reportlab.lib import colors
                from reportlab.lib.styles import ParagraphStyle
                from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
                from reportlab.pdfbase import pdfmetrics
                from reportlab.pdfbase.ttfonts import TTFont

                # Try to register Times New Roman (if available), otherwise fallback to built-ins
                try:
                    pdfmetrics.registerFont(TTFont('TimesNewRoman', 'Times New Roman.ttf'))
                    pdfmetrics.registerFont(TTFont('TimesNewRoman-Bold', 'Times New Roman Bold.ttf'))
                    base_font = 'TimesNewRoman'
                    bold_font = 'TimesNewRoman-Bold'
                except Exception:
                    base_font = 'Times-Roman'
                    bold_font = 'Times-Bold'

                # Header function (Bill No & Date in bold)
                def header(canvas, doc):
                    canvas.saveState()
                    width, height = A4
                    margin = 50

                    # Outer border
                    border_thickness_mm = 0.20
                    border_thickness_pts = border_thickness_mm * 72 / 25.4
                    canvas.setLineWidth(border_thickness_pts)
                    canvas.setStrokeColor(colors.black)
                    canvas.rect(margin, margin, width - 2 * margin, height - 1.5 * margin)

                    y_top = height - margin
                    canvas.setFont(base_font, 12)
                    canvas.drawString(margin + 2, y_top, "PAN No: DJOPB0004F")
                    canvas.drawRightString(width - margin - 2, y_top, "Mob: 8825766745")

                    canvas.setFont(base_font, 14)
                    canvas.drawCentredString(width / 2.0, y_top - 20, "JOB INVOICE")

                    canvas.setFont(base_font, 12)
                    canvas.drawCentredString(width / 2.0, y_top - 40, "SHAHANAZ BANU")
                    canvas.drawCentredString(width / 2.0, y_top - 55,
                                             "No : 39/16/2, Nayar Vardha Pillai Street, Roypettah, Chennai- 600014")

                    # Bill No & Date in bold
                    bill_date_y = y_top - 75
                    canvas.setFont(bold_font, 12)
                    canvas.drawString(margin + 2, bill_date_y, f"Bill No: {invoice_search}")
                    canvas.drawRightString(width - margin - 2, bill_date_y, f"Date: {invoice_date_str}")

                    # Box around Bill No & Date
                    canvas.setLineWidth(0.5)
                    canvas.rect(margin, bill_date_y - 2, width - 2 * margin, 15, stroke=1, fill=0)

                    # Party Info
                    y_party = y_top - 95
                    canvas.setFont(base_font, 12)
                    canvas.drawString(margin + 2, y_party, "Party : SINGHI TEXTORIUM")
                    canvas.drawString(margin + 37, y_party - 15, "No : 145, G.N. Street,")
                    canvas.drawString(margin + 37, y_party - 30, "Chennai - 600001.")
                    canvas.drawCentredString((width / 2.0) + 72, y_party, "GSTIN : 33AAAFS8731L1Z0")
                    canvas.drawCentredString((width / 2.0) + 50, y_party - 15, "Transport: Own")
                    canvas.drawCentredString((width / 2.0) + 124, y_party - 30, "Apply Reverse Charges Yes/No")
                    canvas.restoreState()

                # Generate PDF when button clicked
                if st.button("💾 Save as PDF"):
                    pdf_buffer = BytesIO()
                    doc = SimpleDocTemplate(
                        pdf_buffer,
                        pagesize=A4,
                        leftMargin=54,
                        rightMargin=54,
                        topMargin=54 + 140,
                        bottomMargin=54
                    )

                    normal_style = ParagraphStyle(name='Normal', fontName=base_font, fontSize=12, leading=14)

                    elements = []

                    # Prepare table rows and chunk into pages
                    all_rows = df[print_cols].values.tolist()
                    header_row = print_cols
                    chunk_size = 20
                    chunks = [all_rows[i:i + chunk_size] for i in range(0, len(all_rows), chunk_size)]

                    # column widths
                    col_widths = [30, 40, 65, 60, 34, 150, 42, 32, 42]
                    # ✅ PERFECT-ALIGN FOOTER WITH RIGHT-SIDE PRINT
                    footer_texts = [
                        ["1. Handkerchiefs Goods 6213", "For SHAHANAZ BANU"],
                        ["2. Packing of Handkerchiefs Not for sale", ""],
                        ["3. Good Against party DC and Date                    ________________________", ""],
                        ["4. SAC Code: 9988                                              ________________________", ""],
                        ["5. GST will be paid by Principle                          ________________________", ""],
                        ["Below 20 Lacs Unregistered Manufacturer         ________________________", ""]
                    ]

                    grand_total = df["Amount"].sum()

                    for page_index, chunk in enumerate(chunks):
                        table_data = [header_row] + chunk

                        if page_index == len(chunks) - 1:
                            total_row = ["GRAND TOTAL", "", "", "", "", "", "", "", grand_total]
                            table_data.append(total_row)

                        table = Table(table_data, colWidths=col_widths, repeatRows=1)

                        table_style = TableStyle([
                            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
                            ('FONTNAME', (0, 0), (-1, -1), base_font),
                            ('FONTSIZE', (0, 0), (-1, -1), 12),
                            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ])

                        if page_index == len(chunks) - 1:
                            last_row_idx = len(table_data) - 1
                            table_style.add('SPAN', (0, last_row_idx), (7, last_row_idx))
                            table_style.add('ALIGN', (8, last_row_idx), (8, last_row_idx), 'CENTER')
                            table_style.add('FONTSIZE', (0, last_row_idx), (8, last_row_idx), 13)
                            table_style.add('FONTNAME', (0, last_row_idx), (0, last_row_idx), bold_font)
                            table_style.add('FONTNAME', (8, last_row_idx), (8, last_row_idx), bold_font)

                        table.setStyle(table_style)
                        elements.append(table)
                        elements.append(Spacer(1, 8))

                        # FOOTER LOOP (clean alignment)
                        for line in footer_texts:
                            footer_table = Table([line], colWidths=[350, 150])
                            footer_table.setStyle(TableStyle([
                                ('FONTNAME', (0, 0), (-1, -1), base_font),
                                ('FONTSIZE', (0, 0), (-1, -1), 12),
                                ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
                                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                            ]))
                            elements.append(footer_table)
                            elements.append(Spacer(1, 5))

                        if page_index < len(chunks) - 1:
                            elements.append(PageBreak())

                    doc.build(elements, onFirstPage=header, onLaterPages=header)

                    st.success("✅ PDF generated successfully")
                    st.download_button(
                        label="⬇️ Download Invoice PDF",
                        data=pdf_buffer.getvalue(),
                        file_name=f"{invoice_search}.pdf",
                        mime="application/pdf"
                    )
# ================= TAB 8: STATISTICS =================
# ================= TAB 8: STATISTICS =================
with tab8:
    st.title("📊 Statistics")

    # Date range selector
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("📅 From Date", value=date.today().replace(day=1), key="stats_from_date")
    with col2:
        end_date = st.date_input("📅 To Date", value=date.today(), key="stats_to_date")

    if start_date > end_date:
        st.error("❌ 'From Date' cannot be after 'To Date'")
    else:
        try:
            # Fetch all deliveries in range
            df = get_dc_delivery_details_with_date_filter(start_date, end_date)

            if df.empty:
                st.warning("⚠️ No records found for the selected date range.")
            else:
                # --- Compute metrics ---
                df["Packing Mode"] = df["item"].apply(lambda x: packing_mode.get(x, 0))
                df["Dozens"] = df.apply(lambda row: (row["boxes"] * row["Packing Mode"]) / 12, axis=1)

                # Amount calculation
                def compute_amount(row):
                    rate = amount_per_dozen.get(row["item"], 0)
                    return row["Dozens"] * rate

                df["Amount"] = df.apply(compute_amount, axis=1)

                # --- Summary metrics ---
                total_dozens = df["Dozens"].sum()
                total_amount = df["Amount"].sum()

                # --- DC completion stats ---
                pending_dc_df = get_uncompleted_dcs()
                completed_dcs = len(set(df["dc_entry_number"])) - len(pending_dc_df["dc_entry_number"].unique()) if not pending_dc_df.empty else len(set(df["dc_entry_number"]))
                pending_dcs = len(pending_dc_df["dc_entry_number"].unique()) if not pending_dc_df.empty else 0

                # --- Show summary metrics ---
                st.markdown("### 📈 Summary Overview")
                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("📦 Total Dozens", f"{total_dozens:,.2f}")
                kpi2.metric("💰 Total Amount Earned", f"₹{total_amount:,.2f}")
                kpi3.metric("✅ Completed DCs", f"{completed_dcs}")
                kpi4.metric("⏳ Pending DCs", f"{pending_dcs}")

                st.markdown("---")

                # --- Detailed data table ---
                st.markdown("### 📊 Detailed Delivery Data")
                df_display = df[["date", "dc_entry_number", "item", "boxes", "Packing Mode", "Dozens", "Amount"]]
                df_display.rename(columns={
                    "date": "Date",
                    "dc_entry_number": "DC Number",
                    "item": "Item",
                    "boxes": "Boxes",
                }, inplace=True)

                df_display = df_display.sort_values(by="Date", ascending=True).reset_index(drop=True)
                df_display.insert(0, "Sl.No", range(1, len(df_display) + 1))
                st.dataframe(df_display, use_container_width=True, hide_index=True)

                st.markdown("---")

                # --- New Section: Cumulative Summary by Item ---
                st.markdown("### 🧮 Cumulative Summary by Item")
                item_summary = df.groupby("item", as_index=False).agg({
                    "Dozens": "sum",
                    "Amount": "sum"
                }).sort_values(by="Amount", ascending=False)

                item_summary.rename(columns={
                    "item": "Item (Particular)",
                    "Dozens": "Total Dozens",
                    "Amount": "Total Amount"
                }, inplace=True)

                item_summary.insert(0, "Sl.No", range(1, len(item_summary) + 1))

                # Format values neatly
                st.dataframe(
                    item_summary.style.format({
                        "Total Dozens": "{:,.2f}",
                        "Total Amount": "₹{:,.2f}"
                    }),
                    use_container_width=True,
                    hide_index=True
                )

        except Exception as e:
            st.error(f"⚠️ Error loading statistics: {e}")
