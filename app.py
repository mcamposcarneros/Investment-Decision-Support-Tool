# -*- coding: utf-8 -*-
"""
app.py — Energy Advisor · Streamlit UI
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go


from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from finance import (
    ProjectInputs,
    calculate_metrics,
    sensitivity_analysis,
    monte_carlo,
    get_market_price_api,
)

# ---------------------------------------------------------------------------
# PDF: Investment Memo
# ---------------------------------------------------------------------------

def build_investment_memo_pdf(p_in: ProjectInputs, res: dict, mc: dict | None,
                              country_label: str, tech_label: str) -> bytes:
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    y = height - 50
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "Investment Memo — Energy Advisor (Screening)")
    y -= 22

    c.setFont("Helvetica", 10)
    c.drawString(50, y, f"Location: {country_label} | Technology: {tech_label}")
    y -= 18
    c.drawString(50, y, "Disclaimer: Educational screening tool — not financial advice.")
    y -= 28

    # Inputs
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Key Inputs")
    y -= 16
    c.setFont("Helvetica", 10)

    inputs_lines = [
        f"Project life: {p_in.years} years",
        f"CAPEX: {p_in.capex/1e6:.2f} M€",
        f"Annual MWh (Y1): {p_in.annual_mwh:,.0f}",
        f"Price (Y1): {p_in.price_eur_mwh:.2f} €/MWh",
        f"OPEX fixed: {p_in.opex_fixed/1e3:,.0f} k€/yr | OPEX var: {p_in.opex_var_eur_mwh:.2f} €/MWh",
        f"WACC: {p_in.wacc*100:.2f}% | Tax: {p_in.tax_rate*100:.1f}%",
        f"Debt ratio: {p_in.debt_ratio*100:.0f}% | Interest: {p_in.interest_rate*100:.2f}% | Tenor: {p_in.debt_years}y",
        f"Inflation: {p_in.inflation*100:.2f}% | Price degradation: {p_in.price_degradation*100:.2f}% | Production degradation: {p_in.degradation*100:.2f}%",
    ]
    for line in inputs_lines:
        c.drawString(60, y, f"• {line}")
        y -= 14
        if y < 120:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 10)

    y -= 8

    # KPIs
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "KPIs")
    y -= 16
    c.setFont("Helvetica", 10)

    irr_val = res.get("irr", None)
    irr_str = f"{irr_val*100:.2f}%" if irr_val is not None else "N/D"
    lcoe = res.get("lcoe", None)
    lcoe_str = f"{lcoe:.2f} €/MWh" if lcoe is not None else "N/D"

    pb = res.get("payback", None)
    dpb = res.get("discounted_payback", None)

    kpi_lines = [
        f"NPV (unlevered): {res['npv']/1e6:.2f} M€",
        f"IRR: {irr_str}",
        f"LCOE: {lcoe_str}",
        f"Payback: {pb:.1f} years" if pb is not None else "Payback: > project life",
        f"Discounted Payback: {dpb:.1f} years" if dpb is not None else "Discounted Payback: > project life",
    ]
    for line in kpi_lines:
        c.drawString(60, y, f"• {line}")
        y -= 14
        if y < 120:
            c.showPage()
            y = height - 50
            c.setFont("Helvetica", 10)

    y -= 8

    # Benchmark
    if lcoe is not None:
        spread = p_in.price_eur_mwh - lcoe
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Benchmark: Price vs LCOE")
        y -= 16
        c.setFont("Helvetica", 10)
        status = "Competitive (in-the-money)" if spread >= 0 else "Not competitive (out-of-the-money)"
        c.drawString(60, y, f"• Status: {status}")
        y -= 14
        c.drawString(60, y, f"• Spread (Price - LCOE): {spread:+.2f} €/MWh")
        y -= 20

    # Risk (Monte Carlo)
    if mc is not None:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(50, y, "Risk (Monte Carlo)")
        y -= 16
        c.setFont("Helvetica", 10)

        risk_lines = [
            f"Probability NPV>0: {mc['prob_positive']*100:.1f}%",
            f"NPV mean: {mc['mean']/1e6:.2f} M€",
            f"NPV P50: {mc['p50']/1e6:.2f} M€",
            f"VaR 95% (P5): {mc['var_95']/1e6:.2f} M€",
        ]
        for line in risk_lines:
            c.drawString(60, y, f"• {line}")
            y -= 14
            if y < 120:
                c.showPage()
                y = height - 50
                c.setFont("Helvetica", 10)

    y -= 8

    # Recomendación Determinista (siempre)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Screening Recommendation")
    y -= 16
    c.setFont("Helvetica", 10)

    det_ok = (res["npv"] > 0) and (irr_val is None or irr_val > p_in.wacc)
    det_text = "PASS (NPV>0 and IRR>WACC)" if det_ok else "FAIL / REVIEW (NPV<=0 or IRR<=WACC)"
    c.drawString(60, y, f"• Deterministic: {det_text}")
    y -= 14

    if mc is not None:
        prob = mc["prob_positive"]
        mean_npv = mc["mean"]
        var95 = mc["var_95"]

        if prob >= 0.70 and var95 > -0.10 * p_in.capex:
            verdict = "PASS (screening positive)"
            rationale = "High probability of value creation and acceptable downside."
        elif prob >= 0.50 and mean_npv > 0:
            verdict = "REVIEW (needs due diligence / improve assumptions)"
            rationale = "Positive expected value but material risk."
        else:
            verdict = "FAIL (screening negative)"
            rationale = "Low probability of positive NPV or high downside risk."

        c.drawString(60, y, f"• Risk-based: {verdict}")
        y -= 14
        c.drawString(60, y, f"• Note: {rationale}")
        y -= 14

    c.setFont("Helvetica", 9)
    c.drawString(50, 40, "Generated by Energy Advisor — personal project.")
    c.showPage()
    c.save()

    pdf = buffer.getvalue()
    buffer.close()
    return pdf


# ---------------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Energy Advisor",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
[data-testid="stMetricValue"] {
    color: #00d4aa !important;
    font-weight: 700 !important;
    font-size: 1.4rem !important;
}
[data-testid="stMetricLabel"] {
    color: #a0b4c8 !important;
    font-size: 0.85rem !important;
}
div[data-testid="metric-container"] {
    background: rgba(0, 212, 170, 0.07);
    border: 1px solid rgba(0, 212, 170, 0.25);
    padding: 14px 18px;
    border-radius: 10px;
}
.kpi-positive { color: #00d4aa !important; }
.kpi-negative { color: #ff6b6b !important; }
.source-tag {
    font-size: 0.75rem;
    color: #888;
    margin-top: -6px;
    margin-bottom: 8px;
}
section[data-testid="stSidebar"] { min-width: 300px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "price_val" not in st.session_state:
    st.session_state["price_val"] = 58.4
    st.session_state["price_source"] = "manual"
    st.session_state["mc_results"] = None
    st.session_state["entsoe_token"] = ""

# ---------------------------------------------------------------------------
# Constantes de referencia (fuentes citadas)
# ---------------------------------------------------------------------------
COUNTRY_DATA = {
    "España (ES)": {
        "code": "ES",
        "cost_solar": 750,     # €/kW — BNEF Solar PV Cost Report 2024
        "cost_wind": 1250,     # €/kW — IRENA Renewable Power 2023
        "cost_battery": 350,   # €/kWh — BloombergNEF BESS Outlook 2024
        "tax_rate": 0.25,
        "label": "Referencia: BNEF / IRENA 2024",
        "label_battery": "Referencia: BloombergNEF BESS Outlook 2024",
    },
    "Alemania (DE)": {
        "code": "DE",
        "cost_solar": 870,
        "cost_wind": 1480,
        "cost_battery": 400,   # €/kWh — BloombergNEF BESS Outlook 2024
        "tax_rate": 0.30,
        "label": "Referencia: Fraunhofer ISE 2024",
        "label_battery": "Referencia: BloombergNEF BESS Outlook 2024",
    },
    "Francia (FR)": {
        "code": "FR",
        "cost_solar": 810,
        "cost_wind": 1380,
        "cost_battery": 380,   # €/kWh — BloombergNEF BESS Outlook 2024
        "tax_rate": 0.25,
        "label": "Referencia: ADEME 2024",
        "label_battery": "Referencia: BloombergNEF BESS Outlook 2024",
    },
}

TECH_DATA = {
    "Solar PV": {
        "capex_key": "cost_solar",
        "cf": 0.22,            # Factor de capacidad medio España
        "degradation": 0.005,  # 0.5%/año — NREL 2023
        "opex_eur_kw": 17,     # €/kW·año — IRENA 2023
        "life": 30,
        "unit": "kW",
    },
    "Eólica": {
        "capex_key": "cost_wind",
        "cf": 0.28,
        "degradation": 0.002,
        "opex_eur_kw": 35,
        "life": 25,
        "unit": "kW",
    },
    "Baterías (BESS)": {
        "capex_key": "cost_battery",
        "cf": None,            # Baterías: el usuario define ciclos
        "degradation": 0.020,  # 2%/año degradación capacidad
        "opex_eur_kw": 8,
        "life": 15,
        "unit": "kWh",
    },
}

# ---------------------------------------------------------------------------
# Barra lateral — Localización y tecnología
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("---")
    st.markdown("<h1 style='text-align: center;'>Energy Advisor</h1>", unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("<p style='text-align: center; color: #888; font-size: 0.85rem;'>Herramienta de análisis de inversión en energías renovables</p>", unsafe_allow_html=True)
    st.divider()

    st.subheader("Localización")
    pais = st.selectbox("País del proyecto", list(COUNTRY_DATA.keys()))
    country = COUNTRY_DATA[pais]

    src = st.session_state["price_source"]
    if src == "live":
        badge_color, badge_bg, badge_text = "#27ae60", "rgba(39,174,96,0.12)", "Live"
    elif src == "reference":
        badge_color, badge_bg, badge_text = "#2980b9", "rgba(41,128,185,0.12)", "Ref."
    else:
        badge_color, badge_bg, badge_text = "#d4a017", "rgba(212,160,23,0.12)", "Manual"

    st.markdown(f"""
    <style>
    div[data-testid="stSidebar"] button[kind="secondary"] {{
        font-size: 0.78rem !important;
        font-weight: 600 !important;
        padding: 7px 0 !important;
        height: auto !important;
        border-radius: 6px !important;
        border: 1px solid #555 !important;
        white-space: nowrap !important;
    }}
    .badge-estado {{
        padding: 7px 0;
        background: {badge_bg};
        border: 1px solid {badge_color};
        border-radius: 6px;
        color: {badge_color};
        font-size: 0.78rem;
        font-weight: 600;
        text-align: center;
        white-space: nowrap;
    }}
    </style>
    """, unsafe_allow_html=True)

    col_api, col_info = st.columns([3, 1])
    with col_api:
        if st.button("Precio de mercado", use_container_width=True):
            precio_api, is_live = get_market_price_api(
                country["code"],
                entsoe_token=st.session_state.get("entsoe_token", "")
            )
            st.session_state["price_val"] = precio_api
            st.session_state["price_source"] = "live" if is_live else "reference"
            st.session_state["mc_results"] = None
            st.rerun()
    with col_info:
        st.markdown(f'<div class="badge-estado">{badge_text}</div>', unsafe_allow_html=True)

    if st.session_state["price_source"] == "live":
        st.caption(f"Precio real de mercado OMIE — dato de ayer ({st.session_state['price_val']} €/MWh).")
    elif st.session_state["price_source"] == "reference":
        if country["code"] in ("ES", "PT"):
            st.caption("⚠️ OMIE no disponible en este momento. Usando referencia histórica 2024.")
        else:
            st.caption("ℹ️ Introduce tu token de ENTSO-E abajo para obtener datos live de DE/FR.")
    elif st.session_state["price_source"] == "manual":
        st.caption("⚠️ Valor introducido manualmente.")

    if country["code"] not in ("ES", "PT"):
        with st.expander("Token ENTSO-E (opcional, para DE/FR)"):
            token = st.text_input(
                "Token ENTSO-E",
                value=st.session_state.get("entsoe_token", ""),
                type="password",
                help="Regístrate gratis en transparency.entsoe.eu para obtener tu token"
            )
            st.session_state["entsoe_token"] = token
            st.caption("Sin token, se usan precios de referencia ENTSO-E 2024.")

    st.divider()
    st.subheader("Tecnología")
    tech = st.radio("Tipo de proyecto", list(TECH_DATA.keys()))
    tdata = TECH_DATA[tech]

    st.divider()

    st.subheader("KPIs del proyecto")
    kpi_placeholder = st.empty()

# ---------------------------------------------------------------------------
# Tabs principales
# ---------------------------------------------------------------------------
tab_conf, tab_res, tab_risk, tab_method = st.tabs([
    "Configuración",
    "Resultados",
    "Riesgo",
    "Metodología",
])

# ---------------------------------------------------------------------------
# TAB 1 — Configuración
# ---------------------------------------------------------------------------
with tab_conf:
    st.header("Parámetros del proyecto")

    st.subheader("Estructura financiera")

    wacc = st.slider(
        "WACC (%)",
        min_value=4.0, max_value=15.0, value=8.0, step=0.25,
        help="Coste medio ponderado del capital. Referencia sector renovables España: 6–9% (CNMC 2024)"
    ) / 100

    debt_ratio = st.slider(
        "Ratio de deuda (%)",
        min_value=0, max_value=80, value=60,
        help="% del CAPEX financiado con deuda. Proyectos utility-scale típico: 60–75%"
    ) / 100

    interest_rate = st.slider(
        "Tipo de interés de la deuda (%)",
        min_value=2.0, max_value=8.0, value=4.5, step=0.25,
        help="Euribor 12M + spread bancario. Referencia 2024: ~4–5%"
    ) / 100

    debt_years = st.slider(
        "Plazo del préstamo (años)",
        min_value=5, max_value=25, value=15,
        help="Plazo habitual en project finance renovable: 15–20 años"
    )

    tax_rate = st.number_input(
        "Tipo impositivo efectivo (%)",
        min_value=0.0, max_value=50.0,
        value=country["tax_rate"] * 100,
        help=f"Valor por defecto para {pais}: {country['tax_rate']*100:.0f}%"
    ) / 100

    dep_years = st.slider(
        "Años de amortización fiscal",
        min_value=5, max_value=30, value=min(tdata["life"], 20),
        help="Amortización acelerada reduce la carga fiscal en los primeros años"
    )

    st.divider()

    st.subheader("Ingeniería y CAPEX")

    mw = st.number_input(
        "Potencia / Capacidad (MW / MWh)",
        min_value=0.1, max_value=1000.0, value=10.0, step=0.5,
        help="Potencia instalada para generación, o capacidad para baterías"
    )

    base_cost_kw = country[tdata["capex_key"]]
    capex = mw * 1000 * base_cost_kw
    capex_label = country["label_battery"] if tech == "Baterías (BESS)" else country["label"]
    st.metric(
        "CAPEX estimado",
        f"{capex/1e6:.2f} M€",
        help=f"Fuente: {capex_label}"
    )
    st.markdown(
        f'<p class="source-tag">Fuente: {capex_label} — {base_cost_kw} €/{tdata["unit"]}</p>',
        unsafe_allow_html=True
    )

    st.divider()

    st.subheader("Ingresos y producción")

    if tdata["cf"] is not None:
        default_mwh = mw * tdata["cf"] * 8760
        st.caption(f"Producción estimada con CF={tdata['cf']:.0%}: {default_mwh:,.0f} MWh/año")
    else:
        default_mwh = mw * 250
        st.caption(f"Producción estimada (ciclos): {default_mwh:,.0f} MWh/año")

    annual_mwh = st.number_input(
        "Producción año 1 (MWh)",
        min_value=1.0, value=float(round(default_mwh)),
        help="Ajusta según el recurso específico del emplazamiento (P50 del estudio de viento/sol)"
    )

    st.session_state["price_input"] = float(st.session_state["price_val"])
    price = st.number_input(
        "Precio de venta año 1 (€/MWh)",
        min_value=1.0,
        key="price_input",
        help="PPA, precio de mercado spot o tarifa regulada"
    )
    st.session_state["price_val"] = price

    inf = st.number_input(
        "Inflación OPEX (%/año)",
        min_value=0.0, max_value=10.0, value=2.0,
        help="IPC esperado para indexar costes operativos"
    ) / 100

    price_deg = st.number_input(
        "Caída anual del precio de mercado (%)",
        min_value=0.0, max_value=5.0, value=0.5,
        help="Tendencia bajista del precio mayorista por mayor penetración renovable"
    ) / 100

    degradation = st.number_input(
        "Degradación de producción (%/año)",
        min_value=0.0, max_value=5.0,
        value=tdata["degradation"] * 100,
        help=f"Valor típico {tech}: {tdata['degradation']*100:.1f}%/año (NREL 2023)"
    ) / 100

    opex_fixed = mw * 1000 * tdata["opex_eur_kw"]
    st.metric(
        "OPEX fijo estimado",
        f"{opex_fixed/1e3:.0f} k€/año",
        help=f"Fuente: {country['label']}"
    )
    st.markdown(
        f'<p class="source-tag">Fuente: IRENA O&M Cost Report 2023 — {tdata["opex_eur_kw"]} €/{tdata["unit"]}·año</p>',
        unsafe_allow_html=True
    )

    opex_var = st.number_input(
        "OPEX variable (€/MWh)",
        min_value=0.0, value=3.0,
        help="Coste variable de operación por MWh producido"
    )

# ---------------------------------------------------------------------------
# Construcción del objeto de inputs y cálculo
# ---------------------------------------------------------------------------
p_in = ProjectInputs(
    years=tdata["life"],
    capex=float(capex),
    annual_mwh=float(annual_mwh),
    price_eur_mwh=float(price),
    opex_fixed=float(opex_fixed),
    opex_var_eur_mwh=float(opex_var),
    degradation=float(degradation),
    inflation=float(inf),
    price_degradation=float(price_deg),
    tax_rate=float(tax_rate),
    depreciation_years=int(dep_years),
    wacc=float(wacc),
    debt_ratio=float(debt_ratio),
    interest_rate=float(interest_rate),
    debt_years=int(debt_years),
)

res = calculate_metrics(p_in)

# Actualiza KPIs en sidebar
irr_val = res["irr"]
irr_str = f"{irr_val*100:.1f}%" if irr_val is not None else "N/D"
npv_sign = "🟢" if res["npv"] > 0 else "🔴"

with kpi_placeholder.container():
    st.metric("VAN", f"{res['npv']/1e6:.2f} M€")
    st.metric("TIR", irr_str)
    st.metric("LCOE", f"{res['lcoe']:.1f} €/MWh" if res["lcoe"] else "N/D")
    st.metric("Payback", f"{res['payback']:.1f} años" if res["payback"] else ">vida útil")
    st.caption(f"{npv_sign} Proyecto {'VIABLE' if res['npv'] > 0 else 'NO VIABLE'} a WACC={wacc*100:.1f}%")

# ---------------------------------------------------------------------------
# TAB 2 — Resultados
# ---------------------------------------------------------------------------
with tab_res:
    st.header("Análisis de rentabilidad")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("VAN (Unlevered)", f"{res['npv']/1e6:.2f} M€",
              help="Valor actual neto descontado al WACC sobre flujos antes de deuda")
    c2.metric("TIR", irr_str,
              help="Tasa interna de retorno. Compara con WACC para evaluar si el proyecto crea valor")
    c3.metric("LCOE", f"{res['lcoe']:.1f} €/MWh" if res["lcoe"] else "N/D",
              help="Coste nivelado de energía — precio mínimo de venta para cubrir todos los costes")
    c4.metric("Payback simple", f"{res['payback']:.1f} a" if res["payback"] else ">vida útil")
    c5.metric("Payback descontado",
              f"{res['discounted_payback']:.1f} a" if res["discounted_payback"] else ">vida útil")

    # Recomendación rápida determinista
    st.divider()
    st.subheader("Recomendación rápida (sin riesgo)")

    if res["npv"] > 0 and (res["irr"] is None or res["irr"] > p_in.wacc):
        st.success(
            "🟢 **Apto para avanzar** (VAN>0 y TIR>WACC).\n\n"
            f"- VAN: **{res['npv']/1e6:.2f} M€**\n"
            f"- TIR: **{irr_str}**\n"
            f"- WACC: **{p_in.wacc*100:.1f}%**"
        )
    else:
        st.warning(
            "🟠 **No concluyente / No apto** (VAN≤0 o TIR≤WACC).\n\n"
            f"- VAN: **{res['npv']/1e6:.2f} M€**\n"
            f"- TIR: **{irr_str}**\n"
            f"- WACC: **{p_in.wacc*100:.1f}%**"
        )

    flows = res["flows"]
    years_arr = np.arange(1, p_in.years + 1)

    st.divider()
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.subheader("Flujos de caja anuales")
        fig_cf = go.Figure()
        fig_cf.add_trace(go.Bar(
            x=years_arr, y=flows["cf_unlevered"] / 1e6,
            name="CF Unlevered", marker_color="#2980b9"
        ))
        fig_cf.add_trace(go.Bar(
            x=years_arr, y=flows["cf_levered"] / 1e6,
            name="CF Levered (equity)", marker_color="#16a085"
        ))
        fig_cf.add_trace(go.Scatter(
            x=years_arr,
            y=np.cumsum(flows["cf_unlevered"]) / 1e6,
            name="CF Acumulado", mode="lines+markers",
            line=dict(color="#e74c3c", width=2), yaxis="y2"
        ))
        fig_cf.update_layout(
            barmode="group", height=380,
            yaxis=dict(title="M€/año"),
            yaxis2=dict(title="M€ acumulado", overlaying="y", side="right"),
            legend=dict(orientation="h", y=-0.2),
        )
        st.plotly_chart(fig_cf, use_container_width=True)

    with col_chart2:
        st.subheader("Desglose de ingresos y costes")
        fig_breakdown = go.Figure()
        fig_breakdown.add_trace(go.Scatter(
            x=years_arr, y=flows["revenue_t"] / 1e6,
            name="Ingresos", fill="tozeroy",
            line=dict(color="#27ae60")
        ))
        fig_breakdown.add_trace(go.Scatter(
            x=years_arr, y=flows["opex_t"] / 1e6,
            name="OPEX", line=dict(color="#e67e22", dash="dash")
        ))
        fig_breakdown.add_trace(go.Scatter(
            x=years_arr, y=flows["interest_t"] / 1e6,
            name="Intereses deuda", line=dict(color="#c0392b", dash="dot")
        ))
        fig_breakdown.update_layout(
            height=380, yaxis_title="M€",
            legend=dict(orientation="h", y=-0.2)
        )
        st.plotly_chart(fig_breakdown, use_container_width=True)

    with st.expander("Tabla de flujos de caja detallada"):
        df_flows = pd.DataFrame({
            "Año": years_arr,
            "Producción (MWh)": flows["mwh_t"].round(0),
            "Precio (€/MWh)": flows["price_t"].round(2),
            "Ingresos (k€)": (flows["revenue_t"] / 1e3).round(1),
            "OPEX (k€)": (flows["opex_t"] / 1e3).round(1),
            "Amort. Fiscal (k€)": (flows["dep_t"] / 1e3).round(1),
            "EBIT (k€)": (flows["ebit_t"] / 1e3).round(1),
            "Impuestos (k€)": (flows["taxes_t"] / 1e3).round(1),
            "Intereses (k€)": (flows["interest_t"] / 1e3).round(1),
            "CF Unlevered (k€)": (flows["cf_unlevered"] / 1e3).round(1),
            "CF Levered (k€)": (flows["cf_levered"] / 1e3).round(1),
        }).set_index("Año")
        st.dataframe(df_flows, use_container_width=True)

    # Benchmark mercado LCOE vs Precio
    st.divider()
    st.subheader("Benchmark mercado: LCOE vs Precio")

    lcoe = res["lcoe"]
    market_price = p_in.price_eur_mwh  # precio que usa el modelo

    if lcoe is not None:
        spread = market_price - lcoe  # €/MWh
        if spread >= 0:
            st.success(
                f"🟢 **Competitivo**: Precio ({market_price:.2f} €/MWh) ≥ LCOE ({lcoe:.2f} €/MWh)\n\n"
                f"Spread: **+{spread:.2f} €/MWh**"
            )
        else:
            st.error(
                f"🔴 **No competitivo**: Precio ({market_price:.2f} €/MWh) < LCOE ({lcoe:.2f} €/MWh)\n\n"
                f"Spread: **{spread:.2f} €/MWh** (falta {-spread:.2f} €/MWh para break-even)"
            )

        st.caption("Interpretación: si el precio esperado cae por debajo del LCOE de forma sostenida, el proyecto destruye valor salvo mejoras (CAPEX/OPEX/CF/WACC).")
    else:
        st.info("LCOE no disponible con los supuestos actuales.")

    # Sensibilidad tornado
    st.divider()
    st.subheader("Análisis de sensibilidad tornado (±10%, ±20%)")

    sens = sensitivity_analysis(p_in, deltas=(-0.20, -0.10, 0.10, 0.20))

    fig_tornado = go.Figure()
    colors = ["#c0392b", "#e74c3c", "#27ae60", "#2ecc71"]
    delta_labels = ["-20%", "-10%", "+10%", "+20%"]
    deltas_vals = (-0.20, -0.10, 0.10, 0.20)

    for d, color, dlabel in zip(deltas_vals, colors, delta_labels):
        x_vals = [sens[label][d] / 1e6 for label in sens]
        fig_tornado.add_trace(go.Bar(
            y=list(sens.keys()),
            x=x_vals,
            name=dlabel,
            orientation="h",
            marker_color=color,
        ))

    fig_tornado.add_vline(x=0, line_width=1, line_color="black")
    fig_tornado.update_layout(
        barmode="group", height=420,
        xaxis_title="Variación en VAN (M€)",
        legend=dict(orientation="h", y=-0.15),
    )
    st.plotly_chart(fig_tornado, use_container_width=True)

    # Export PDF
    st.divider()
    st.subheader("Exportar Investment Memo (PDF)")

    pdf_bytes = build_investment_memo_pdf(
        p_in=p_in,
        res=res,
        mc=st.session_state.get("mc_results"),
        country_label=pais,
        tech_label=tech
    )

    st.download_button(
        label="Descargar PDF",
        data=pdf_bytes,
        file_name="investment_memo_energy_advisor.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

# ---------------------------------------------------------------------------
# TAB 3 — Riesgo (Monte Carlo)
# ---------------------------------------------------------------------------
with tab_risk:
    st.header("Análisis de riesgo — Simulación Monte Carlo")

    st.markdown("""
    La simulación varía simultáneamente **precio, producción, CAPEX, OPEX y WACC**
    usando distribuciones normales centradas en los valores base.
    Se ejecutan escenarios para estimar la distribución del VAN.
    """)

    col_mc_params, col_mc_run = st.columns([3, 1])
    with col_mc_params:
        n_sims = st.select_slider(
            "Número de simulaciones",
            options=[1000, 2000, 5000, 10000],
            value=5000
        )
    with col_mc_run:
        st.write("")
        run_mc = st.button("▶ Ejecutar Monte Carlo", type="primary", use_container_width=True)

    if run_mc:
        with st.spinner("Ejecutando simulación..."):
            st.session_state["mc_results"] = monte_carlo(p_in, n_simulations=n_sims)

    mc = st.session_state.get("mc_results")

    if mc is not None:
        st.divider()
        col_v1, col_v2, col_v3, col_v4, col_v5 = st.columns(5)
        col_v1.metric("VAN P5 (VaR 95%)", f"{mc['var_95']/1e6:.2f} M€",
                      help="El 5% de los escenarios tiene un VAN inferior a este valor")
        col_v2.metric("VAN P25", f"{mc['p25']/1e6:.2f} M€")
        col_v3.metric("VAN P50 (mediana)", f"{mc['p50']/1e6:.2f} M€")
        col_v4.metric("VAN P75", f"{mc['p75']/1e6:.2f} M€")
        col_v5.metric("Prob. VAN > 0", f"{mc['prob_positive']*100:.1f}%")

        col_hist, col_box = st.columns(2)

        with col_hist:
            st.subheader("Distribución del VAN")
            fig_hist = go.Figure()
            fig_hist.add_trace(go.Histogram(
                x=mc["npvs"] / 1e6,
                nbinsx=80,
                name="Simulaciones",
                marker_color="#2980b9",
                opacity=0.75,
            ))
            for pval, pname, color in [
                (mc["var_95"], "P5 (VaR)", "#c0392b"),
                (mc["p50"], "P50", "#27ae60"),
            ]:
                fig_hist.add_vline(
                    x=pval / 1e6, line_width=2, line_dash="dash",
                    line_color=color, annotation_text=pname,
                    annotation_position="top right"
                )
            fig_hist.add_vline(x=0, line_width=1.5, line_color="black",
                               annotation_text="VAN=0", annotation_position="top left")
            fig_hist.update_layout(
                xaxis_title="VAN (M€)", yaxis_title="Frecuencia",
                height=380, showlegend=False,
            )
            st.plotly_chart(fig_hist, use_container_width=True)

        with col_box:
            st.subheader("Box Plot de escenarios")
            fig_box = go.Figure()
            fig_box.add_trace(go.Box(
                y=mc["npvs"] / 1e6,
                name="VAN simulado",
                boxpoints="outliers",
                marker_color="#2980b9",
                line_color="#003366",
            ))
            fig_box.add_hline(y=0, line_dash="dash", line_color="red",
                              annotation_text="Break-even")
            fig_box.update_layout(
                yaxis_title="VAN (M€)", height=380, showlegend=False
            )
            st.plotly_chart(fig_box, use_container_width=True)

        st.info(f"""
        **Interpretación:**
        Con los parámetros actuales, hay una probabilidad del **{mc['prob_positive']*100:.1f}%** de que el proyecto genere valor positivo.
        En el peor 5% de escenarios (VaR 95%), el VAN no supera los **{mc['var_95']/1e6:.2f} M€**.
        La mediana de los escenarios es **{mc['p50']/1e6:.2f} M€**.
        """)

        # Recomendación automática con riesgo (screening)
        st.divider()
        st.subheader("Recomendación automática (screening)")

        prob = mc["prob_positive"]
        mean_npv = mc["mean"]
        var95 = mc["var_95"]

        if prob >= 0.70 and var95 > -0.10 * p_in.capex:
            verdict = "APTO para avanzar (screening positivo)"
            color = "🟢"
            rationale = "Alta probabilidad de creación de valor y downside razonable."
        elif prob >= 0.50 and mean_npv > 0:
            verdict = "DUDOSO (necesita due diligence / mejorar supuestos)"
            color = "🟠"
            rationale = "Rentabilidad esperada positiva, pero con riesgo relevante."
        else:
            verdict = "NO APTO (screening negativo)"
            color = "🔴"
            rationale = "Baja probabilidad de VAN positivo o riesgo de pérdidas elevado."

        st.success(
            f"{color} **{verdict}**\n\n"
            f"- Prob(VAN > 0): **{prob*100:.1f}%**\n"
            f"- VAN esperado (media): **{mean_npv/1e6:.2f} M€**\n"
            f"- VaR 95% (P5): **{var95/1e6:.2f} M€**\n\n"
            f"**Interpretación:** {rationale}"
        )

    else:
        st.info("Pulsa **Ejecutar Monte Carlo** para calcular la distribución de riesgo del proyecto.")

# ---------------------------------------------------------------------------
# TAB 4 — Metodología
# ---------------------------------------------------------------------------
with tab_method:
    st.header("Metodología y fuentes")

    st.subheader("Flujos de caja")
    st.markdown("""
