# Energy Advisor

> Herramienta interactiva de modelización financiera para evaluar inversiones en energías renovables mediante flujos de caja descontados.

Desarrollada para explorar cómo el análisis de financiación de proyectos puede hacerse interactivo y accesible — sin Excel.

![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-1.32-FF4B4B?logo=streamlit&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Qué hace

- Calcula **VAN**, **TIR**, **LCOE** y **Payback** (simple y descontado)
- Modela flujos de caja apalancados y no apalancados con un calendario real de amortización de deuda (anualidad francesa)
- Ejecuta **simulación de Monte Carlo** (hasta 10.000 escenarios) — distribución del VAN, VaR al 95%, probabilidad de VAN positivo
- **Análisis de sensibilidad Tornado** sobre seis variables clave (±10% / ±20%)
- Obtiene **precios de electricidad en tiempo real** desde OMIE (España/Portugal, sin token) y ENTSO-E (Alemania/Francia, token gratuito)
- Genera un **Informe de Inversión en PDF** — informe de screening listo para compartir
- **Veredicto de screening** (Aprobado / Revisión / Rechazado) que combina comprobaciones deterministas y basadas en riesgo

---

## Capturas de pantalla

**Panel lateral — KPIs y configuración del proyecto**
![Sidebar](screenshots/01_sidebar_kpis.png)

**Resultados — VAN, TIR, LCOE y gráficos de flujo de caja**
![Results](screenshots/02_results.png)

**Análisis de sensibilidad — Gráfico Tornado y benchmark de LCOE**
![Sensitivity](screenshots/03_sensitivity_pdf.png)

**Riesgo — Simulación de Monte Carlo y veredicto de screening**
![Monte Carlo](screenshots/04_monte_carlo.png)

**Metodología — fórmulas y fuentes de datos**
![Methodology](screenshots/05_methodology.png)

---

## Stack tecnológico

| Capa | Librería |
|---|---|
| Interfaz de usuario | Streamlit 1.32 |
| Validación de datos | Pydantic v2 |
| Computación numérica | NumPy, numpy-financial |
| Manipulación de datos | Pandas |
| Visualización | Plotly |
| Generación de PDF | ReportLab |
| Cliente HTTP | requests |

---

## Ejecución local

```bash
git clone https://github.com/mcamposcarneros/Investment-Decision-Support-Tool.git
cd energy-advisor
pip install -r requirements.txt
streamlit run app.py
```

---

## Estructura del proyecto

```
├── app.py           # Interfaz Streamlit
├── finance.py       # Motor financiero (DCF, Monte Carlo, sensibilidad, APIs de mercado)
├── requirements.txt
└── README.md
```

---

## Precios de mercado en tiempo real

| Mercado | Fuente | Autenticación |
|---|---|---|
| España / Portugal | Archivos públicos Day-Ahead de OMIE | No requerida |
| Alemania / Francia | Plataforma de Transparencia ENTSO-E (A44) | Token gratuito |

Si la conexión en tiempo real falla, la aplicación utiliza precios de referencia del promedio anual 2024 y muestra un indicador de estado: **En vivo** / **Ref.** / **Manual**.

Para conectar ENTSO-E: regístrate en [transparency.entsoe.eu](https://transparency.entsoe.eu/), genera un token en *Mi cuenta → Token de seguridad* e introdúcelo en el panel lateral de la aplicación.

---

## Notas metodológicas

- El LCOE sigue la metodología de WACC pre-impuestos de la AIE/IRENA
- La deuda se modela como un calendario de pagos constantes (anualidad francesa) con carga de intereses decreciente
- El escudo fiscal de los intereses se añade explícitamente al flujo de caja apalancado
- Monte Carlo muestrea simultáneamente precio, producción, CAPEX, OPEX y WACC a partir de distribuciones normales independientes
- El veredicto de screening combina una comprobación determinista (VAN > 0 y TIR > WACC) con una comprobación basada en riesgo (P(VAN > 0) ≥ 70% y VaR 95% > −10% del CAPEX)

---

## Fuentes de datos

| Elemento | Fuente |
|---|---|
| CAPEX Solar FV | BNEF Solar PV Cost Report 2024 |
| CAPEX Eólico | IRENA Renewable Power Generation Costs 2023 |
| CAPEX Baterías | BloombergNEF BESS Outlook 2024 |
| OPEX O&M | IRENA O&M Cost Report 2023 |
| Factores de capacidad | ENTSO-E / REE Generación Histórica 2023 |
| Precios de referencia | OMIE / ENTSO-E Day-Ahead promedio anual 2024 |

### Benchmarks de CAPEX por defecto según país

| País | Solar FV (€/kW) | Eólico (€/kW) | Batería BESS (€/kWh) |
|---|---|---|---|
| España | 750 — BNEF 2024 | 1.250 — IRENA 2023 | 350 — BloombergNEF 2024 |
| Alemania | 870 — Fraunhofer ISE 2024 | 1.480 — IRENA 2023 | 400 — BloombergNEF 2024 |
| Francia | 810 — ADEME 2024 | 1.380 — IRENA 2023 | 380 — BloombergNEF 2024 |

---

## Aviso legal

Este es un proyecto personal desarrollado con fines de aprendizaje y experimentación. No está destinado a análisis de inversiones reales ni a la toma de decisiones financieras.
