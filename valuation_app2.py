import streamlit as st
from streamlit import cache_data
import os
import pandas as pd
import re
import streamlit.components.v1 as components
# AgGrid for interactive tables in tab2
from st_aggrid import AgGrid, GridOptionsBuilder, GridUpdateMode, DataReturnMode
import numpy as np
import plotly.graph_objects as go
from sklearn.linear_model import LinearRegression

# --- Cached loader for all transaction files ---
@cache_data
def load_all_transactions(transactions_dir):
    """Load and concatenate all Excel files in the transactions directory, with caching."""
    files = [f for f in os.listdir(transactions_dir) if f.endswith('.xlsx')]
    dfs = []
    for file in files:
        file_path = os.path.join(transactions_dir, file)
        try:
            df = pd.read_excel(file_path)
            df['Source File'] = file
            dfs.append(df)
        except Exception as e:
            st.warning(f"Failed to load {file}: {e}")
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

def _reset_filters():
    # Preserve only sales_recurrence
    saved = st.session_state.get("sales_recurrence", "All")
    # Clear all session state
    st.session_state.clear()
    # Restore sales_recurrence
    st.session_state["sales_recurrence"] = saved

# --- Page Config ---
st.set_page_config(page_title="Valuation App V2", layout="wide")

# --- Load Transaction Data from DATA/Transactions (cached) ---
transactions_dir = os.path.join(os.path.dirname(__file__), 'DATA', 'Transactions')
with st.spinner("Loading transaction files..."):
    all_transactions = load_all_transactions(transactions_dir)
if not all_transactions.empty:
    all_transactions.columns = all_transactions.columns.str.replace('\xa0', '', regex=False).str.strip()
    # Parse Evidence Date once for filtering
    if 'Evidence Date' in all_transactions.columns:
        all_transactions['Evidence Date'] = pd.to_datetime(all_transactions['Evidence Date'], errors='coerce')
    # Count unique source files actually loaded
    file_count = int(all_transactions['Source File'].nunique())
    st.success(f"Loaded {file_count} transaction file(s).")
else:
    st.warning("No transaction data loaded.")
# --- Cached loader for all transaction files ---
@cache_data
def load_all_listings(listings_dir):
    """Load and concatenate all Excel listing files, with caching."""
    files = [f for f in os.listdir(listings_dir) if f.endswith('.xlsx') and not f.startswith('~$')]
    dfs = []
    for file in files:
        path = os.path.join(listings_dir, file)
        try:
            df = pd.read_excel(path)
            df.columns = df.columns.str.replace('\xa0', '', regex=False).str.strip()
            df['Source File'] = file
            dfs.append(df)
        except Exception as e:
            st.warning(f"Failed to load listing {file}: {e}")
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

 # --- Load Layout Types Mapping ---
layout_dir = os.path.join(os.path.dirname(__file__), 'DATA', 'Layout Types')
layout_files = [f for f in os.listdir(layout_dir) if f.endswith('.xlsx')]
layout_dfs = []
for file in layout_files:
    file_path = os.path.join(layout_dir, file)
    try:
        df_l = pd.read_excel(file_path, sheet_name='Types')
        # Clean column names immediately
        df_l.columns = df_l.columns.str.replace('\xa0', '', regex=False).str.strip()
        project_name = os.path.splitext(file)[0]
        if project_name.lower().endswith('_layouts'):
            project_name = project_name[:-len('_layouts')]
        # Keep only Unit No. and Layout Type
        df_l = df_l.loc[:, ['Unit No.', 'Layout Type']]
        df_l['Unit No.'] = df_l['Unit No.'].astype(str).str.strip()
        df_l['Project'] = project_name
        layout_dfs.append(df_l)
    except Exception:
        continue
if layout_dfs:
    layout_map_df = pd.concat(layout_dfs, ignore_index=True).drop_duplicates(subset=['Unit No.'])
    layout_map = dict(zip(layout_map_df['Unit No.'], layout_map_df['Layout Type']))
else:
    layout_map_df = pd.DataFrame(columns=['Unit No.', 'Layout Type', 'Project'])
    layout_map = {}