**Flujo unlevered (FCFF):** Se construye a partir del EBIT neto de impuestos
más la amortización contable, sin considerar la estructura de deuda.
Se descuenta al **WACC** para obtener el valor del activo (Enterprise Value).

**Flujo levered (FCFE):** Descuenta los intereses reales del calendario
de amortización del préstamo (cuota constante tipo francés), el principal
y añade el escudo fiscal de intereses. Representa el flujo disponible
para el accionista.
    """)

    st.divider()

    st.subheader("NPV / VAN")
    st.latex(r"VAN = -I_0 + \sum_{t=1}^{N} \frac{CF_t}{(1+WACC)^t}")
    st.markdown("Donde $I_0$ es el CAPEX inicial y $CF_t$ los flujos de caja unlevered.")

    st.divider()

    st.subheader("LCOE")
    st.markdown("Coste nivelado de energía calculado como:")
    st.latex(r"LCOE = \frac{CAPEX + \sum_{t} \frac{OPEX_t}{(1+WACC)^t}}{\sum_{t} \frac{MWh_t}{(1+WACC)^t}}")
    st.markdown("Refleja el precio mínimo al que el proyecto debe vender energía para recuperar todos sus costes a la tasa de descuento dada.")
    st.divider()

    st.subheader("Monte Carlo")
    st.markdown("Se simulan 5 variables simultáneamente con distribución normal:")
    st.table({
        "Variable": ["Precio de venta", "Producción anual", "CAPEX", "OPEX fijo", "WACC"],
        "Desviación estándar asumida": ["±15%", "±8%", "±10%", "±10%", "±5% (relativo)"],
    })

    st.divider()

    st.subheader("Fuentes de datos de costes")
    st.table({
        "País": ["España", "Alemania", "Francia"],
        "CAPEX Solar (€/kW)": ["750 — BNEF Solar PV 2024", "870 — Fraunhofer ISE 2024", "810 — ADEME 2024"],
        "CAPEX Eólica (€/kW)": ["1.250 — IRENA 2023", "1.480 — IRENA 2023", "1.380 — IRENA 2023"],
        "CAPEX Baterías (€/kWh)": ["350 — BloombergNEF 2024", "400 — BloombergNEF 2024", "380 — BloombergNEF 2024"],
    })
    st.markdown("""
- Datos de OPEX: IRENA O&M Cost Report 2023
- Factores de capacidad: ENTSO-E / REE Historical Generation 2023
- Precios de referencia fallback: OMIE / ENTSO-E Day-Ahead 2024
    """)

    st.divider()

    st.warning(
        "**Aviso legal (proyecto personal):** Esta herramienta es un proyecto personal con fines educativos y de exploración. "
        "Los resultados son únicamente orientativos y no constituyen asesoramiento financiero ni una recomendación de inversión. "
        "Antes de tomar cualquier decisión o comprometer capital, contrasta la información con fuentes oficiales "
        "y/o asesórate con un profesional independiente."
    )