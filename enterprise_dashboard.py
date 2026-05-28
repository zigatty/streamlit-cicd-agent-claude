"""
New Zealand Annual Enterprise Survey 2024 (Provisional) — Dashboard
Dataset : annual-enterprise-survey-2024-financial-year-provisional.csv
Source  : Stats NZ  https://www.stats.govt.nz/information-releases/
          annual-enterprise-survey-2024-financial-year-provisional/

Columns (10):
  Year | Industry_aggregation_NZSIOC | Industry_code_NZSIOC
  Industry_name_NZSIOC | Units | Variable_code | Variable_name
  Variable_category | Value | Industry_code_ANZSIC06

Variable codes used:
  H01  Total income              H08  Total expenditure
  H12  Salaries and wages paid   H23  Surplus before income tax
  H24  Total assets              H25  Current assets
  H26  Fixed tangible assets     H31  Shareholders equity
  H39  Return on equity (%)      H40  Return on total assets (%)
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import matplotlib.gridspec as gridspec
from matplotlib.patches import FancyBboxPatch
from matplotlib.colors import LinearSegmentedColormap
import warnings
warnings.filterwarnings("ignore")

# ── Palette ───────────────────────────────────────────────────────────────────
C1, C2, C3, C4 = "#1a6fb5", "#e05c1a", "#2ca02c", "#9467bd"
C5, C6         = "#8c564b", "#17becf"
BG             = "#f4f7fb"

# ── 1. Load ───────────────────────────────────────────────────────────────────
CSV = "annual-enterprise-survey-2024-financial-year-provisional.csv"
raw = pd.read_csv(CSV)
raw["Value"] = pd.to_numeric(raw["Value"], errors="coerce")
raw["Year"]  = pd.to_numeric(raw["Year"],  errors="coerce")
raw.dropna(subset=["Value", "Year"], inplace=True)

# Convenience filters
mil  = raw[raw["Units"] == "Dollars (millions)"]
pct  = raw[raw["Units"] == "Percentage"]
lv1  = mil[mil["Industry_aggregation_NZSIOC"] == "Level 1"]   # all-industry aggregates
lv3  = mil[mil["Industry_aggregation_NZSIOC"] == "Level 3"]   # sector breakdown

LATEST = int(raw["Year"].max())

# ── 2. Helper functions ───────────────────────────────────────────────────────
def fmt_b(v):           # NZD millions → formatted string
    if abs(v) >= 1_000: return f"${v/1_000:.1f}B"
    return f"${v:.0f}M"

def ts(code, pool=lv1):
    return (pool[pool["Variable_code"] == code]
            .groupby("Year")["Value"].sum().sort_index())

def ind_latest(code, year=LATEST):
    sub = lv3[(lv3["Variable_code"] == code) & (lv3["Year"] == year)]
    return (sub.groupby("Industry_name_NZSIOC")["Value"].sum()
               .sort_values(ascending=False).head(10))

def kpi(code, year=LATEST, pool=lv1):
    return pool[(pool["Variable_code"] == code) & (pool["Year"] == year)]["Value"].sum()

def add_card(ax, title, val, sub="", color=C1):
    ax.set_xlim(0,1); ax.set_ylim(0,1); ax.axis("off")
    ax.add_patch(FancyBboxPatch((.04,.04),.92,.92,
                                boxstyle="round,pad=0.02",
                                facecolor="white", edgecolor=color, linewidth=2))
    ax.text(.5,.76, title, ha="center", va="center", fontsize=8.5,
            color="#555", fontweight="bold", transform=ax.transAxes)
    ax.text(.5,.46, val,   ha="center", va="center", fontsize=15,
            color=color,   fontweight="bold", transform=ax.transAxes)
    ax.text(.5,.20, sub,   ha="center", va="center", fontsize=7.5,
            color="#888",  transform=ax.transAxes)

# ── 3. KPIs ───────────────────────────────────────────────────────────────────
income   = kpi("H01")
expend   = kpi("H08")
surplus  = kpi("H23")
wages    = kpi("H12")
assets   = kpi("H24")
cur_ast  = kpi("H25")
fix_ast  = kpi("H26")
equity   = kpi("H31")

prev_inc = kpi("H01", LATEST-1)
yoy      = (income - prev_inc) / abs(prev_inc) * 100 if prev_inc else None

margin   = surplus / income * 100 if income else 0
n_ind    = lv3[lv3["Year"] == LATEST]["Industry_name_NZSIOC"].nunique()

roe_val  = (pct[(pct["Variable_code"]=="H39") &
                (pct["Year"]==LATEST) &
                (pct["Industry_aggregation_NZSIOC"]=="Level 1")]["Value"].mean())
roa_val  = (pct[(pct["Variable_code"]=="H40") &
                (pct["Year"]==LATEST) &
                (pct["Industry_aggregation_NZSIOC"]=="Level 1")]["Value"].mean())

# ── 4. Figure layout ──────────────────────────────────────────────────────────
fig = plt.figure(figsize=(24, 28), facecolor=BG)
fig.suptitle(
    f"New Zealand Annual Enterprise Survey  ·  FY{LATEST} (Provisional)",
    fontsize=22, fontweight="bold", color="#12263a", y=0.985
)
fig.text(.5, .972,
         "Source: Stats NZ  |  Values in NZD millions unless noted  |  "
         f"Dataset rows: {len(raw):,}  |  Coverage: 2013–{LATEST}",
         ha="center", fontsize=9, color="#666")

gs = gridspec.GridSpec(7, 4, figure=fig,
                       hspace=0.60, wspace=0.40,
                       top=0.965, bottom=0.025, left=0.06, right=0.97)

# ── Row 0 — KPI cards (4 cols) ────────────────────────────────────────────────
cards_r0 = [
    ("Total Income",      fmt_b(income),  f"FY{LATEST}", C1),
    ("Total Expenditure", fmt_b(expend),  f"FY{LATEST}", C2),
    ("Surplus Before Tax",fmt_b(surplus), f"FY{LATEST}", C3),
    ("Salaries & Wages",  fmt_b(wages),   f"FY{LATEST}", C4),
]
for i,(t,v,s,c) in enumerate(cards_r0):
    add_card(fig.add_subplot(gs[0, i]), t, v, s, c)

# ── Row 1 — KPI cards (4 cols) ────────────────────────────────────────────────
yoy_str  = f"{yoy:+.1f}%" if yoy is not None else "N/A"
yoy_col  = C3 if (yoy or 0) >= 0 else C2
cards_r1 = [
    ("Total Assets",      fmt_b(assets),      f"FY{LATEST}",              C5),
    ("Income Growth YoY", yoy_str,            f"FY{LATEST-1}→{LATEST}",  yoy_col),
    ("Return on Equity",  f"{roe_val:.1f}%"   if not np.isnan(roe_val) else "N/A",
                                              f"FY{LATEST}", "#e377c2"),
    ("Return on Assets",  f"{roa_val:.1f}%"   if not np.isnan(roa_val) else "N/A",
                                              f"FY{LATEST}", C6),
]
for i,(t,v,s,c) in enumerate(cards_r1):
    add_card(fig.add_subplot(gs[1, i]), t, v, s, c)

# ── Row 2L — Income vs Expenditure trend ─────────────────────────────────────
ax = fig.add_subplot(gs[2, :2])
ts_inc = ts("H01"); ts_exp = ts("H08")
ax.fill_between(ts_inc.index, ts_inc/1000, alpha=.18, color=C1)
ax.plot(ts_inc.index, ts_inc/1000, "o-", color=C1, lw=2.2, ms=5, label="Total Income")
ax.fill_between(ts_exp.index, ts_exp/1000, alpha=.13, color=C2)
ax.plot(ts_exp.index, ts_exp/1000, "s--",color=C2, lw=2.2, ms=5, label="Total Expenditure")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"${x:.0f}B"))
ax.set_title("Total Income vs Expenditure (NZD Billions)", fontweight="bold", fontsize=11)
ax.set_xlabel("Year"); ax.set_ylabel("NZD Billions")
ax.legend(fontsize=9); ax.set_facecolor(BG)
ax.grid(axis="y", ls="--", alpha=.4)
ax.spines[["top","right"]].set_visible(False)

# ── Row 2R — Surplus before tax trend (bar) ──────────────────────────────────
ax = fig.add_subplot(gs[2, 2:])
ts_s = ts("H23")
cols = [C3 if v >= 0 else C2 for v in ts_s]
ax.bar(ts_s.index, ts_s/1000, color=cols, alpha=.85, edgecolor="white", width=0.6)
ax.axhline(0, color="#555", lw=.8)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"${x:.0f}B"))
ax.set_title("Surplus Before Income Tax (NZD Billions)", fontweight="bold", fontsize=11)
ax.set_xlabel("Year"); ax.set_ylabel("NZD Billions")
ax.set_facecolor(BG)
ax.grid(axis="y", ls="--", alpha=.4)
ax.spines[["top","right"]].set_visible(False)

# ── Row 3L — Top 10 industries by income (horizontal bar) ────────────────────
ax = fig.add_subplot(gs[3, :2])
top = ind_latest("H01")
names = [n[:38]+"…" if len(n)>38 else n for n in top.index]
c_bar = plt.cm.Blues(np.linspace(.4,.9, len(top)))[::-1]
bars  = ax.barh(names, top/1000, color=c_bar, edgecolor="white")
for b, v in zip(bars, top.values):
    ax.text(b.get_width()+.3, b.get_y()+b.get_height()/2,
            fmt_b(v), va="center", fontsize=7.5, color="#333")
ax.invert_yaxis()
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"${x:.0f}B"))
ax.set_title(f"Top 10 Industries — Total Income FY{LATEST}", fontweight="bold", fontsize=11)
ax.set_xlabel("NZD Billions")
ax.set_facecolor(BG)
ax.spines[["top","right"]].set_visible(False)

# ── Row 3R — Salaries & wages trend ──────────────────────────────────────────
ax = fig.add_subplot(gs[3, 2:])
ts_w = ts("H12")
ax.fill_between(ts_w.index, ts_w/1000, alpha=.18, color=C4)
ax.plot(ts_w.index, ts_w/1000, "D-", color=C4, lw=2.2, ms=5)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"${x:.0f}B"))
ax.set_title("Salaries & Wages Paid (NZD Billions)", fontweight="bold", fontsize=11)
ax.set_xlabel("Year"); ax.set_ylabel("NZD Billions")
ax.set_facecolor(BG)
ax.grid(axis="y", ls="--", alpha=.4)
ax.spines[["top","right"]].set_visible(False)

# ── Row 4L — Industry income pie ─────────────────────────────────────────────
ax = fig.add_subplot(gs[4, :2])
pie_d = top.copy()
if len(pie_d) > 8:
    oth = pie_d.iloc[8:].sum()
    pie_d = pie_d.iloc[:8]
    pie_d["Other industries"] = oth
plabels = [n[:20]+"…" if len(n)>20 else n for n in pie_d.index]
wcolors = plt.cm.tab20.colors[:len(pie_d)]
wedges, _, autos = ax.pie(pie_d.values, labels=None, autopct="%1.1f%%",
                          colors=wcolors, startangle=140, pctdistance=.78,
                          wedgeprops={"edgecolor":"white","linewidth":1.5})
for a in autos: a.set_fontsize(7)
ax.legend(wedges, plabels, loc="center left", bbox_to_anchor=(1.0,.5),
          fontsize=7, frameon=False)
ax.set_title(f"Industry Share of Total Income — FY{LATEST}", fontweight="bold", fontsize=11)

# ── Row 4R — Asset composition stacked area ──────────────────────────────────
ax = fig.add_subplot(gs[4, 2:])
ts_ca = ts("H25")   # Current assets
ts_fa = ts("H26")   # Fixed tangible assets
ts_oa = ts("H29") if ts("H29", lv1).sum() > 0 else ts("H24") - ts_ca - ts_fa  # Other assets

common_idx = ts_ca.index
ts_fa_a = ts_fa.reindex(common_idx, fill_value=0)
ts_oa_a = (ts("H24").reindex(common_idx, fill_value=0)
           - ts_ca.reindex(common_idx, fill_value=0)
           - ts_fa_a)

ax.stackplot(common_idx,
             ts_ca.reindex(common_idx, fill_value=0)/1000,
             ts_fa_a/1000,
             ts_oa_a.clip(lower=0)/1000,
             labels=["Current Assets","Fixed Tangible","Other Assets"],
             colors=[C6, C1, C5], alpha=.82)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"${x:.0f}B"))
ax.set_title("Asset Composition Over Time (NZD Billions)", fontweight="bold", fontsize=11)
ax.set_xlabel("Year"); ax.set_ylabel("NZD Billions")
ax.legend(loc="upper left", fontsize=8, frameon=False)
ax.set_facecolor(BG)
ax.grid(axis="y", ls="--", alpha=.4)
ax.spines[["top","right"]].set_visible(False)

# ── Row 5L — Return on equity & return on assets trend ───────────────────────
ax = fig.add_subplot(gs[5, :2])
ts_roe = (pct[(pct["Variable_code"]=="H39") &
              (pct["Industry_aggregation_NZSIOC"]=="Level 1")]
          .groupby("Year")["Value"].mean().sort_index())
ts_roa = (pct[(pct["Variable_code"]=="H40") &
              (pct["Industry_aggregation_NZSIOC"]=="Level 1")]
          .groupby("Year")["Value"].mean().sort_index())
ax.plot(ts_roe.index, ts_roe, "o-",  color="#e377c2", lw=2.2, ms=5, label="Return on Equity (%)")
ax.plot(ts_roa.index, ts_roa, "s--", color=C6,        lw=2.2, ms=5, label="Return on Assets (%)")
ax.axhline(0, color="#aaa", lw=.7, ls=":")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"{x:.1f}%"))
ax.set_title("Return on Equity & Return on Assets (%)", fontweight="bold", fontsize=11)
ax.set_xlabel("Year"); ax.set_ylabel("Percentage")
ax.legend(fontsize=9); ax.set_facecolor(BG)
ax.grid(axis="y", ls="--", alpha=.4)
ax.spines[["top","right"]].set_visible(False)

# ── Row 5R — Operating margin trend ──────────────────────────────────────────
ax = fig.add_subplot(gs[5, 2:])
ts_inc2 = ts("H01"); ts_sur2 = ts("H23")
margin_ts = (ts_sur2 / ts_inc2 * 100).dropna()
bar_cols = [C3 if v>=0 else C2 for v in margin_ts]
ax.bar(margin_ts.index, margin_ts.values, color=bar_cols, alpha=.85, edgecolor="white", width=0.6)
ax.axhline(0, color="#555", lw=.8)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x,_: f"{x:.1f}%"))
ax.set_title("Operating Margin % (Surplus / Total Income)", fontweight="bold", fontsize=11)
ax.set_xlabel("Year"); ax.set_ylabel("Margin %")
ax.set_facecolor(BG)
ax.grid(axis="y", ls="--", alpha=.4)
ax.spines[["top","right"]].set_visible(False)

# ── Row 6 — Industry heatmap (income by year, top 12 industries) ──────────────
ax = fig.add_subplot(gs[6, :])
pivot = (lv3[lv3["Variable_code"]=="H01"]
         .groupby(["Industry_name_NZSIOC","Year"])["Value"]
         .sum().unstack("Year"))
top12 = (pivot[LATEST].sort_values(ascending=False).head(12).index
         if LATEST in pivot.columns else
         pivot.sum(axis=1).sort_values(ascending=False).head(12).index)
ph = pivot.loc[top12] / 1000
ph.index = [n[:32]+"…" if len(n)>32 else n for n in ph.index]

cmap_h = LinearSegmentedColormap.from_list("aes_heat", ["#eef5ff", C1, "#082a50"])
im = ax.imshow(ph.values, aspect="auto", cmap=cmap_h)
ax.set_xticks(range(len(ph.columns)))
ax.set_xticklabels(ph.columns.astype(int), fontsize=8)
ax.set_yticks(range(len(ph.index)))
ax.set_yticklabels(ph.index, fontsize=8)
ax.set_title("Industry Total Income Heatmap by Year (NZD Billions — top 12 industries)",
             fontweight="bold", fontsize=11)
cbar = plt.colorbar(im, ax=ax, fraction=.018, pad=.01)
cbar.set_label("NZD Billions", fontsize=8)
vmax = np.nanmax(ph.values)
for r in range(ph.shape[0]):
    for c in range(ph.shape[1]):
        v = ph.values[r, c]
        if not np.isnan(v):
            txt_c = "white" if v > vmax * .55 else "#111"
            ax.text(c, r, f"{v:.0f}", ha="center", va="center",
                    fontsize=6.5, color=txt_c, fontweight="bold")

# ── 5. Save & display ─────────────────────────────────────────────────────────
OUT = "enterprise_dashboard_2024.png"
plt.savefig(OUT, dpi=150, bbox_inches="tight", facecolor=BG)
print(f"\nDashboard saved -> {OUT}")

# Print summary table to console
print(f"\n{'='*60}")
print(f"  NZ Annual Enterprise Survey — FY{LATEST} Summary")
print(f"{'='*60}")
print(f"  Total Income           : {fmt_b(income)}")
print(f"  Total Expenditure      : {fmt_b(expend)}")
print(f"  Surplus Before Tax     : {fmt_b(surplus)}")
print(f"  Salaries & Wages       : {fmt_b(wages)}")
print(f"  Total Assets           : {fmt_b(assets)}")
print(f"  Operating Margin       : {margin:.1f}%")
print(f"  Income Growth (YoY)    : {yoy:+.1f}%" if yoy else "  Income Growth (YoY)    : N/A")
print(f"  Return on Equity       : {roe_val:.1f}%" if not np.isnan(roe_val) else "  Return on Equity       : N/A")
print(f"  Return on Assets       : {roa_val:.1f}%" if not np.isnan(roa_val) else "  Return on Assets       : N/A")
print(f"  Industries tracked     : {n_ind}")
print(f"  Dataset rows           : {len(raw):,}")
print(f"{'='*60}")

plt.show()