# Add Layout Type to transactions
if not all_transactions.empty:
    # Clean transaction unit numbers
    all_transactions['Unit No.'] = all_transactions['Unit No.'].astype(str).str.strip()
    # Normalize keys to match mapping (remove subcommunity number before '-V')
    def _normalize_unit_key(u):
        m = re.match(r'^(.+?) \d+(-V.*)$', u)
        return f"{m.group(1)}{m.group(2)}" if m else u
    all_transactions['unit_key'] = all_transactions['Unit No.'].apply(_normalize_unit_key)
    all_transactions['Layout Type'] = all_transactions['unit_key'].map(layout_map).fillna('')
    all_transactions.drop(columns=['unit_key'], inplace=True)
else:
    all_transactions['Layout Type'] = ''

# --- Sidebar ---
with st.sidebar:
    st.title("Valuation Controls")

    if st.button("🔄 Reset Filters", key="reset_filters"):
        _reset_filters()
        st.rerun()

    unit_number = st.session_state.get("unit_number", "")

    # --- Location Filters ---
    st.subheader("Location")
    if not all_transactions.empty:
        dev_options = sorted(all_transactions['All Developments'].dropna().unique())
        com_options = sorted(all_transactions['Community/Building'].dropna().unique())
        subcom_options = sorted(all_transactions['Sub Community / Building'].dropna().unique())
    else:
        dev_options = com_options = subcom_options = []

    development = ""
    community = []
    subcommunity = ""
    property_type = ""
    bedrooms = ""
    floor = ""
    bua = ""
    plot_size = ""
    sales_recurrence = "All"


    if unit_number:
        unit_row = all_transactions[all_transactions['Unit No.'] == unit_number].iloc[0]

        development = unit_row['All Developments']
        community = [unit_row['Community/Building']] if pd.notna(unit_row['Community/Building']) else []
        subcommunity = unit_row['Sub Community / Building']
        property_type = unit_row['Unit Type']
        bedrooms = str(unit_row['Beds'])
        floor = str(unit_row['Floor Level']) if pd.notna(unit_row['Floor Level']) else ""
        bua = unit_row['Unit Size (sq ft)'] if pd.notna(unit_row['Unit Size (sq ft)']) else ""
        plot_size = unit_row['Plot Size (sq ft)'] if pd.notna(unit_row['Plot Size (sq ft)']) else ""
        # Keep Sales Recurrence fixed to 'All' unless changed manually — do not autofill

    development = st.selectbox("Development", options=[""] + dev_options, index=([""] + dev_options).index(development) if development in dev_options else 0, key="development", placeholder="")
    community = st.multiselect("Community", options=com_options, default=community if community else [], key="community")

    # Filter subcom_options by selected community
    if community:
        subcom_options = sorted(
            all_transactions[all_transactions['Community/Building'].isin(community)]['Sub Community / Building'].dropna().unique()
        )

    subcommunity = st.multiselect("Sub community / Building", options=subcom_options, default=[subcommunity] if subcommunity in subcom_options else [], key="subcommunity")

    # --- Unit Number Filter (cascading based on Development, Community, Subcommunity) ---
    if not all_transactions.empty:
        unit_df = all_transactions
        if development:
            unit_df = unit_df[unit_df['All Developments'] == development]
        if community:
            unit_df = unit_df[unit_df['Community/Building'].isin(community)]
        if subcommunity:
            unit_df = unit_df[unit_df['Sub Community / Building'].isin(subcommunity)]
        unit_number_options = sorted(unit_df['Unit No.'].dropna().unique())
    else:
        unit_number_options = []
    # Preserve prior selection if still in options
    current = st.session_state.get("unit_number", "")
    options = [""] + unit_number_options
    default_idx = options.index(current) if current in options else 0
    unit_number = st.selectbox(
        "Unit Number",
        options=options,
        index=default_idx,
        key="unit_number",
        placeholder=""
    )

    # --- Time Period Filter ---
    st.subheader("Time Period")

    time_filter_mode = st.selectbox("Time Filter Mode", ["", "Last N Days", "After Date", "From Date to Date"], index=1, key="time_filter_mode", placeholder="")

    last_n_days = None
    after_date = None
    date_range = (None, None)

    if time_filter_mode == "Last N Days":
        last_n_days = st.number_input("Enter number of days", min_value=1, step=1, value=365, key="last_n_days")

    elif time_filter_mode == "After Date":
        after_date = st.date_input("Select start date", key="after_date")

    elif time_filter_mode == "From Date to Date":
        date_range = st.date_input("Select date range", value=(None, None), key="date_range")

    st.markdown("---")

    # --- Property Filters ---
    st.subheader("Property Info")

    if not all_transactions.empty:
        prop_type_options = sorted(all_transactions['Unit Type'].dropna().unique())
        bedrooms_options = sorted(all_transactions['Beds'].dropna().astype(str).unique())
        sales_rec_options = ['All'] + sorted(all_transactions['Sales Recurrence'].dropna().unique())
    else:
        prop_type_options = bedrooms_options = []
        sales_rec_options = ['All']

    property_type = st.selectbox("Property Type", options=[""] + prop_type_options, index=([""] + prop_type_options).index(property_type) if property_type in prop_type_options else 0, key="property_type", placeholder="")
    bedrooms = st.selectbox("Bedrooms", options=[""] + bedrooms_options, index=([""] + bedrooms_options).index(bedrooms) if bedrooms in bedrooms_options else 0, key="bedrooms", placeholder="")
    if property_type == "Apartment":
        floor = st.text_input("Floor", value=floor, label_visibility="visible", key="floor")
    else:
        st.text_input("Floor", value="", disabled=True, label_visibility="visible", key="floor")
        floor = ""
    bua = st.text_input("BUA (sq ft)", value="", label_visibility="visible", key="bua")
    plot_size = st.text_input("Plot Size (sq ft)", value="", label_visibility="visible", key="plot_size")
    # --- Layout Type Filter (by Project) ---
    # Determine project tag from filename-based Projects
    all_projects = layout_map_df['Project'].unique().tolist()
    project_keys = []
    if development:
        project_keys = [p for p in all_projects if p.lower() in development.lower()]
    elif community:
        project_keys = [p for p in all_projects if any(p.lower() in c.lower() for c in community)]
    elif subcommunity:
        project_keys = [p for p in all_projects if any(p.lower() in s.lower() for s in subcommunity)]
    if project_keys:
        layout_options = sorted(layout_map_df[layout_map_df['Project'].isin(project_keys)]['Layout Type'].dropna().unique())
    else:
        layout_options = sorted(layout_map_df['Layout Type'].dropna().unique())
    # Default mapped layout
    mapped_layout = layout_map.get(unit_number, "") if unit_number else ""
    layout_type = st.multiselect(
        "Layout Type",
        options=layout_options,
        default=[mapped_layout] if mapped_layout in layout_options else [],
        key="layout_type"
    )
    sales_recurrence = st.selectbox("Sales Recurrence", options=sales_rec_options, index=sales_rec_options.index(sales_recurrence) if sales_recurrence in sales_rec_options else 0, key="sales_recurrence", placeholder="")

