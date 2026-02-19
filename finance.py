"""
finance.py — Motor financiero para Energy Advisor
"""

import numpy as np
import numpy_financial as npf
from pydantic import BaseModel, Field
from typing import Optional
import requests


# ---------------------------------------------------------------------------
# Modelo de datos de entrada
# ---------------------------------------------------------------------------

class ProjectInputs(BaseModel):
    # Proyecto
    years: int = Field(gt=0, description="Vida útil del proyecto en años")
    capex: float = Field(gt=0, description="Inversión inicial total (€)")
    annual_mwh: float = Field(gt=0, description="Producción anual año 1 (MWh)")
    price_eur_mwh: float = Field(gt=0, description="Precio de venta año 1 (€/MWh)")

    # Costes operativos
    opex_fixed: float = Field(ge=0, description="OPEX fijo anual (€/año)")
    opex_var_eur_mwh: float = Field(ge=0, description="OPEX variable (€/MWh)")

    # Degradación e inflación
    degradation: float = Field(ge=0, description="Degradación anual de producción (fracción)")
    inflation: float = Field(ge=0, description="Inflación anual (fracción)")
    price_degradation: float = Field(default=0.0, ge=0,
                                     description="Caída anual del precio de mercado (fracción)")

    # Fiscalidad
    tax_rate: float = Field(ge=0, description="Tipo impositivo efectivo (fracción)")
    depreciation_years: Optional[int] = Field(default=None, gt=0,
                                               description="Años de amortización fiscal (None = vida útil)")

    # Financiación
    wacc: float = Field(gt=0, description="WACC (fracción)")
    debt_ratio: float = Field(ge=0, le=1.0, description="% de deuda sobre CAPEX")
    interest_rate: float = Field(ge=0, description="Tipo de interés nominal (fracción)")
    debt_years: Optional[int] = Field(default=None, gt=0,
                                      description="Plazo de la deuda en años (None = vida útil)")

    class Config:
        validate_assignment = True


# ---------------------------------------------------------------------------
# Utilidad: precio de mercado — OMIE (ES/PT) con fallback histórico
# ---------------------------------------------------------------------------

# Fallback: precios medios anuales de referencia OMIE/ENTSO-E 2024
_MARKET_REFERENCE = {
    "ES": 58.4,
    "DE": 78.2,
    "FR": 62.1,
    "PT": 57.9,
}


def _fetch_omie_daily_price(country_code: str) -> float | None:
    """
    Descarga el fichero de precios marginales del mercado diario de OMIE.
    Formato: marginalpdbc_YYYYMMDD.1 — CSV separado por punto y coma.
    Columnas: Hora;Fecha;Precio España (€/MWh);Precio Portugal (€/MWh)
    Devuelve el precio medio del día o None si falla.
    """
    from datetime import datetime, timedelta

    # OMIE publica el precio del día D antes de las 14:00 del día D-1.
    # Para garantizar datos disponibles, pedimos el día de ayer.
    target = datetime.now() - timedelta(days=1)
    date_str = target.strftime("%Y%m%d")
    year_str = target.strftime("%Y")
    month_str = target.strftime("%Y_%m")

    url = (
        f"https://www.omie.es/es/file-access-list"
        f"?parents%5B0%5D=/&parents%5B1%5D=/{year_str}"
        f"&parents%5B2%5D=/{month_str}"
        f"&elem=marginalpdbc_{date_str}.1"
    )

    try:
        resp = requests.get(url, timeout=8)
        resp.raise_for_status()
        # El fichero tiene una cabecera de 2 líneas y luego datos hora a hora
        lines = resp.text.strip().splitlines()
        prices = []
        col = 2 if country_code in ("ES", "PT") else 2  # col 2=ES, col 3=PT
        col_idx = 2 if country_code == "ES" else 3
        for line in lines[2:]:  # Saltar cabecera
            parts = line.split(";")
            if len(parts) > col_idx:
                try:
                    val = float(parts[col_idx].replace(",", "."))
                    if val > 0:
                        prices.append(val)
                except ValueError:
                    continue
        if prices:
            return round(sum(prices) / len(prices), 2)
    except Exception:
        pass
    return None


