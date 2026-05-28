"""
NZ Annual Enterprise Survey — Interactive Streamlit Dashboard
Deploy: streamlit run streamlit_app.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(
    page_title="NZ Enterprise Survey Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  [data-testid="stMetric"] {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px 20px;
  }
  [data-testid="stMetricLabel"]  { font-size: 0.78rem; color: #64748b; }
  [data-testid="stMetricValue"]  { font-size: 1.45rem; font-weight: 700; }
  [data-testid="stMetricDelta"]  { font-size: 0.82rem; }
  .section-title { font-size: 1.05rem; font-weight: 600; color: #1e293b; margin-bottom: 4px; }
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def fmt_b(v):
    if abs(v) >= 1_000:
        return f"${v/1_000:.1f}B"
    return f"${v:.0f}M"

COLORS = px.colors.qualitative.Plotly

# ── Sidebar — Data Source ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("📂 Data Source")
    uploaded = st.file_uploader("Upload CSV", type=["csv"], help="Upload a Stats NZ Enterprise Survey CSV")

DEFAULT_CSV = "annual-enterprise-survey-2024-financial-year-provisional.csv"

@st.cache_data(show_spinner="Loading data…")
def load_data(file_obj=None, path=None):
    if file_obj is not None:
        df = pd.read_csv(file_obj)
    else:
        df = pd.read_csv(path)
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    df["Year"]  = pd.to_numeric(df["Year"],  errors="coerce")
    df.dropna(subset=["Value", "Year"], inplace=True)
    return df

try:
    raw = load_data(file_obj=uploaded) if uploaded else load_data(path=DEFAULT_CSV)
except FileNotFoundError:
    st.error("No dataset found. Please upload the CSV using the sidebar.")
    st.stop()

# ── Sidebar — Filters ─────────────────────────────────────────────────────────
with st.sidebar:
    st.header("🔧 Filters")

    LATEST   = int(raw["Year"].max())
    EARLIEST = int(raw["Year"].min())

    year_range = st.slider("Year Range", EARLIEST, LATEST, (EARLIEST, LATEST))

    agg_levels = sorted(raw["Industry_aggregation_NZSIOC"].dropna().unique().tolist())
    sel_agg = st.multiselect("Industry Aggregation Level", agg_levels,
                             default=["Level 1", "Level 3"] if "Level 1" in agg_levels else agg_levels[:2])

    all_vars = raw[["Variable_code", "Variable_name"]].drop_duplicates()
    var_map  = dict(zip(all_vars["Variable_name"], all_vars["Variable_code"]))

    st.markdown("---")
    st.caption(f"Dataset: **{len(raw):,}** rows · FY{EARLIEST}–{LATEST}")

# ── Apply filters ─────────────────────────────────────────────────────────────
y0, y1 = year_range
df = raw[(raw["Year"] >= y0) & (raw["Year"] <= y1)].copy()
if sel_agg:
    df = df[df["Industry_aggregation_NZSIOC"].isin(sel_agg)]

mil = raw[raw["Units"] == "Dollars (millions)"]
pct = raw[raw["Units"] == "Percentage"]
lv1 = mil[mil["Industry_aggregation_NZSIOC"] == "Level 1"]
lv3 = mil[mil["Industry_aggregation_NZSIOC"] == "Level 3"]

mil_f = mil[(mil["Year"] >= y0) & (mil["Year"] <= y1)]
lv1_f = lv1[(lv1["Year"] >= y0) & (lv1["Year"] <= y1)]
lv3_f = lv3[(lv3["Year"] >= y0) & (lv3["Year"] <= y1)]

def ts(code, pool):
    return pool[pool["Variable_code"] == code].groupby("Year")["Value"].sum().sort_index()

def kpi(code, year, pool=lv1):
    return pool[(pool["Variable_code"] == code) & (pool["Year"] == year)]["Value"].sum()

# ── Header ────────────────────────────────────────────────────────────────────
st.title("🇳🇿 NZ Annual Enterprise Survey Dashboard")
st.caption(f"Source: Stats NZ · Provisional · FY{EARLIEST}–{LATEST} · Filtered: FY{y0}–{y1}")

# ── KPI Cards ─────────────────────────────────────────────────────────────────
income  = kpi("H01", LATEST)
expend  = kpi("H08", LATEST)
surplus = kpi("H23", LATEST)
wages   = kpi("H12", LATEST)
assets  = kpi("H24", LATEST)

prev_inc = kpi("H01", LATEST - 1)
yoy      = (income - prev_inc) / abs(prev_inc) * 100 if prev_inc else 0
margin   = surplus / income * 100 if income else 0

roe_val = (pct[(pct["Variable_code"] == "H39") &
               (pct["Year"] == LATEST) &
               (pct["Industry_aggregation_NZSIOC"] == "Level 1")]["Value"].mean())
roa_val = (pct[(pct["Variable_code"] == "H40") &
               (pct["Year"] == LATEST) &
               (pct["Industry_aggregation_NZSIOC"] == "Level 1")]["Value"].mean())

c1, c2, c3, c4, c5, c6, c7, c8 = st.columns(8)
c1.metric("Total Income",       fmt_b(income),   f"FY{LATEST}")
c2.metric("Total Expenditure",  fmt_b(expend),   f"FY{LATEST}")
c3.metric("Surplus Before Tax", fmt_b(surplus),  f"FY{LATEST}")
c4.metric("Salaries & Wages",   fmt_b(wages),    f"FY{LATEST}")
c5.metric("Total Assets",       fmt_b(assets),   f"FY{LATEST}")
c6.metric("Income Growth YoY",  f"{yoy:+.1f}%",  f"FY{LATEST-1}→{LATEST}",
          delta=f"{yoy:+.1f}%", delta_color="normal")
c7.metric("Return on Equity",   f"{roe_val:.1f}%" if not np.isnan(roe_val) else "N/A", f"FY{LATEST}")
c8.metric("Operating Margin",   f"{margin:.1f}%", f"FY{LATEST}")

st.markdown("---")

# ── Row 1: Income vs Expenditure | Surplus ────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown('<p class="section-title">Total Income vs Expenditure (NZD Billions)</p>', unsafe_allow_html=True)
    ts_inc = ts("H01", lv1_f)
    ts_exp = ts("H08", lv1_f)
    fig = go.Figure()
    fig.add_scatter(x=ts_inc.index, y=ts_inc/1000, mode="lines+markers",
                    name="Total Income", line=dict(color="#1a6fb5", width=2.5),
                    fill="tozeroy", fillcolor="rgba(26,111,181,0.08)")
    fig.add_scatter(x=ts_exp.index, y=ts_exp/1000, mode="lines+markers",
                    name="Total Expenditure", line=dict(color="#e05c1a", width=2.5, dash="dash"),
                    fill="tozeroy", fillcolor="rgba(224,92,26,0.06)")
    fig.update_layout(yaxis_tickprefix="$", yaxis_ticksuffix="B",
                      legend=dict(orientation="h", y=1.1), margin=dict(t=10, b=0),
                      plot_bgcolor="#f8fafc", paper_bgcolor="#f8fafc", height=340)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown('<p class="section-title">Surplus Before Income Tax (NZD Billions)</p>', unsafe_allow_html=True)
    ts_s = ts("H23", lv1_f)
    colors_bar = ["#2ca02c" if v >= 0 else "#e05c1a" for v in ts_s]
    fig = go.Figure(go.Bar(x=ts_s.index, y=ts_s/1000, marker_color=colors_bar,
                           hovertemplate="%{x}: $%{y:.2f}B<extra></extra>"))
    fig.add_hline(y=0, line_color="#555", line_width=0.8)
    fig.update_layout(yaxis_tickprefix="$", yaxis_ticksuffix="B",
                      margin=dict(t=10, b=0),
                      plot_bgcolor="#f8fafc", paper_bgcolor="#f8fafc", height=340)
    st.plotly_chart(fig, use_container_width=True)

# ── Row 2: Top 10 Industries | Wages trend ───────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown(f'<p class="section-title">Top 10 Industries — Total Income FY{LATEST}</p>', unsafe_allow_html=True)
    top_ind = (lv3[(lv3["Variable_code"] == "H01") & (lv3["Year"] == LATEST)]
               .groupby("Industry_name_NZSIOC")["Value"].sum()
               .sort_values(ascending=False).head(10))
    names = [n[:40] + "…" if len(n) > 40 else n for n in top_ind.index]
    fig = go.Figure(go.Bar(
        x=top_ind.values / 1000, y=names, orientation="h",
        marker=dict(color=top_ind.values, colorscale="Blues"),
        hovertemplate="%{y}: $%{x:.2f}B<extra></extra>",
        text=[fmt_b(v) for v in top_ind.values], textposition="outside"
    ))
    fig.update_layout(xaxis_tickprefix="$", xaxis_ticksuffix="B",
                      yaxis=dict(autorange="reversed"),
                      margin=dict(t=10, b=0),
                      plot_bgcolor="#f8fafc", paper_bgcolor="#f8fafc", height=360)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown('<p class="section-title">Salaries & Wages Paid (NZD Billions)</p>', unsafe_allow_html=True)
    ts_w = ts("H12", lv1_f)
    fig = go.Figure(go.Scatter(x=ts_w.index, y=ts_w/1000, mode="lines+markers",
                               line=dict(color="#9467bd", width=2.5),
                               fill="tozeroy", fillcolor="rgba(148,103,189,0.1)",
                               hovertemplate="FY%{x}: $%{y:.2f}B<extra></extra>"))
    fig.update_layout(yaxis_tickprefix="$", yaxis_ticksuffix="B",
                      margin=dict(t=10, b=0),
                      plot_bgcolor="#f8fafc", paper_bgcolor="#f8fafc", height=360)
    st.plotly_chart(fig, use_container_width=True)

# ── Row 3: Industry Pie | Asset Composition ───────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown(f'<p class="section-title">Industry Share of Total Income — FY{LATEST}</p>', unsafe_allow_html=True)
    pie_d = top_ind.copy()
    if len(pie_d) > 8:
        oth = pie_d.iloc[8:].sum()
        pie_d = pie_d.iloc[:8]
        pie_d["Other"] = oth
    fig = go.Figure(go.Pie(
        labels=[n[:24] + "…" if len(n) > 24 else n for n in pie_d.index],
        values=pie_d.values,
        hole=0.35,
        hovertemplate="%{label}: %{percent} (%{value:.0f}M)<extra></extra>"
    ))
    fig.update_layout(margin=dict(t=10, b=0), height=360,
                      paper_bgcolor="#f8fafc",
                      legend=dict(font=dict(size=9)))
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown('<p class="section-title">Asset Composition Over Time (NZD Billions)</p>', unsafe_allow_html=True)
    ts_ca = ts("H25", lv1_f)
    ts_fa = ts("H26", lv1_f)
    ts_ta = ts("H24", lv1_f)
    common = ts_ca.index
    ts_oa = (ts_ta.reindex(common, fill_value=0)
             - ts_ca.reindex(common, fill_value=0)
             - ts_fa.reindex(common, fill_value=0)).clip(lower=0)
    fig = go.Figure()
    for label, series, color in [
        ("Current Assets",    ts_ca, "#17becf"),
        ("Fixed Tangible",    ts_fa, "#1a6fb5"),
        ("Other Assets",      ts_oa, "#8c564b"),
    ]:
        fig.add_scatter(x=series.reindex(common, fill_value=0).index,
                        y=series.reindex(common, fill_value=0).values / 1000,
                        name=label, stackgroup="one",
                        line=dict(color=color),
                        hovertemplate=f"{label}: $%{{y:.2f}}B<extra></extra>")
    fig.update_layout(yaxis_tickprefix="$", yaxis_ticksuffix="B",
                      legend=dict(orientation="h", y=1.1),
                      margin=dict(t=10, b=0),
                      plot_bgcolor="#f8fafc", paper_bgcolor="#f8fafc", height=360)
    st.plotly_chart(fig, use_container_width=True)

# ── Row 4: ROE & ROA | Operating Margin ──────────────────────────────────────
col1, col2 = st.columns(2)

with col1:
    st.markdown('<p class="section-title">Return on Equity & Return on Assets (%)</p>', unsafe_allow_html=True)
    pct_f = pct[(pct["Year"] >= y0) & (pct["Year"] <= y1)]
    ts_roe = (pct_f[(pct_f["Variable_code"] == "H39") &
                    (pct_f["Industry_aggregation_NZSIOC"] == "Level 1")]
              .groupby("Year")["Value"].mean().sort_index())
    ts_roa = (pct_f[(pct_f["Variable_code"] == "H40") &
                    (pct_f["Industry_aggregation_NZSIOC"] == "Level 1")]
              .groupby("Year")["Value"].mean().sort_index())
    fig = go.Figure()
    fig.add_scatter(x=ts_roe.index, y=ts_roe, mode="lines+markers",
                    name="Return on Equity (%)", line=dict(color="#e377c2", width=2.5))
    fig.add_scatter(x=ts_roa.index, y=ts_roa, mode="lines+markers",
                    name="Return on Assets (%)", line=dict(color="#17becf", width=2.5, dash="dash"))
    fig.add_hline(y=0, line_color="#aaa", line_dash="dot", line_width=0.8)
    fig.update_layout(yaxis_ticksuffix="%",
                      legend=dict(orientation="h", y=1.1),
                      margin=dict(t=10, b=0),
                      plot_bgcolor="#f8fafc", paper_bgcolor="#f8fafc", height=340)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.markdown('<p class="section-title">Operating Margin % (Surplus / Total Income)</p>', unsafe_allow_html=True)
    ts_inc2 = ts("H01", lv1_f)
    ts_sur2 = ts("H23", lv1_f)
    margin_ts = (ts_sur2 / ts_inc2 * 100).dropna()
    bar_cols2 = ["#2ca02c" if v >= 0 else "#e05c1a" for v in margin_ts]
    fig = go.Figure(go.Bar(x=margin_ts.index, y=margin_ts.values,
                           marker_color=bar_cols2,
                           hovertemplate="FY%{x}: %{y:.1f}%<extra></extra>"))
    fig.add_hline(y=0, line_color="#555", line_width=0.8)
    fig.update_layout(yaxis_ticksuffix="%",
                      margin=dict(t=10, b=0),
                      plot_bgcolor="#f8fafc", paper_bgcolor="#f8fafc", height=340)
    st.plotly_chart(fig, use_container_width=True)

# ── Row 5: Industry Heatmap ───────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<p class="section-title">Industry Total Income Heatmap by Year (NZD Billions — Top 12)</p>',
    unsafe_allow_html=True,
)

pivot = (lv3_f[lv3_f["Variable_code"] == "H01"]
         .groupby(["Industry_name_NZSIOC", "Year"])["Value"]
         .sum().unstack("Year"))

if not pivot.empty:
    last_col = pivot.columns.max()
    top12_idx = (pivot[last_col].sort_values(ascending=False).head(12).index
                 if last_col in pivot.columns else
                 pivot.sum(axis=1).sort_values(ascending=False).head(12).index)
    ph = pivot.loc[top12_idx] / 1000
    ph.index = [n[:35] + "…" if len(n) > 35 else n for n in ph.index]

    fig = go.Figure(go.Heatmap(
        z=ph.values,
        x=ph.columns.astype(str).tolist(),
        y=ph.index.tolist(),
        colorscale=[[0, "#eef5ff"], [0.5, "#1a6fb5"], [1, "#082a50"]],
        hovertemplate="Industry: %{y}<br>Year: %{x}<br>Income: $%{z:.1f}B<extra></extra>",
        text=[[f"{v:.0f}" if not np.isnan(v) else "" for v in row] for row in ph.values],
        texttemplate="%{text}",
        textfont=dict(size=9),
        colorbar=dict(title="NZD Billions"),
    ))
    fig.update_layout(margin=dict(t=10, b=0),
                      paper_bgcolor="#f8fafc", height=420,
                      xaxis=dict(tickangle=0))
    st.plotly_chart(fig, use_container_width=True)

# ── Raw Data Explorer ─────────────────────────────────────────────────────────
st.markdown("---")
with st.expander("🔍 Raw Data Explorer"):
    col_f1, col_f2, col_f3 = st.columns(3)
    with col_f1:
        var_names = raw["Variable_name"].dropna().unique().tolist()
        sel_var = st.selectbox("Variable", ["(all)"] + sorted(var_names))
    with col_f2:
        ind_names = raw["Industry_name_NZSIOC"].dropna().unique().tolist()
        sel_ind = st.selectbox("Industry", ["(all)"] + sorted(ind_names))
    with col_f3:
        units_list = raw["Units"].dropna().unique().tolist()
        sel_unit = st.selectbox("Units", ["(all)"] + sorted(units_list))

    view = raw.copy()
    if sel_var != "(all)":
        view = view[view["Variable_name"] == sel_var]
    if sel_ind != "(all)":
        view = view[view["Industry_name_NZSIOC"] == sel_ind]
    if sel_unit != "(all)":
        view = view[view["Units"] == sel_unit]

    st.dataframe(view.sort_values("Year", ascending=False), use_container_width=True, height=320)
    st.download_button("⬇ Download filtered CSV", view.to_csv(index=False).encode(),
                       "filtered_data.csv", "text/csv")

st.caption("Built with Streamlit · Data: Stats NZ Annual Enterprise Survey 2024 (Provisional)")