from datetime import datetime, timedelta

# --- Filter Transactions based on Time Period ---
filtered_transactions = all_transactions.copy()

# Apply Time Period Filter
if not filtered_transactions.empty:
    if 'Evidence Date' in filtered_transactions.columns:
        filtered_transactions['Evidence Date'] = pd.to_datetime(filtered_transactions['Evidence Date'], errors='coerce')

        today = datetime.today()

        if time_filter_mode == "Last N Days" and last_n_days:
            date_threshold = today - timedelta(days=last_n_days)
            filtered_transactions = filtered_transactions[filtered_transactions['Evidence Date'] >= date_threshold]

        elif time_filter_mode == "After Date" and after_date:
            filtered_transactions = filtered_transactions[filtered_transactions['Evidence Date'] >= pd.to_datetime(after_date)]

        elif time_filter_mode == "From Date to Date" and all(date_range):
            start_date, end_date = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
            filtered_transactions = filtered_transactions[
                (filtered_transactions['Evidence Date'] >= start_date) &
                (filtered_transactions['Evidence Date'] <= end_date)
            ]

# --- Apply sidebar filters ---
 # Apply sidebar filters
if development:
    filtered_transactions = filtered_transactions[filtered_transactions['All Developments'] == development]

if community:
    filtered_transactions = filtered_transactions[filtered_transactions['Community/Building'].isin(community)]

if subcommunity:
    filtered_transactions = filtered_transactions[filtered_transactions['Sub Community / Building'].isin(subcommunity)]

    # Unit Number selection is used only to autofill other filters, not as an active filter
    # So it is not applied here