def _fetch_entsoe_daily_price(country_code: str, token: str) -> float | None:
    """
    Descarga precios Day-Ahead de ENTSO-E Transparency Platform.
    Requiere token gratuito de https://transparency.entsoe.eu/
    Útil para Alemania (DE) y Francia (FR) que no están en OMIE.
    """
    from datetime import datetime, timedelta

    AREA_CODES = {
        "DE": "10Y1001A1001A83F",
        "FR": "10YFR-RTE------C",
        "ES": "10YES-REE------0",
        "PT": "10YPT-REN------W",
    }
    area = AREA_CODES.get(country_code)
    if not area or not token:
        return None

    now = datetime.utcnow()
    period_start = (now - timedelta(days=1)).strftime("%Y%m%d0000")
    period_end = now.strftime("%Y%m%d0000")

    url = (
        f"https://web-api.tp.entsoe.eu/api"
        f"?securityToken={token}"
        f"&documentType=A44"
        f"&in_Domain={area}"
        f"&out_Domain={area}"
        f"&periodStart={period_start}"
        f"&periodEnd={period_end}"
    )

    try:
        import xml.etree.ElementTree as ET
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        root = ET.fromstring(resp.text)
        ns = {"ns": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"}
        points = root.findall(".//ns:Point/ns:price.amount", ns)
        prices = [float(p.text) for p in points if p.text]
        if prices:
            return round(sum(prices) / len(prices), 2)
    except Exception:
        pass
    return None


def get_market_price_api(country_code: str = "ES", entsoe_token: str = "") -> tuple[float, bool]:
    """
    Obtiene el precio medio diario del mercado eléctrico.

    Para ES y PT: usa la API pública de OMIE (sin token).
    Para DE y FR: usa ENTSO-E si se proporciona token, si no usa fallback.

    Devuelve (precio, is_live) donde is_live=True si el dato es en tiempo real.
    """
    price = None
    is_live = False

    if country_code in ("ES", "PT"):
        price = _fetch_omie_daily_price(country_code)
        if price is not None:
            is_live = True

    if price is None and entsoe_token:
        price = _fetch_entsoe_daily_price(country_code, entsoe_token)
        if price is not None:
            is_live = True

    if price is None:
        price = _MARKET_REFERENCE.get(country_code, 65.0)
        is_live = False

    return price, is_live

# ---------------------------------------------------------------------------
# Motor de cálculo principal
# ---------------------------------------------------------------------------

def _build_cashflows(inputs: ProjectInputs):
    """
    Construye los flujos de caja anuales unlevered y levered.
    Devuelve un dict con arrays año a año.
    """
    t = np.arange(1, inputs.years + 1)

    # --- Producción e ingresos ---
    mwh_t = inputs.annual_mwh * ((1 - inputs.degradation) ** (t - 1))
    price_t = inputs.price_eur_mwh * (
        (1 + inputs.inflation) ** (t - 1) *
        (1 - inputs.price_degradation) ** (t - 1)
    )
    revenue_t = mwh_t * price_t

    # --- OPEX con inflación ---
    opex_t = (
        inputs.opex_fixed +
        inputs.annual_mwh * inputs.opex_var_eur_mwh
    ) * ((1 + inputs.inflation) ** (t - 1))

    # --- Amortización fiscal ---
    dep_years = inputs.depreciation_years or inputs.years
    dep_t = np.where(t <= dep_years, inputs.capex / dep_years, 0.0)

    # --- EBIT y flujo unlevered ---
    ebit_t = revenue_t - opex_t - dep_t
    taxes_t = np.maximum(0, ebit_t) * inputs.tax_rate
    cf_unlevered = ebit_t - taxes_t + dep_t  # NOPAT + D&A

    # --- Debt scheduling: préstamo amortizable (cuota constante) ---
    debt_amt = inputs.capex * inputs.debt_ratio
    d_years = inputs.debt_years or inputs.years
    interest_t = np.zeros(inputs.years)
    principal_t = np.zeros(inputs.years)

    if debt_amt > 0 and d_years > 0:
        # Cuota anual constante (tipo francés)
        r = inputs.interest_rate
        if r > 0:
            payment = debt_amt * r / (1 - (1 + r) ** (-d_years))
        else:
            payment = debt_amt / d_years
        balance = debt_amt
        for i in range(min(d_years, inputs.years)):
            int_i = balance * r
            princ_i = payment - int_i
            interest_t[i] = int_i
            principal_t[i] = princ_i
            balance = max(0, balance - princ_i)

    # Escudo fiscal de intereses
    tax_shield_t = interest_t * inputs.tax_rate
    cf_levered = cf_unlevered - interest_t - principal_t + tax_shield_t

    return {
        "t": t,
        "mwh_t": mwh_t,
        "price_t": price_t,
        "revenue_t": revenue_t,
        "opex_t": opex_t,
        "dep_t": dep_t,
        "ebit_t": ebit_t,
        "taxes_t": taxes_t,
        "cf_unlevered": cf_unlevered,
        "interest_t": interest_t,
        "principal_t": principal_t,
        "tax_shield_t": tax_shield_t,
        "cf_levered": cf_levered,
        "debt_amt": debt_amt,
    }


def calculate_metrics(inputs: ProjectInputs) -> dict:
    """
    Calcula NPV, IRR, LCOE y Payback a partir de un objeto ProjectInputs.
    No muta el objeto de entrada.
    """
    flows = _build_cashflows(inputs)
    t = flows["t"]

    # --- Flujos para NPV/IRR (unlevered: equity = CAPEX total) ---
    cf_unlevered_total = np.insert(flows["cf_unlevered"], 0, -inputs.capex)

    # --- Flujos levered (equity = CAPEX - deuda) ---
    equity_inv = inputs.capex - flows["debt_amt"]
    cf_levered_total = np.insert(flows["cf_levered"], 0, -equity_inv)

    # --- NPV unlevered ---
    npv = float(npf.npv(inputs.wacc, cf_unlevered_total))

    # --- IRR (unlevered) ---
    try:
        irr = float(npf.irr(cf_unlevered_total))
        if np.isnan(irr):
            irr = None
    except Exception:
        irr = None

    # --- LCOE: coste nivelado sobre activos (pre-tax WACC) ---
    df = (1 + inputs.wacc) ** t
    present_opex = np.sum(flows["opex_t"] / df)
    present_mwh = np.sum(flows["mwh_t"] / df)
    lcoe = (inputs.capex + present_opex) / present_mwh if present_mwh > 0 else None

    # --- Payback simple (flujos nominales no descontados) ---
    cum = np.cumsum(cf_unlevered_total)
    payback = None
    pos_idx = np.where(cum >= 0)[0]
    if len(pos_idx) > 0:
        idx = pos_idx[0]
        if idx == 0:
            payback = 0.0
        else:
            payback = idx - 1 + (-cum[idx - 1] / (cum[idx] - cum[idx - 1]))

    # --- Payback descontado ---
    disc_cf = np.insert(flows["cf_unlevered"] / df, 0, -inputs.capex)
    cum_disc = np.cumsum(disc_cf)
    discounted_payback = None
    pos_idx_d = np.where(cum_disc >= 0)[0]
    if len(pos_idx_d) > 0:
        idx_d = pos_idx_d[0]
        if idx_d == 0:
            discounted_payback = 0.0
        else:
            discounted_payback = idx_d - 1 + (
                -cum_disc[idx_d - 1] / (cum_disc[idx_d] - cum_disc[idx_d - 1])
            )

    return {
        "npv": npv,
        "irr": irr,
        "lcoe": lcoe,
        "payback": payback,
        "discounted_payback": discounted_payback,
        "cashflows": cf_unlevered_total,
        "levered_cf": cf_levered_total,
        "flows": flows,
    }


# ---------------------------------------------------------------------------
# Análisis de sensibilidad multivariable (sin mutación)
# ---------------------------------------------------------------------------

SENSITIVITY_PARAMS = {
    "Precio (€/MWh)": "price_eur_mwh",
    "CAPEX (€)": "capex",
    "Producción (MWh)": "annual_mwh",
    "WACC (%)": "wacc",
    "OPEX Fijo (€)": "opex_fixed",
    "Inflación (%)": "inflation",
}


def sensitivity_analysis(
    base_inputs: ProjectInputs,
    deltas: tuple = (-0.20, -0.10, 0.0, 0.10, 0.20),
) -> dict:
    """
    Análisis tornado multivariable.
    Devuelve un dict {param_label: {delta: npv_delta}} sin mutar base_inputs.
    """
    base_npv = calculate_metrics(base_inputs)["npv"]
    results = {}

    for label, attr in SENSITIVITY_PARAMS.items():
        orig = getattr(base_inputs, attr)
        row = {}
        for d in deltas:
            new_val = orig * (1 + d)
            modified = base_inputs.model_copy(update={attr: new_val})
            row[d] = calculate_metrics(modified)["npv"] - base_npv
        results[label] = row

    return results


# ---------------------------------------------------------------------------
# Simulación Monte Carlo
# ---------------------------------------------------------------------------

def monte_carlo(
    base_inputs: ProjectInputs,
    n_simulations: int = 5000,
    seed: int = 42,
) -> dict:
    """
    Simula la distribución del NPV variando precio, producción y CAPEX
    con distribuciones normales centradas en los valores base.
    Devuelve percentiles, VaR y la distribución completa.
    """
    rng = np.random.default_rng(seed)
    npvs = np.empty(n_simulations)

    # Desviaciones estándar relativas asumidas
    sigma = {
        "price_eur_mwh": 0.15,   # ±15% volatilidad precio
        "annual_mwh": 0.08,      # ±8% incertidumbre producción
        "capex": 0.10,           # ±10% incertidumbre CAPEX
        "opex_fixed": 0.10,      # ±10% OPEX
        "wacc": 0.05,            # ±5% relativo en WACC
    }

    base_vals = {k: getattr(base_inputs, k) for k in sigma}

    for i in range(n_simulations):
        sampled = {
            k: max(1e-6, rng.normal(v, v * sigma[k]))
            for k, v in base_vals.items()
        }
        sim_inputs = base_inputs.model_copy(update=sampled)
        npvs[i] = calculate_metrics(sim_inputs)["npv"]

    p5, p25, p50, p75, p95 = np.percentile(npvs, [5, 25, 50, 75, 95])
    prob_positive = float(np.mean(npvs > 0))

    return {
        "npvs": npvs,
        "p5": p5,
        "p25": p25,
        "p50": p50,
        "p75": p75,
        "p95": p95,
        "mean": float(np.mean(npvs)),
        "std": float(np.std(npvs)),
        "prob_positive": prob_positive,
        "var_95": p5,  # Value at Risk al 95%
    }