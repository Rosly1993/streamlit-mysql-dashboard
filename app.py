
import streamlit as st
import pandas as pd
import plotly.express as px
import matplotlib.pyplot as plt
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
import io
import os
import time
from db_connection import get_connection
from datetime import datetime

# -----------------------------
# PDF CREATION FUNCTION
# -----------------------------
def create_pdf(df, report_title="Sales Report"):
    pdf_file = "sales_report.pdf"
    doc = SimpleDocTemplate(pdf_file, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()

    elements.append(Paragraph(report_title, styles['Title']))
    elements.append(Paragraph("Generated using Streamlit & Python", styles['Normal']))
    elements.append(Spacer(1,12))

    chart_file = "chart.png"
    if 'amount' in df.columns or 'total_amount' in df.columns:
        plt.figure(figsize=(6,3))
        if 'product_name' in df.columns:
            plt.bar(df['product_name'], df['amount'] if 'amount' in df.columns else df['total_amount'], color='skyblue')
            plt.ylabel("Amount")
            plt.title("Sales by Product")
        elif 'category' in df.columns:
            plt.pie(df['total_amount'], labels=df['category'], autopct='%1.1f%%')
            plt.title("Sales by Category")
        plt.tight_layout()
        plt.savefig(chart_file)
        plt.close()
        elements.append(Image(chart_file, width=400, height=200))
        elements.append(Spacer(1,12))

    data = [df.columns.tolist()] + df.values.tolist()
    table = Table(data, repeatRows=1)
    style = TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#4F81BD')),
        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
        ('ALIGN',(0,0),(-1,-1),'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
    ])
    table.setStyle(style)

    top_amounts = df['total_amount'].nlargest(3).tolist() if 'total_amount' in df.columns else df['amount'].nlargest(3).tolist()
    for i, row in enumerate(df.values.tolist(), start=1):
        value = row[df.columns.get_loc('total_amount') if 'total_amount' in df.columns else df.columns.get_loc('amount')]
        bg_color = colors.HexColor('#FFD700') if value in top_amounts else (colors.HexColor('#DCE6F1') if i%2==0 else colors.whitesmoke)
        table.setStyle(TableStyle([('BACKGROUND', (0,i), (-1,i), bg_color)]))

    elements.append(table)
    doc.build(elements)

    if os.path.exists(chart_file):
        os.remove(chart_file)

    return pdf_file

# -----------------------------
# EXCEL EXPORT FUNCTION
# -----------------------------
def create_excel_with_chart(df):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name="Report")
        workbook = writer.book
        worksheet = writer.sheets["Report"]

        top_amounts = df['total_amount'].nlargest(3).tolist() if 'total_amount' in df.columns else df['amount'].nlargest(3).tolist()
        format_top = workbook.add_format({'bg_color': '#FFD700', 'font_color': 'black'})
        for i, val in enumerate(df.iloc[:, -1]):
            if val in top_amounts:
                worksheet.set_row(i+1, None, format_top)

        chart = workbook.add_chart({'type': 'column'})
        col_amount = df.columns.get_loc('total_amount') + 1 if 'total_amount' in df.columns else df.columns.get_loc('amount') + 1
        col_name = df.columns.get_loc('category') + 1 if 'category' in df.columns else df.columns.get_loc('product_name') + 1
        chart.add_series({
            'name': 'Sales Amount',
            'categories': ['Report', 1, col_name-1, len(df), col_name-1],
            'values': ['Report', 1, col_amount-1, len(df), col_amount-1],
            'fill': {'color': '#4F81BD'}
        })
        chart.set_title({'name': 'Sales Chart'})
        chart.set_x_axis({'name': 'Category/Product'})
        chart.set_y_axis({'name': 'Amount'})
        worksheet.insert_chart('H2', chart)

    return output.getvalue()

# -----------------------------
# FETCH DATA FUNCTION
# -----------------------------
def fetch_data(query):
    conn = get_connection()
    df = pd.read_sql(query, conn)
    conn.close()
    return df

# -----------------------------
# STREAMLIT CONFIG
# -----------------------------
st.set_page_config(page_title="Enhanced Sales Dashboard", layout="wide", initial_sidebar_state="expanded")

# -----------------------------
# SIDEBAR NAVIGATION & FILTERS
# -----------------------------
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to", ["Dashboard", "Dynamic KPIs", "Export Excel", "Export PDF"])

st.sidebar.subheader("Filters")
date_range_df = fetch_data("SELECT MIN(sale_date) as min_date, MAX(sale_date) as max_date FROM sales")
min_date = date_range_df['min_date'][0]
max_date = date_range_df['max_date'][0]
start_date = st.sidebar.date_input("Start Date", min_value=min_date, max_value=max_date, value=min_date)
end_date = st.sidebar.date_input("End Date", min_value=min_date, max_value=max_date, value=max_date)

product_options = fetch_data("SELECT DISTINCT product_name FROM sales")['product_name'].tolist()
selected_products = st.sidebar.multiselect("Products", product_options, default=product_options)

category_options = fetch_data("SELECT DISTINCT category FROM sales")['category'].tolist()
selected_categories = st.sidebar.multiselect("Categories", category_options, default=category_options)