if property_type:
    filtered_transactions = filtered_transactions[filtered_transactions['Unit Type'] == property_type]

if bedrooms:
    filtered_transactions = filtered_transactions[filtered_transactions['Beds'].astype(str) == bedrooms]

if property_type == "Apartment" and floor:
    filtered_transactions = filtered_transactions[filtered_transactions['Floor Level'].astype(str) == floor]

if layout_type:
    filtered_transactions = filtered_transactions[filtered_transactions['Layout Type'].isin(layout_type)]

# if bua > 0:
#     filtered_transactions = filtered_transactions[filtered_transactions['Unit Size (sq ft)'] == bua]

# if plot_size > 0:
#     filtered_transactions = filtered_transactions[filtered_transactions['Plot Size (sq ft)'] == plot_size]

if sales_recurrence != "All":
    filtered_transactions = filtered_transactions[filtered_transactions['Sales Recurrence'] == sales_recurrence]

 # --- Load Live Listings Data from DATA/Listings ---
listings_dir = os.path.join(os.path.dirname(__file__), 'DATA', 'Listings')
with st.spinner("Loading live listings..."):
    all_listings = load_all_listings(listings_dir)
# Pre-convert numeric columns for listings
if not all_listings.empty:
    if 'Beds' in all_listings.columns:
        all_listings['Beds'] = pd.to_numeric(all_listings['Beds'], errors='coerce')
    if 'Floor Level' in all_listings.columns:
        all_listings['Floor Level'] = pd.to_numeric(all_listings['Floor Level'], errors='coerce')
    if 'Price (AED)' in all_listings.columns:
        all_listings['Price (AED)'] = pd.to_numeric(all_listings['Price (AED)'], errors='coerce')
    if 'BUA' in all_listings.columns:
        all_listings['BUA'] = pd.to_numeric(all_listings['BUA'], errors='coerce')
    if 'Days Listed' in all_listings.columns:
        all_listings['Days Listed'] = pd.to_numeric(all_listings['Days Listed'], errors='coerce')

# --- Main Tabs ---
tab1, tab2, tab3, tab4 = st.tabs(["Dashboard", "Live Listings", "Trend & Valuation", "Other"])

with tab1:
    st.title("Real Estate Valuation Dashboard")
    st.write("Main dashboard area will be developed here.")

    st.subheader("Selected Unit Info")

    if unit_number:
        selected_unit_data = all_transactions[all_transactions['Unit No.'] == unit_number].copy()

        if not selected_unit_data.empty:
            # Get unit characteristics from first matching row
            unit_info = selected_unit_data.iloc[0]
            st.markdown(f"**Unit:** {unit_number}")
            st.markdown(f"**Development:** {unit_info['All Developments']}")
            st.markdown(f"**Community:** {unit_info['Community/Building']}")
            st.markdown(f"**Sub Community / Building:** {unit_info['Sub Community / Building']}")
            st.markdown(f"**Property Type:** {unit_info['Unit Type']}")
            st.markdown(f"**Bedrooms:** {unit_info['Beds']}")
            st.markdown(f"**BUA:** {unit_info['Unit Size (sq ft)']}")
            st.markdown(f"**Plot Size:** {unit_info['Plot Size (sq ft)']}")
            st.markdown(f"**Floor Level:** {unit_info['Floor Level']}")

            st.markdown("---")
            st.markdown("**Transaction History for Selected Unit:**")

            # Show transaction history for the unit (all rows, not filtered)
            unit_txn_columns_to_hide = ["Unit No.", "Unit Number", "Select Data Points", "Maid", "Study", "Balcony", "Developer Name", "Source", "Comments", "Source File", "View"]
            unit_txn_visible_columns = [col for col in selected_unit_data.columns if col not in unit_txn_columns_to_hide]
            st.dataframe(selected_unit_data[unit_txn_visible_columns])
        else:
            st.info("No transaction data found for selected unit.")

    st.subheader("Transaction History")
    if isinstance(filtered_transactions, pd.DataFrame) and filtered_transactions.shape[0] > 0:
        columns_to_hide = ["Unit No.", "Unit Number", "Select Data Points", "Maid", "Study", "Balcony", "Developer Name", "Source", "Comments", "Source File", "View"]
        visible_columns = [col for col in filtered_transactions.columns if col not in columns_to_hide]
        # Show count of transactions
        st.markdown(f"**Showing {filtered_transactions.shape[0]} transactions**")
        st.dataframe(filtered_transactions[visible_columns])
    else:
        st.info("No transactions match the current filters.")


