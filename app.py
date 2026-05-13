import re
from datetime import date

import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="Moomoo Positions Dashboard",
    page_icon="📈",
    layout="wide",
)

OPTION_RE = re.compile(r"^([A-Z.\-]+)\s+(\d{6})\s+([\d.]+)([CP])$", re.IGNORECASE)

NUMERIC_COLS = [
    "Quantity",
    "Current price",
    "Average Cost",
    "Market Value",
    "Today's P/L",
    "Unrealized P/L",
    "% Unrealized P/L",
    "Total P/L",
    "Realized P/L",
    "% of Portfolio",
    "Initial Margin",
    "Delta",
    "Gamma (options only)",
    "Vega (options only)",
    "Theta (options only)",
    "Rho (options only)",
    "IV (options only)",
    "Intrinsic Value (options only)",
    "Extrinsic Value (options only)",
]


def to_num(series: pd.Series) -> pd.Series:
    return pd.to_numeric(
        series.astype(str)
        .str.replace(",", "", regex=False)
        .str.replace("$", "", regex=False)
        .str.replace("%", "", regex=False)
        .str.replace("+", "", regex=False)
        .str.strip()
        .replace({"--": None, "nan": None, "None": None, "": None}),
        errors="coerce",
    ).fillna(0.0)


def parse_option_name(name: str) -> dict:
    m = OPTION_RE.match(str(name).strip())
    if not m:
        return {
            "Underlying": None,
            "Expiry": pd.NaT,
            "Strike": None,
            "Type": "STOCK",
            "IsOption": False,
        }

    underlying, yymmdd, strike, opt_type = m.groups()
    year = 2000 + int(yymmdd[:2])
    month = int(yymmdd[2:4])
    day = int(yymmdd[4:6])

    return {
        "Underlying": underlying.upper(),
        "Expiry": pd.Timestamp(year=year, month=month, day=day),
        "Strike": float(strike),
        "Type": opt_type.upper(),
        "IsOption": True,
    }


def calc_dte(expiry):
    if pd.isna(expiry):
        return None
    return (expiry.date() - date.today()).days


def classify_position(row) -> tuple[str, str]:
    is_option = bool(row["IsOption"])
    dte = row["DTE"]
    mv = float(row["Market Value"])
    pnl_pct = float(row["% Unrealized P/L"])
    intrinsic = float(row["Intrinsic Value (options only)"])
    qty = float(row["Quantity"])

    if not is_option:
        if qty <= 2 and mv < 25:
            return "CLEAN UP", "Tiny stock position. More clutter than real exposure."
        return "WATCH", "Stock position with no option-expiration pressure."

    if dte is not None and dte <= 2:
        if intrinsic > 0 and mv > 20:
            return "SELL NOW", "Near-expiry option with real value. Protect it before final-day decay hits."
        if pnl_pct > 0 and mv > 25:
            return "SELL NOW", "Short-dated winner. Lock it instead of squeezing for the last few cents."
        return "SALVAGE", "Very little time left and weak odds. Take any bid if there is one."

    if pnl_pct >= 300:
        return "TAKE PROFIT", "Huge winner. Best time to bank gains before they round-trip."
    if pnl_pct >= 100:
        return "TAKE PROFIT", "Strong winner with enough premium to protect."
    if dte is not None and dte <= 10 and pnl_pct <= -70:
        return "SALVAGE", "Short time left and already badly damaged."
    if dte is not None and dte > 10 and -30 <= pnl_pct < 100:
        return "HOLD", "Still has time. Not the most urgent position today."

    return "WATCH", "Needs monitoring, but it's not the top priority."


def action_color(action: str) -> str:
    colors = {
        "SELL NOW": "#ff5f78",
        "TAKE PROFIT": "#f2c14e",
        "SALVAGE": "#9ba8d0",
        "HOLD": "#1ec980",
        "WATCH": "#63a4ff",
        "CLEAN UP": "#b08cff",
    }
    return colors.get(action, "#63a4ff")


@st.cache_data
def load_data(uploaded_file) -> pd.DataFrame:
    df = pd.read_csv(uploaded_file, encoding="utf-8-sig")

    for col in NUMERIC_COLS:
        if col in df.columns:
            df[col] = to_num(df[col])

    parsed = df["Name"].apply(parse_option_name).apply(pd.Series)
    df = pd.concat([df, parsed], axis=1)

    df["Expiry"] = pd.to_datetime(df["Expiry"], errors="coerce")
    df["ExpiryStr"] = df["Expiry"].dt.strftime("%Y-%m-%d").fillna("N/A")
    df["DTE"] = df["Expiry"].apply(calc_dte)

    actions = df.apply(classify_position, axis=1, result_type="expand")
    df["Action"] = actions[0]
    df["Reason"] = actions[1]

    return df


def fmt_money(x):
    return f"${x:,.2f}"


def export_action_csv(df: pd.DataFrame) -> bytes:
    cols = [
        "Symbol",
        "Name",
        "Quantity",
        "ExpiryStr",
        "Market Value",
        "Unrealized P/L",
        "% Unrealized P/L",
        "Action",
        "Reason",
    ]
    out = df[cols].rename(columns={"ExpiryStr": "Expiry"})
    return out.to_csv(index=False).encode("utf-8")


st.title("📈 Moomoo Positions Dashboard")
st.caption("Upload your Moomoo positions CSV to get a cleanup view: sell now, take profit, salvage, hold.")

uploaded_file = st.file_uploader(
    "Upload Moomoo Positions CSV",
    type="csv",
    help="Use the raw Moomoo positions export CSV.",
)

if uploaded_file is None:
    st.info("Upload your CSV to start.")
    st.stop()

df = load_data(uploaded_file)