query_option = st.sidebar.selectbox("Report Type", ["All Sales Data", "Sales by Product", "Daily Sales Summary", "Sales by Category"])

# -----------------------------
# AUTO-REFRESH SETTINGS (from previous project)
# -----------------------------
refresh_sec = st.sidebar.slider("⏱️ Refresh Interval (seconds)", 5, 60, 10)
pause_refresh = st.sidebar.checkbox("⏸️ Pause Auto-Refresh", value=False)
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = time.time()

# -----------------------------
# SQL QUERY
# -----------------------------
base_condition = f"sale_date BETWEEN '{start_date}' AND '{end_date}'"
if selected_products:
    base_condition += " AND product_name IN (" + ",".join(f"'{p}'" for p in selected_products) + ")"
if selected_categories:
    base_condition += " AND category IN (" + ",".join(f"'{c}'" for c in selected_categories) + ")"

if query_option == "All Sales Data":
    query = f"SELECT *, quantity*unit_price AS amount FROM sales WHERE {base_condition}"
elif query_option == "Sales by Product":
    query = f"""
        SELECT product_name, SUM(quantity) AS total_qty, SUM(quantity*unit_price) AS total_amount
        FROM sales
        WHERE {base_condition}
        GROUP BY product_name
    """
elif query_option == "Daily Sales Summary":
    query = f"""
        SELECT sale_date, SUM(quantity) AS total_qty, SUM(quantity*unit_price) AS total_amount
        FROM sales
        WHERE {base_condition}
        GROUP BY sale_date
        ORDER BY sale_date
    """
elif query_option == "Sales by Category":
    query = f"""
        SELECT category, SUM(quantity) AS total_qty, SUM(quantity*unit_price) AS total_amount
        FROM sales
        WHERE {base_condition}
        GROUP BY category
    """

df = fetch_data(query)

# -----------------------------
# RENDER DASHBOARD FUNCTION
# -----------------------------
def render_dashboard():
    st.title("📊 Sales Dashboard")

    total_sales = df['amount'].sum() if 'amount' in df.columns else df['total_amount'].sum()
    total_qty = df['quantity'].sum() if 'quantity' in df.columns else df['total_qty'].sum()
    num_products = df['product_name'].nunique() if 'product_name' in df.columns else "N/A"
    num_categories = df['category'].nunique() if 'category' in df.columns else "N/A"

    kpi_col1, kpi_col2, kpi_col3, kpi_col4 = st.columns(4)
    kpi_col1.metric("Total Sales", f"${total_sales:,.2f}")
    kpi_col2.metric("Total Quantity", f"{total_qty}")
    kpi_col3.metric("Number of Products", f"{num_products}")
    kpi_col4.metric("Number of Categories", f"{num_categories}")

    st.subheader("📈 Interactive Charts")
    if query_option == "Sales by Product":
        fig = px.bar(df, x='product_name', y='total_amount', text='total_amount', color='total_amount',
                     color_continuous_scale='Blues', title="Sales Amount by Product")
    elif query_option == "Daily Sales Summary":
        fig = px.line(df, x='sale_date', y='total_amount', markers=True, title="Daily Sales Amount")
    elif query_option == "Sales by Category":
        fig = px.pie(df, names='category', values='total_amount', title="Sales Amount by Category")
    else:
        fig = px.bar(df, x='product_name', y='amount', color='category', title="Sales Amount by Product")
    st.plotly_chart(fig, use_container_width=True)

    st.subheader("📋 Sales Data Table")
    highlight_col = 'amount' if 'amount' in df.columns else 'total_amount'
    st.dataframe(df.style.highlight_max(subset=[highlight_col], color='gold'))

# -----------------------------
# AUTO-REFRESH LOGIC
# -----------------------------
# -----------------------------
# CONDITIONAL RENDERING BASED ON PAGE
# -----------------------------

if page == "Dashboard":
    render_dashboard()

    # AUTO-REFRESH
    if not pause_refresh:
        time.sleep(refresh_sec)
        st.rerun()
    else:
        st.info("⏸️ Auto-refresh paused. Uncheck the box to resume live updates.")

elif page == "Dynamic KPIs":
    st.title("📊 Dynamic KPIs Dashboard")
    monthly_df = fetch_data(f"""
        SELECT DATE_FORMAT(sale_date, '%Y-%m') AS month, SUM(quantity*unit_price) AS total_amount
        FROM sales
        WHERE {base_condition}
        GROUP BY month
        ORDER BY month
    """)
    fig = px.line(monthly_df, x='month', y='total_amount', markers=True, title="Monthly Sales Trend")
    st.plotly_chart(fig, use_container_width=True)

elif page == "Export Excel":
    st.title("💾 Export Excel with Chart")
    if st.button("Download Excel Report"):
        excel_data = create_excel_with_chart(df)
        st.download_button(
            label="Download Excel",
            data=excel_data,
            file_name="sales_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

elif page == "Export PDF":
    st.title("💾 Export PDF with Chart")
    if st.button("Download PDF Report"):
        pdf_file = create_pdf(df, report_title=query_option)
        with open(pdf_file, "rb") as f:
            st.download_button(
                label="Download PDF",
                data=f,
                file_name="sales_report.pdf",
                mime="application/pdf"
            )