with tab2:
    if isinstance(all_listings, pd.DataFrame) and all_listings.shape[0] > 0:
        st.subheader("All Live Listings")
        # Apply sidebar filters to live listings (NO date-based or "Days Listed"/"Listed When"/"Listed Date" filtering here)
        filtered_listings = all_listings.copy()
        if development and 'Development' in filtered_listings.columns:
            filtered_listings = filtered_listings[filtered_listings['Development'] == development]
        if community and 'Community' in filtered_listings.columns:
            filtered_listings = filtered_listings[filtered_listings['Community'].isin(community)]
        if subcommunity and 'Subcommunity' in filtered_listings.columns:
            filtered_listings = filtered_listings[filtered_listings['Subcommunity'].isin(subcommunity)]
        if property_type and 'Type' in filtered_listings.columns:
            filtered_listings = filtered_listings[filtered_listings['Type'] == property_type]
        if bedrooms and 'Beds' in filtered_listings.columns:
            filtered_listings = filtered_listings[filtered_listings['Beds'].astype(str) == bedrooms]
        if property_type == "Apartment" and floor and 'Floor Level' in filtered_listings.columns:
            filtered_listings = filtered_listings[filtered_listings['Floor Level'].astype(str) == floor]
        if layout_type and 'Layout Type' in filtered_listings.columns:
            filtered_listings = filtered_listings[filtered_listings['Layout Type'].isin(layout_type)]
        if sales_recurrence != "All" and 'Sales Recurrence' in filtered_listings.columns:
            filtered_listings = filtered_listings[filtered_listings['Sales Recurrence'] == sales_recurrence]

        # Exclude listings marked as not available
        if 'Availability' in filtered_listings.columns:
            filtered_listings = filtered_listings[filtered_listings['Availability'].astype(str).str.strip().str.lower() != "not available"]

        # Hide certain columns but keep them in the DataFrame (do NOT filter by Days Listed or any date here)
        columns_to_hide = ["Reference Number", "URL", "Source File", "Unit No.", "Unit Number", "Listed When", "Listed when"]
        visible_columns = [c for c in filtered_listings.columns if c not in columns_to_hide] + ["URL"]

        # Show count of live listings
        st.markdown(f"**Showing {filtered_listings.shape[0]} live listings**")

        # Use AgGrid for clickable selection
        gb = GridOptionsBuilder.from_dataframe(filtered_listings[visible_columns])
        gb.configure_selection('single', use_checkbox=False, rowMultiSelectWithClick=False)
        grid_options = gb.build()

        grid_response = AgGrid(
            filtered_listings[visible_columns],
            gridOptions=grid_options,
            enable_enterprise_modules=False,
            update_mode=GridUpdateMode.SELECTION_CHANGED,
            data_return_mode=DataReturnMode.FILTERED_AND_SORTED,
            theme='alpine'
        )

        # Handle selection from AgGrid (can be list of dicts or DataFrame)
        sel = grid_response['selected_rows']
        selected_url = None
        if isinstance(sel, list):
            if len(sel) > 0:
                selected_url = sel[0].get("URL")
        elif isinstance(sel, pd.DataFrame):
            if sel.shape[0] > 0 and "URL" in sel.columns:
                selected_url = sel.iloc[0]["URL"]
        if selected_url:
            # Foldable Listing Preview
            with st.expander("Listing Preview", expanded=True):
                components.html(
                    f'''
                    <iframe
                        src="{selected_url}"
                        width="100%"
                        height="1600px"
                        style="border:none;"
                        scrolling="yes"
                    ></iframe>
                    ''',
                    height=1600
                )
    else:
        st.info("No live listings data found.")