with st.sidebar:
    st.header("Filters")
    search = st.text_input("Search ticker or name")
    actions = st.multiselect(
        "Action",
        options=["SELL NOW", "TAKE PROFIT", "SALVAGE", "HOLD", "WATCH", "CLEAN UP"],
        default=[],
    )
    expiring_week = st.checkbox("Only expiring this week", value=False)

    st.divider()
    st.download_button(
        "Download action list CSV",
        data=export_action_csv(df),
        file_name="positions_action_list.csv",
        mime="text/csv",
        use_container_width=True,
    )

filtered = df.copy()

if search:
    s = search.lower().strip()
    filtered = filtered[
        filtered["Symbol"].astype(str).str.lower().str.contains(s)
        | filtered["Name"].astype(str).str.lower().str.contains(s)
        | filtered["Underlying"].astype(str).str.lower().str.contains(s)
    ]

if actions:
    filtered = filtered[filtered["Action"].isin(actions)]

if expiring_week:
    filtered = filtered[filtered["DTE"].fillna(9999) <= 7]

total_value = df["Market Value"].sum()
total_unreal = df["Unrealized P/L"].sum()
week_value = df.loc[df["DTE"].fillna(9999) <= 7, "Market Value"].sum()
tp_count = int((df["Action"] == "TAKE PROFIT").sum())
salvage_count = int((df["Action"] == "SALVAGE").sum())
sell_now_count = int((df["Action"] == "SELL NOW").sum())

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Value", fmt_money(total_value))
c2.metric("Unrealized P/L", fmt_money(total_unreal))
c3.metric("Expiring This Week", fmt_money(week_value))
c4.metric("Sell Now", sell_now_count)
c5.metric("Take Profit", tp_count)
c6.metric("Salvage", salvage_count)

st.divider()

left, right = st.columns([1.65, 1])

display = filtered[
    [
        "Symbol",
        "Name",
        "Quantity",
        "ExpiryStr",
        "DTE",
        "Market Value",
        "Unrealized P/L",
        "% Unrealized P/L",
        "Action",
    ]
].copy()

display = display.rename(columns={"ExpiryStr": "Expiry"})

with left:
    st.subheader("Positions")
    if display.empty:
        st.warning("No positions match your filter.")
    else:
        event = st.dataframe(
            display,
            hide_index=True,
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            column_config={
                "Quantity": st.column_config.NumberColumn(format="%d"),
                "Market Value": st.column_config.NumberColumn(format="$ %.2f"),
                "Unrealized P/L": st.column_config.NumberColumn(format="$ %.2f"),
                "% Unrealized P/L": st.column_config.NumberColumn(format="%.2f%%"),
                "DTE": st.column_config.NumberColumn("Days Left", format="%d"),
            },
            key="positions_table",
        )

with right:
    st.subheader("Selected Position")

    if display.empty:
        st.info("Nothing to show.")
    else:
        selected_idx = 0
        if event and event.selection and event.selection["rows"]:
            selected_idx = event.selection["rows"][0]

        row = filtered.iloc[selected_idx]

        st.markdown(
            f"""
            <div style="padding:12px 14px;border-radius:12px;background:{action_color(row['Action'])}22;border:1px solid {action_color(row['Action'])};margin-bottom:12px;">
            <strong>{row['Action']}</strong><br>{row['Reason']}
            </div>
            """,
            unsafe_allow_html=True,
        )

        d1, d2 = st.columns(2)
        d1.metric("Qty", int(row["Quantity"]))
        d2.metric("Current Price", fmt_money(row["Current price"]))

        d3, d4 = st.columns(2)
        d3.metric("Avg Cost", fmt_money(row["Average Cost"]))
        d4.metric("Market Value", fmt_money(row["Market Value"]))

        d5, d6 = st.columns(2)
        d5.metric("Unrealized P/L", fmt_money(row["Unrealized P/L"]))
        d6.metric("Unrealized %", f"{row['% Unrealized P/L']:.2f}%")

        if row["IsOption"]:
            st.markdown("**Option details**")
            o1, o2 = st.columns(2)
            o1.metric("Underlying", row["Underlying"])
            o2.metric("Type", "Call" if row["Type"] == "C" else "Put")

            o3, o4 = st.columns(2)
            o3.metric("Strike", row["Strike"])
            o4.metric("Expiry", row["ExpiryStr"])

            o5, o6 = st.columns(2)
            o5.metric("Delta", f"{row['Delta']:.4f}")
            o6.metric("Theta", f"{row['Theta (options only)']:.4f}")

            o7, o8 = st.columns(2)
            o7.metric("Intrinsic", fmt_money(row["Intrinsic Value (options only)"]))
            o8.metric("Extrinsic", fmt_money(row["Extrinsic Value (options only)"]))

        st.markdown("**What I'd do next**")
        if row["Action"] == "SELL NOW":
            st.write("- Close it while it still has real value.")
            st.write("- Don’t let a near-expiry winner turn into a theta victim.")
        elif row["Action"] == "TAKE PROFIT":
            st.write("- Bank the gain or trim it hard.")
            st.write("- These are the trades that too often turn into stories.")
        elif row["Action"] == "SALVAGE":
            st.write("- If there’s a bid, take it.")
            st.write("- Stop spending attention on dead premium.")
        elif row["Action"] == "HOLD":
            st.write("- Not urgent today.")
            st.write("- Reassess if the underlying weakens or volatility collapses.")
        elif row["Action"] == "CLEAN UP":
            st.write("- Close it if you want the account cleaner.")
            st.write("- It’s too small to matter much.")
        else:
            st.write("- Monitor it, but prioritize expiring trades first.")

st.divider()
st.caption("Tip: click a row in the table, then use the details panel on the right.")