with tab3:
    st.subheader("Trend & Valuation")

    # --- Transaction-Based Valuation Summary ---
    with st.expander("🔍 Valuation Analysis Summary", expanded=True):
        # Prepare transaction comparables
        tx = filtered_transactions.copy()
        if 'Evidence Date' in tx.columns:
            tx['Evidence Date'] = pd.to_datetime(tx['Evidence Date'], dayfirst=True, errors='coerce')
        tx = tx.sort_values('Evidence Date', ascending=False)

        if isinstance(tx, pd.DataFrame) and tx.shape[0] > 0:
            # Use up to the last 5 transactions (but at least 1 if available)
            n_comps = min(5, tx.shape[0])
            comps = tx.head(n_comps)

            # Average price per sqft (raw)
            avg_ppsqft = comps['Price (AED/sq ft)'].mean()
            st.markdown(f"- **Last {n_comps} Transactions Avg (AED/sq ft):** {avg_ppsqft:.2f}")

            # Determine BUA of selected unit
            unit_bua = None
            if unit_number:
                row = all_transactions[all_transactions['Unit No.'] == unit_number].iloc[0]
                unit_bua = row.get('Unit Size (sq ft)', None)
            elif bua:
                try:
                    unit_bua = float(bua)
                except:
                    unit_bua = None

            # Total value based on resale avg
            if unit_bua:
                total_val = avg_ppsqft * unit_bua
                st.markdown(f"- **Total Value (Resale Avg × BUA):** {total_val:,.0f} AED")

            # Market Trend based on newest vs oldest in selection
            if comps.shape[0] >= 2:
                latest = comps.iloc[0]['Price (AED/sq ft)']
                oldest = comps.iloc[-1]['Price (AED/sq ft)']
                pct_change = ((latest - oldest) / oldest) * 100
                trend_color = 'green' if pct_change > 0 else 'red' if pct_change < 0 else 'black'
                trend_label = 'Rising' if pct_change > 0 else 'Falling' if pct_change < 0 else 'Flat'
                st.markdown(f"- **Market Trend:** <span style='color:{trend_color}'>{trend_label} ({pct_change:.2f}%)</span>", unsafe_allow_html=True)
        else:
            st.info("No transaction data available.")

    # --- Price Trend & Forecast Chart ---

    tx_chart = filtered_transactions.copy()
    # Determine BUA for actual price calculation
    unit_bua = None
    if unit_number:
        try:
            unit_bua = float(all_transactions[all_transactions['Unit No.'] == unit_number].iloc[0]['Unit Size (sq ft)'])
        except:
            unit_bua = None
    elif bua:
        try:
            unit_bua = float(bua)
        except:
            unit_bua = None

    if 'Evidence Date' in tx_chart.columns:
        tx_chart['Evidence Date'] = pd.to_datetime(tx_chart['Evidence Date'], errors='coerce')
        # Monthly aggregates including transaction count
        df_monthly = (
            tx_chart.set_index('Evidence Date')
                      .resample('M')['Price (AED/sq ft)']
                      .agg(['mean', 'median', 'count'])
                      .rename(columns={'mean': 'Average', 'median': 'Median', 'count': 'Txns'})
        )
        # 3-month rolling average
        df_monthly['3M Rolling Avg'] = df_monthly['Average'].rolling(3).mean()

        # Convert per-sqft stats to actual price
        if unit_bua:
            df_monthly['Average Price'] = df_monthly['Average'] * unit_bua
            df_monthly['Median Price'] = df_monthly['Median'] * unit_bua
            df_monthly['3M Rolling Price'] = df_monthly['3M Rolling Avg'] * unit_bua
        else:
            st.info("BUA required to calculate actual prices.")
            st.stop()

        if df_monthly.shape[0] >= 3:
            # --- Forecast via Linear Regression on Actual Price ---
            # Reset index and drop months without actual price
            df_reg = df_monthly.reset_index()
            df_reg = df_reg.dropna(subset=['Average Price']).reset_index(drop=True)
            # Recompute month index
            df_reg['MonthIndex'] = np.arange(df_reg.shape[0])
            X = df_reg[['MonthIndex']]
            y = df_reg['Average Price']
            # Fit regression
            model = LinearRegression().fit(X, y)
            # Prepare future indices and dates
            last_idx = df_reg['MonthIndex'].iloc[-1]
            future_indices = np.arange(last_idx + 1, last_idx + 7)
            last_date = df_reg['Evidence Date'].iloc[-1]
            future_months = pd.date_range(last_date + pd.offsets.MonthBegin(), periods=6, freq='M')
            # Predict
            forecast_values = model.predict(future_indices.reshape(-1, 1))
            forecast_df = pd.DataFrame({
                'Forecast Month': future_months,
                'Forecast Price (AED)': [round(v, 0) for v in forecast_values]
            })

            # --- Two-Way Pricing Comparison & Suggested Range (after forecast computed) ---
            if isinstance(tx, pd.DataFrame) and tx.shape[0] > 0 and unit_bua and 'forecast_df' in locals() and not forecast_df.empty:
                # Recent transactions for resale avg
                n_comps = min(5, tx.shape[0])
                comps = tx.head(n_comps)
                avg_ppsqft = comps['Price (AED/sq ft)'].mean()
                st.markdown(f"- **Last {n_comps} Transactions Avg:** {avg_ppsqft:.0f} AED/sqft")
                conservative_ppsqft = avg_ppsqft
                conservative_total = conservative_ppsqft * unit_bua
                # Forecasted total for current month
                high_total = forecast_df['Forecast Price (AED)'].iloc[0]
                high_ppsqft = high_total / unit_bua
                suggested_ppsqft = high_ppsqft
                # Display
                st.markdown("### 💸 Pricing Comparison")
                st.markdown(f"- **Conservative Price (Resale Avg):** {conservative_ppsqft:.0f} AED/sqft → Total: {conservative_total:,.0f} AED")
                st.markdown(f"- **Forecasted Price (Current Month):** {high_ppsqft:.0f} AED/sqft → Total: {high_total:,.0f} AED")

                # --- Live Listings Median Suggested Price ---
                live = all_listings.copy() if 'all_listings' in globals() else pd.DataFrame()
                # Apply sidebar filters to live listings
                if not live.empty:
                    if development and 'Development' in live.columns:
                        live = live[live['Development'] == development]
                    if community and 'Community' in live.columns:
                        live = live[live['Community'].isin(community)]
                    if subcommunity and 'Subcommunity' in live.columns:
                        live = live[live['Subcommunity'].isin(subcommunity)]
                    if property_type and 'Unit Type' in live.columns:
                        live = live[live['Unit Type'] == property_type]
                    if bedrooms and 'Beds' in live.columns:
                        live = live[live['Beds'].astype(str) == bedrooms]
                    if property_type == "Apartment" and floor and 'Floor Level' in live.columns:
                        live = live[live['Floor Level'].astype(str) == floor]
                    if layout_type and 'Layout Type' in live.columns:
                        live = live[live['Layout Type'].isin(layout_type)]
                    if sales_recurrence != "All" and 'Sales Recurrence' in live.columns:
                        live = live[live['Sales Recurrence'] == sales_recurrence]
                    # Exclude listings marked as not available
                    if 'Availability' in live.columns:
                        live = live[live['Availability'].astype(str).str.strip().str.lower() != "not available"]
                # Filter verified and recent via Days Listed
                if 'Verified' in live.columns:
                    live = live[live['Verified'].astype(str).str.strip().str.lower() == "yes"]
                if 'Days Listed' in live.columns:
                    live['Days Listed'] = pd.to_numeric(live['Days Listed'], errors='coerce')
                    live = live[live['Days Listed'].notna() & (live['Days Listed'] <= 30)]
                # Compute price-per-sqft using listing BUA
                live_count = 0
                if not live.empty:
                    # Ensure numeric price and BUA
                    live['Price (AED)'] = pd.to_numeric(live['Price (AED)'], errors='coerce')
                    live['BUA'] = pd.to_numeric(live['BUA'], errors='coerce')
                    # Drop rows missing price or BUA
                    live = live.dropna(subset=['Price (AED)', 'BUA'])
                    # Ignore listings with BUA outside ±20% of the selected unit's BUA
                    if unit_bua:
                        try:
                            selected_bua = float(unit_bua)
                            lower = selected_bua * 0.8
                            upper = selected_bua * 1.2
                            before_count = live.shape[0]
                            live = live[(live['BUA'] >= lower) & (live['BUA'] <= upper)]
                            dropped = before_count - live.shape[0]
                            if dropped > 0:
                                st.markdown(f"_Ignored {dropped} listing(s) with BUA outside ±20% range of selected unit._")
                        except:
                            pass
                    if not live.empty:
                        live['Price_per_sqft'] = live['Price (AED)'] / live['BUA']
                        live = live.dropna(subset=['Price_per_sqft'])
                        live_count = live.shape[0]
                if live_count >= 3:
                    # Remove outliers based on IQR on price_per_sqft
                    # Compute Q1 and Q3
                    q1 = live['Price_per_sqft'].quantile(0.25)
                    q3 = live['Price_per_sqft'].quantile(0.75)
                    iqr = q3 - q1
                    lower_bound = q1 - 1.5 * iqr
                    upper_bound = q3 + 1.5 * iqr
                    before_iqr_count = live.shape[0]
                    live = live[(live['Price_per_sqft'] >= lower_bound) & (live['Price_per_sqft'] <= upper_bound)]
                    after_iqr_count = live.shape[0]
                    dropped = before_iqr_count - after_iqr_count
                    if dropped > 0:
                        st.markdown(f"_Removed {dropped} outlier listing(s) based on price-per-sqft IQR before averaging._")
                    # Recompute live_count after outlier removal
                    live_count = live.shape[0]
                    if live_count >= 1:
                        live_avg_ppsqft = live['Price_per_sqft'].mean()
                        live_avg_total = live_avg_ppsqft * unit_bua
                        st.markdown(f"- **Live Listings Average (IQR-cleaned):** {live_avg_ppsqft:.0f} AED/sqft (based on {live_count} listings) → Total: {live_avg_total:,.0f} AED")
                        st.markdown("_This average excludes listings with extreme price-per-sqft values based on IQR filtering._")
                    else:
                        st.markdown(f"- **Live Listings Average:** No valid listings remain after outlier removal; skipping average suggestion")
                else:
                    st.markdown(f"- **Live Listings Average:** Not enough valid listings (found {live_count}); skipping average suggestion")

                st.markdown("### 💸 Suggested Valuation Range")
                st.markdown(f"- **{conservative_ppsqft:.0f} – {high_ppsqft:.0f} AED/sqft**")
                st.markdown(f"- **Total Value Range:** {conservative_total:,.0f} – {high_total:,.0f} AED")
            else:
                st.info("Insufficient data for pricing comparison or forecast.")

            # Build Plotly figure using actual prices, include Txns in hover
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_monthly.index, y=df_monthly['Average Price'],
                mode='lines+markers', name='Average Price',
                line=dict(color='royalblue'),
                customdata=df_monthly['Txns'],
                hovertemplate='Average Price: %{y:.0f} AED<br>Txns: %{customdata}<extra></extra>'
            ))
            fig.add_trace(go.Scatter(
                x=df_monthly.index, y=df_monthly['Median Price'],
                mode='lines', name='Median Price',
                line=dict(color='green', dash='dot'),
                hovertemplate='Median Price: %{y:.0f} AED<extra></extra>'
            ))
            fig.add_trace(go.Scatter(
                x=df_monthly.index, y=df_monthly['3M Rolling Price'],
                mode='lines', name='3M Rolling Price',
                line=dict(color='orange', dash='dash'),
                hovertemplate='3M Rolling Price: %{y:.0f} AED<extra></extra>'
            ))
            fig.add_trace(go.Scatter(
                x=forecast_df['Forecast Month'], y=forecast_df['Forecast Price (AED)'],
                mode='markers+lines', name='Forecast Price',
                marker=dict(symbol='x', color='firebrick'),
                line=dict(dash='dot')
            ))
            # Shaded forecast window
            fig.add_vrect(
                x0=forecast_df['Forecast Month'].min(),
                x1=forecast_df['Forecast Month'].max(),
                fillcolor='grey', opacity=0.2, line_width=0
            )
            fig.update_layout(
                title='📈 Price Trend & Forecast',
                height=520,
                margin=dict(l=40, r=40, t=40, b=40),
                hovermode='x unified'
            )
            st.plotly_chart(fig, use_container_width=True)

            # Forecast table: only actual price
            forecast_df['Forecast Month'] = forecast_df['Forecast Month'].dt.strftime('%b %Y')
            st.table(forecast_df)
        else:
            st.info("Need at least 3 months of data for trend & forecast.")
    else:
        st.info("No date column for trend analysis.")

with tab4:
    st.write("Placeholder for other functionality.")
