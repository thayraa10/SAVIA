
import streamlit as st
import pandas as pd
import numpy as np
import math
import io
import re
import unicodedata
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta
import pytz
import gc
import streamlit.components.v1 as _components
from streamlit_autorefresh import st_autorefresh
import requests as _requests
from scipy.stats import gamma as gamma_dist, norm as _norm_inv
import pulp as _pulp

try:
    from gurobipy import *
    _GUROBI_OK = True
except Exception:
    _GUROBI_OK = False
import calendar
from dateutil.relativedelta import relativedelta

st.set_page_config(page_title="SAVIA — Abastecimiento de Medi"
                              "camentos", layout="wide")

# ── Keep-alive triple: WebSocket + HTTP browser + HTTP server-side ───────────

# 1) Autorefresh cada 4 min → mantiene WebSocket activo sin interrumpir cargas de archivos.
st_autorefresh(interval=4 * 60 * 1000, limit=None, key="keepalive")

# 2) Ping HTTP desde el browser cada 2.5 min (funciona mientras el tab está abierto).
_components.html("""
<script>
(function ping() {
    fetch('/_stcore/health').catch(function(){});
    setTimeout(ping, 150000);
})();
</script>
""", height=0)

# 3) Hilo de fondo server-side: hace ping HTTP a la propia app cada 90 segundos.
#    A diferencia de los pings del browser, este corre aunque nadie tenga el tab abierto.
#    Previene que el event loop de Tornado quede completamente inactivo y falle el
#    health-check con EOF cuando las sesiones huérfanas expiran a los ~5 minutos.
@st.cache_resource
def _iniciar_keepalive_server():
    import threading, urllib.request, time
    def _worker():
        time.sleep(30)           # dar tiempo a que Streamlit termine de arrancar
        while True:
            try:
                urllib.request.urlopen(
                    "http://localhost:8501/_stcore/health", timeout=5
                )
            except Exception:
                pass
            time.sleep(90)       # ping cada 90 segundos
    hilo = threading.Thread(target=_worker, daemon=True)
    hilo.start()
    return id(hilo)              # int serializable → Streamlit no se queja

_iniciar_keepalive_server()

# 4) GC explícito en cada rerun para limpiar objetos de sesiones huérfanas
#    de forma incremental en lugar de dejar que se acumulen 5 minutos.
gc.collect()

st.markdown("""
<style>
html, body { font-family: sans-serif; } .stApp { background-color: #f0f4f8; } /* fondo gris */

[data-testid="stSidebar"] { background: #0a0f2c; } /* fondo azul oscuro */
[data-testid="stSidebar"] * { color: #f0f4f8 !important; }
/* botones dentro del sidebar mantienen texto blanco */
[data-testid="stSidebar"] .stButton > button { color: white !important; }
/* texto negro solo dentro de los cuadros de input blancos */
[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stNumberInput input,
[data-testid="stSidebar"] .stDateInput input {
    background: white !important; border: 1px solid #334155 !important;
    color: #0f172a !important; border-radius: 8px !important;
}
/* placeholder de los inputs también en tono visible pero diferenciado */
[data-testid="stSidebar"] .stTextInput input::placeholder,
[data-testid="stSidebar"] .stNumberInput input::placeholder,
[data-testid="stSidebar"] .stDateInput input::placeholder {
    color: #64748b !important;
}
/* select / dropdown: fondo blanco y texto negro en todos sus descendientes */
[data-testid="stSidebar"] [data-baseweb="select"],
[data-testid="stSidebar"] [data-baseweb="select"] * {
    background: white !important; color: #0f172a !important;
}
/* time input */
[data-testid="stSidebar"] [data-testid="stTimeInput"] input {
    background: white !important; color: #0f172a !important;
    border: 1px solid #334155 !important; border-radius: 8px !important;
}
/* Días semana en español */
[data-testid="stDateInput"] abbr[title="Monday"]    { visibility:hidden; } [data-testid="stDateInput"] abbr[title="Monday"]::after    { content:"Lu"; visibility:visible; }
[data-testid="stDateInput"] abbr[title="Tuesday"]   { visibility:hidden; } [data-testid="stDateInput"] abbr[title="Tuesday"]::after   { content:"Ma"; visibility:visible; }
[data-testid="stDateInput"] abbr[title="Wednesday"] { visibility:hidden; } [data-testid="stDateInput"] abbr[title="Wednesday"]::after { content:"Mi"; visibility:visible; }
[data-testid="stDateInput"] abbr[title="Thursday"]  { visibility:hidden; } [data-testid="stDateInput"] abbr[title="Thursday"]::after  { content:"Ju"; visibility:visible; }
[data-testid="stDateInput"] abbr[title="Friday"]    { visibility:hidden; } [data-testid="stDateInput"] abbr[title="Friday"]::after    { content:"Vi"; visibility:visible; }
[data-testid="stDateInput"] abbr[title="Saturday"]  { visibility:hidden; } [data-testid="stDateInput"] abbr[title="Saturday"]::after  { content:"Sá"; visibility:visible; }
[data-testid="stDateInput"] abbr[title="Sunday"]    { visibility:hidden; } [data-testid="stDateInput"] abbr[title="Sunday"]::after    { content:"Do"; visibility:visible; }
[data-testid="stSidebar"] hr { border-color: #334155 !important; }

/* ── Tabs ────────────────────────────────────────────────── */
.stTabs [data-baseweb="tab-list"] {
    background: white; border-radius: 12px; padding: 4px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.08); gap: 4px;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important; font-weight: 500;
    color: #64748b !important; padding: 8px 20px !important;
}
.stTabs [aria-selected="true"] {
    background: #2563eb !important; color: white !important;
}

/* ── Métricas ────────────────────────────────────────────── */
[data-testid="metric-container"] {
    background: white; border-radius: 12px; padding: 16px 20px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.07);
    border-left: 4px solid #2563eb;
}
[data-testid="stMetricLabel"] { font-size: 0.78rem !important; color: #64748b !important; font-weight: 500; }
[data-testid="stMetricValue"] { font-size: 1.4rem !important; color: #0f172a !important; font-weight: 700; }

/* ── Expanders ───────────────────────────────────────────── */
[data-testid="stExpander"] {
    background: white; border-radius: 12px !important;
    border: 1px solid #e2e8f0 !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    margin-bottom: 12px;
}
[data-testid="stExpander"] summary {
    font-weight: 600 !important; color: #0f172a !important;
    padding: 14px 18px !important;
}
/* Expanders dentro del sidebar: todo el contenido en negro */
[data-testid="stSidebar"] [data-testid="stExpander"],
[data-testid="stSidebar"] [data-testid="stExpander"] *,
[data-testid="stSidebar"] [data-testid="stExpander"] summary,
[data-testid="stSidebar"] [data-testid="stExpander"] summary *,
[data-testid="stSidebar"] [data-testid="stExpander"] p,
[data-testid="stSidebar"] [data-testid="stExpander"] span,
[data-testid="stSidebar"] [data-testid="stExpander"] small {
    color: #0f172a !important;
}

/* ── Botones +/- number input ────────────────────────────── */
[data-testid="stNumberInput"] button { background: royalblue !important; color: white !important; border: none !important; }

/* ── Dataframes ──────────────────────────────────────────── */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

/* ── Botones ─────────────────────────────────────────────── */
.stButton > button, [data-testid="stFileUploaderDropzone"] button {
    border-radius: 8px !important; font-weight: 500 !important;
    background-color: royalblue !important; color: white !important;
    border: none !important;
}

/* ── Traducción uploader ─────────────────────────────────── */
[data-testid="stFileUploaderDropzoneInstructions"] span { display: none; }
[data-testid="stFileUploaderDropzoneInstructions"]::before { content: "Arrastra y suelta el archivo aquí"; display: block; }
[data-testid="stFileUploaderDropzoneInstructions"] small { display: none; }
[data-testid="stFileUploaderDropzoneInstructions"]::after { content: "Límite 200MB por archivo • XLSX, CSV"; display: block; font-size: 0.8rem; color: gray; }
[data-testid="stFileUploaderDropzone"] button { color: transparent !important; position: relative; width: 100% !important; }
[data-testid="stFileUploaderDropzone"] button::after { content: "Buscar archivo"; color: white; position: absolute; left: 50%; transform: translateX(-50%); font-size: 14px; }

/* ── Alertas ─────────────────────────────────────────────── */
.stAlert { border-radius: 10px !important; }

/* ── Divider ─────────────────────────────────────────────── */
hr { border-color: #e2e8f0 !important; }

/* ── Header hero ─────────────────────────────────────────── */
.hero-banner {
    background: #0a0f2c;
    border-radius: 16px; padding: 48px 36px; margin-bottom: 24px;
    color: white; text-align: center;
}
.hero-banner h1 { font-size: 3.5rem; font-weight: 800; margin: 0; color: white; }
.hero-banner p  { font-size: 1.1rem; color: #93c5fd; margin: 8px 0 0; }

/* ── Tarjeta de sección ──────────────────────────────────── */
.section-card {
    background: white; border-radius: 14px; padding: 24px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.08); margin-bottom: 20px;
}

/* ── Badge de estado ─────────────────────────────────────── */
.badge-red    { background:lightpink;   color:red;    padding:3px 10px; border-radius:99px; font-size:0.75rem; font-weight:600; }
.badge-orange { background:moccasin;    color:darkorange; padding:3px 10px; border-radius:99px; font-size:0.75rem; font-weight:600; }
.badge-green  { background:lightgreen;  color:green;  padding:3px 10px; border-radius:99px; font-size:0.75rem; font-weight:600; }
.badge-blue   { background:lightblue;   color:blue;   padding:3px 10px; border-radius:99px; font-size:0.75rem; font-weight:600; }
.badge-gray   { background:lightgray;   color:dimgray; padding:3px 10px; border-radius:99px; font-size:0.75rem; font-weight:600; }
</style>
""", unsafe_allow_html=True)

def _m(n) -> str:
    """Formatea un número entero con punto como separador de miles (estilo Chile).
    Ej.: 1285 → '1.285', 37842 → '37.842'.
    """
    try:
        return f"{int(round(float(n))):,}".replace(",", ".")
    except Exception:
        return str(n)

# ──────────────────────────────────────────────────────────────────────────────
def _safe_df(df):
    """Sanitiza un DataFrame para st.dataframe():
    - Normaliza nombres de columna a str.
    - Convierte a str SOLO las columnas object que mezclan tipos Python
      (e.g., ints y strings en la misma columna), que son las que fallan
      en PyArrow. Las columnas que ya son uniformemente str se dejan intactas
      para no inflar el tamaño del mensaje WebSocket.
    """
    df = df.copy()
    df.columns = [str(c) for c in df.columns]
    for col in df.columns:
        if df[col].dtype == object:
            muestra = df[col].dropna().head(200)
            if len(muestra) == 0:
                continue
            if any(not isinstance(v, str) for v in muestra):
                df[col] = df[col].astype(str)
    return df

# ──────────────────────────────────────────────────────────────────────────────
def _ayuda(texto: str, color: str = "#EBF8FF", borde: str = "#3182CE"):
    """Caja azul de ayuda contextual para explicar una sección o dato."""
    return (
        f'<div style="background:{color};border-left:4px solid {borde};border-radius:6px;'
        f'padding:10px 14px;margin:6px 0 12px 0;font-size:0.80rem;color:#2D3748;line-height:1.55">'
        f'{texto}</div>'
    )

# ──────────────────────────────────────────────────────────────────────────────

def _sin_tildes(texto: str) -> str:
    """Devuelve el texto en minúsculas y sin tildes/diacríticos.
    Permite comparar 'código' con 'codigo', 'CÓDIGO', etc."""
    nfkd = unicodedata.normalize("NFKD", str(texto))
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def encontrar_columna(df, palabras_clave, ya_usadas):
    if df is None:
        return None
    for columna in df.columns:
        if columna in ya_usadas:
            continue
        nombre = _sin_tildes(str(columna)).replace("_", " ").replace("-", " ")
        for palabra in palabras_clave:
            if _sin_tildes(palabra) in nombre:
                ya_usadas.add(columna)
                return columna
    return None

# ──────────────────────────────────────────────────────────────────────────────
def calcular_estado(días):
    if pd.isna(días): return "Sin fecha"
    if días < 0:      return "VENCIDO"
    if días <= 30:    return "CRITICO"
    if días <= 90:    return "ADVERTENCIA"
    return "NORMAL"

# ──────────────────────────────────────────────────────────────────────────────
# FEFO HELPERS (First Expired, First Out)
# Gestión de lotes perecibles: purga, consumo y alta de lotes ordenados por
# fecha de vencimiento. Tomados directamente del notebook de referencia.
# ──────────────────────────────────────────────────────────────────────────────
def oh_total(batches):
    """Inventario en mano como suma de todos los lotes vigentes."""
    return sum(b[0] for b in batches)

def purgar_vencidos(batches, t_now):
    """Elimina lotes vencidos. Devuelve (batches_vigentes, unidades_vencidas)."""
    vencidas = sum(b[0] for b in batches if b[1] <= t_now)
    vigentes  = [b for b in batches if b[1] > t_now]
    return vigentes, vencidas

def consumir_demanda(batches, cantidad):
    """Descuenta `cantidad` unidades usando política FEFO."""
    restante = cantidad
    while restante > 0 and batches:
        if batches[0][0] <= restante:
            restante -= batches[0][0]
            batches.pop(0)
        else:
            batches[0][0] -= restante
            restante = 0
    return batches

def agregar_lote(batches, cantidad, t_arribo, sl_dias):
    """Agrega un lote recibido, insertado ordenado por tiempo de vencimiento (FEFO)."""
    vencimiento = t_arribo + sl_dias
    batches.append([cantidad, vencimiento])
    batches.sort(key=lambda x: x[1])
    return batches

# ──────────────────────────────────────────────────────────────────────────────
# PARÁMETROS DE INVENTARIO — fórmulas exactas del notebook de referencia.
# ──────────────────────────────────────────────────────────────────────────────
def calcular_politicas(Media, V, OC, HC, LT, R, Z=1.645):
    V      = max(V, 0.001)
    sigma  = V ** 0.5
    R_     = max(R, 0.001)
    LT_ef  = min(LT, LT - (math.trunc(LT / R_) * R_))             # LT mod R (para referencia)
    # Período de protección: cuando LT >= R usar el LT real porque no hay órdenes previas
    # en tránsito que cubran el lead time completo (especialmente al inicio de la simulación).
    LT_prot = LT if LT >= R_ else LT_ef
    U      = math.ceil((Media / (2 * V)) + ((V * R_) / 2))
    s      = math.ceil((Media * (LT_prot + R_)) + Z * sigma * ((LT_prot + R_) ** 0.5))
    Q      = math.ceil(((2 * OC * Media) / max(HC, 0.001)) ** 0.5)
    S      = s + Q + U
    SS     = math.ceil((Media * R_) + (Z * sigma * ((LT_prot + R_) ** 0.5) - U))
    return {"s": s, "Q": Q, "S": S, "SS": SS, "U": U, "LT_ef": round(LT_ef, 4)}

# ──────────────────────────────────────────────────────────────────────────────
# PARÁMETROS DE PERECIBILIDAD
# Q_max: máximo lote que se consume antes de vencer con probabilidad beta.
# Q*: mínimo entre EOQ y Q_max.
# E[O]: esperanza de caducidad por ciclo de pedido.
# ──────────────────────────────────────────────────────────────────────────────
def calcular_perecibilidad(Media, V, Q, SL, SL_eff=None, beta=0.95):
    """Restricción de perecibilidad sobre la cantidad de pedido."""
    if SL_eff is None:
        SL_eff = SL
    sigma_t = max(V, 0.001) ** 0.5
    Z_beta  = _norm_inv.ppf(beta)
    Q_max   = max(1, math.ceil(Media * SL_eff - Z_beta * sigma_t * (SL_eff ** 0.5)))
    Q_star  = min(Q, Q_max)
    denom   = sigma_t * (SL_eff ** 0.5)
    z_o     = (Q_star - Media * SL_eff) / denom if denom > 0 else -10.0
    E_O     = (Q_star - Media * SL_eff) * _norm_inv.cdf(z_o) + denom * _norm_inv.pdf(z_o)
    return {
        "Q_max":  Q_max,
        "Q_star": Q_star,
        "z_o":    round(z_o, 4),
        "E_O":    round(max(E_O, 0.0), 4),
    }

# ──────────────────────────────────────────────────────────────────────────────
# COSTOS ANALÍTICOS — fórmulas exactas del notebook "Calculadora de Políticas"
# CT1 (R,s,Q) / CT2 (R,S) / CT3 (R,s,S)  × 360 días
# ──────────────────────────────────────────────────────────────────────────────
def calcular_costos_analiticos(D, V, OC, HC, LT, R, Z, s, Q, S, U):
    """Costo anual teórico de cada política según "Calculadora de Políticas.ipynb"."""
    V  = max(V, 0.001)
    Q  = max(Q, 1)
    R  = max(R, 0.001)
    CT1 = 360 * math.ceil(
        OC * (D / Q) + HC * (Q / 2) +
        HC * (D * R + Z * ((R + LT) ** 0.5) * (V ** 0.5) - U)
    )
    CT2 = 360 * math.ceil(
        OC / R + HC * (D * R / 2) +
        HC * Z * ((R + LT) ** 0.5) * (V ** 0.5)
    )
    denom = max(S - s + U, 1)
    CT3 = 360 * math.ceil(
        OC * (D / denom) + HC * (denom / 2) +
        HC * (D * R + Z * ((R + LT) ** 0.5) * (V ** 0.5) - U)
    )
    return {"CT1": CT1, "CT2": CT2, "CT3": CT3}

# ──────────────────────────────────────────────────────────────────────────────
# RECOMENDAR PERÍODO DE REVISIÓN
# ──────────────────────────────────────────────────────────────────────────────
def recomendar_periodo(media_diaria, varianza_diaria, costo_orden, costo_mantener, lead_time):
    d = max(media_diaria, 0.001)
    Q = math.ceil(((2 * costo_orden * d) / costo_mantener) ** 0.5)
    R = Q / d
    if R < lead_time:
        R = lead_time
    if R <= 7:  return 7,  "Semanal (7 días)"
    if R <= 14: return 14, "Quincenal (14 días)"
    if R <= 21: return 21, "Cada 3 semanas (21 días)"
    if R <= 30: return 30, "Mensual (30 días)"
    r_redondeado = round(R / 7) * 7
    return int(r_redondeado), "Cada " + str(int(r_redondeado)) + " días"

# ──────────────────────────────────────────────────────────────────────────────
# SIMULACIÓN DISCRETA (por período R) — para productos de alta demanda (Media>200)
# Equivalente estadísticamente a la continua pero 1000x más rápida.
# ──────────────────────────────────────────────────────────────────────────────
def _sim_discreta(Media, OC, HC, LT, R, s, Q_star, S_obj, política,
                  NR=5, TiempoTotal=360):
    """
    Simulación discreta por período de revisión R.
    política: 'rsq' | 'rs' | 'rss'

    Corrección v2 (2026-06):
    - pedidos_en_transito rastreados en DÍAS REALES (t_orden + LT), no en pasos.
      t_orden = paso * R (inicio del período, momento de la revisión).
      Las llegadas se procesan cuando dia_llegada <= t_actual = (paso+1)*R.
      Esto garantiza que ningún lote llega antes de LT días reales,
      independientemente de si LT es múltiplo de R o no.
    - (R,s,Q): emite tantos lotes de Q_star como sean necesarios hasta que
      IP > s (semántica correcta de revisión periódica cuando LT > R: entre
      dos revisiones el inventario puede cruzar s múltiples veces).
    - (R,S) y (R,s,S): solo adoptan días reales; lógica de orden sin cambio.
    """
    pasos = max(1, int(round(TiempoTotal / R)))

    CostoTotalRep = 0.0; CostoDiarioRep = 0.0
    Inv_final = []; Tiempo_final = []; IP_final = []

    for i in range(NR):
        np.random.seed(i)
        OH = float(S_obj)   # arranque en nivel máximo S (notebook: OH_init=S)
        IT = 0.0; CostoTotal = 0.0
        pedidos_en_transito = []   # lista de (dia_llegada_real, cantidad)
        Inv = [OH]; Tiempo = [0.0]; IP_list = [OH + IT]

        for paso in range(pasos):
            t_actual = (paso + 1) * R   # fin del período
            t_orden  = paso * R         # inicio del período = momento de la revisión

            # ── Llegadas cuyo día real <= t_actual ───────────────────────────
            llegadas = [q for (dl, q) in pedidos_en_transito if dl <= t_actual]
            pedidos_en_transito = [(dl, q) for (dl, q) in pedidos_en_transito
                                   if dl > t_actual]
            OH += sum(llegadas)
            IT -= sum(llegadas)

            # ── Demanda del período ~ Poisson(Media × R) ────────────────────
            demanda = int(np.random.poisson(Media * R))
            OH_ant  = OH
            OH      = max(0.0, OH - demanda)

            # ── Costo holding (trapezoidal) ──────────────────────────────────
            CostoTotal += ((OH_ant + OH) / 2.0) * R * HC

            # ── Revisión y decisión de pedido ────────────────────────────────
            IP = OH + IT

            if política == 'rsq':
                # Emitir tantos Q_star hasta IP > s (multi-order periódico)
                while IP <= s:
                    IT += Q_star
                    pedidos_en_transito.append((t_orden + LT, Q_star))
                    CostoTotal += OC
                    IP += Q_star

            elif política == 'rs':
                Q_ord = max(0.0, S_obj - IP)
                if Q_ord > 0:
                    IT += Q_ord
                    pedidos_en_transito.append((t_orden + LT, Q_ord))
                    CostoTotal += OC

            elif política == 'rss':
                if IP <= s:
                    Q_ord = max(0.0, S_obj - IP)
                    if Q_ord > 0:
                        IT += Q_ord
                        pedidos_en_transito.append((t_orden + LT, Q_ord))
                        CostoTotal += OC

            Inv.append(OH); Tiempo.append(t_actual); IP_list.append(OH + IT)

        CostoTotalRep  += CostoTotal
        CostoDiarioRep += CostoTotal / TiempoTotal
        Inv_final = Inv; Tiempo_final = Tiempo; IP_final = IP_list

    return (
        round(CostoDiarioRep / NR),
        round(CostoTotalRep  / NR),
        Tiempo_final, Inv_final,
        0,
        IP_final,
        0,
    )

# ──────────────────────────────────────────────────────────────────────────────
# SIMULACIÓN UNIFICADA CON FEFO Y PERECIBILIDAD
# Función única equivalente al notebook Politicas_Inventario_Paracetamol.
#   Q_fijo=Q_star, usar_s=True,  S_obj=None    → política (R,s,Q)
#   Q_fijo=None,   usar_s=False, S_obj=nivel_S  → política (R,S)
#   Q_fijo=None,   usar_s=True,  S_obj=nivel_S  → política (R,s,S)
# Retorna: (cd, ct, Tiempo, OH, 0, IP, vencidas)
# ──────────────────────────────────────────────────────────────────────────────
def simular(OH_init, Q_fijo, usar_s, S_obj,
            Media, V, OC, HC, LT, R, s, Q_max,
            NR=5, TiempoTotal=360, SL=None, WC=0):
    """
    Simulación FEFO con demanda Poisson AGREGADA por intervalo (rápida).

    En lugar de procesar cada unidad como evento separado (inviable para
    Media=4000+ en Streamlit Cloud), agrupa la demanda entre revisiones/llegadas
    como Poisson(Media × Δt).  Estadísticamente equivalente; ~1000× más rápida.

    Lógica de políticas idéntica al notebook v2:
      Q_fijo=Q_star, usar_s=True,  S_obj=None   → (R,s,Q)
      Q_fijo=None,   usar_s=False, S_obj=S_RS    → (R,S)  OC en cada revisión
      Q_fijo=None,   usar_s=True,  S_obj=S       → (R,s,S)
    """
    import bisect

    if Media > 1_000_000:
        pol = 'rsq' if Q_fijo is not None else ('rs' if not usar_s else 'rss')
        _Q  = Q_fijo if Q_fijo is not None else Q_max
        _S  = S_obj  if S_obj  is not None else OH_init
        return _sim_discreta(Media, OC, HC, LT, R, s, _Q, _S, pol, NR, TiempoTotal)

    SL_eff = float(SL) if SL and SL > 0 else 1e6
    WC     = float(WC)

    # Limitar OH_init a Media*SL_eff: si el lote inicial es mayor que lo consumible
    # antes de vencer, el exceso se purga al día SL creando un vacío artificial de stock.
    OH_init = min(float(OH_init), Media * SL_eff) if SL_eff < 1e5 else float(OH_init)

    CostoDiarioReplica = 0.0
    CostoTotalReplica  = 0.0
    VencimientoTotal   = 0
    QuiebresTotal      = 0
    Tiempo_out = Inventario_out = OH_out = None

    for rep in range(NR):
        np.random.seed(rep)
        TNow     = 0.0
        batches  = [[float(OH_init), SL_eff]]   # [qty, t_vencimiento]
        IT       = 0.0
        CT       = 0.0
        UV       = 0
        QQ       = 0   # unidades sin atender (quiebres) en esta réplica
        pending  = []          # [(t_llegada, qty)], ordenado
        next_rev = float(R)    # próxima revisión

        Inventario   = [oh_total(batches) + IT]
        InventarioOH = [oh_total(batches)]
        Tiempo       = [TNow]

        while TNow < TiempoTotal:
            t_arr  = pending[0][0] if pending else float('inf')
            t_next = min(next_rev, t_arr, float(TiempoTotal))
            dt     = t_next - TNow

            # ── demanda agregada en [TNow, t_next] ────────────────────────
            if dt > 0:
                # Sub-intervalos delimitados por vencimientos de lotes
                exps = sorted({b[1] for b in batches if TNow < b[1] <= t_next})
                checkpoints = [TNow] + exps + [t_next]

                for k in range(len(checkpoints) - 1):
                    t_a, t_b = checkpoints[k], checkpoints[k + 1]
                    sub_dt   = t_b - t_a
                    if sub_dt <= 0:
                        continue

                    # Demanda Poisson del sub-intervalo
                    D = int(np.random.poisson(Media * sub_dt))

                    OH_pre = oh_total(batches)

                    # Consumo FEFO
                    rem, new_b = D, []
                    for b in batches:
                        if rem <= 0:
                            new_b.append(b)
                        else:
                            c = min(b[0], rem)
                            b[0] -= c
                            rem  -= c
                            if b[0] > 0:
                                new_b.append(b)
                    batches = new_b

                    # Si rem > 0 después del FEFO, esas unidades no pudieron atenderse
                    QQ += rem   # acumula quiebres de esta réplica

                    OH_post = oh_total(batches)
                    # Costo mantener: aproximación trapezoidal
                    CT += (OH_pre + OH_post) / 2.0 * sub_dt * HC

                    # Purgar lotes vencidos al final del sub-intervalo
                    vivos, wasted = [], 0.0
                    for b in batches:
                        if b[1] <= t_b:
                            wasted += b[0]
                        else:
                            vivos.append(b)
                    if wasted > 0:
                        CT += wasted * WC
                        UV += int(wasted)
                    batches = vivos

            TNow = t_next

            # ── procesar llegadas en TNow ──────────────────────────────────
            while pending and pending[0][0] <= TNow + 1e-9:
                _, qty = pending.pop(0)
                batches.append([float(qty), TNow + SL_eff])
                IT -= qty
            batches.sort(key=lambda b: b[1])

            # ── revisión en TNow ──────────────────────────────────────────
            if TNow >= next_rev - 1e-9 and TNow < TiempoTotal:
                OH = oh_total(batches)
                IP = OH + IT

                if usar_s:
                    # (R,s,Q): emite tantos lotes de Q_fijo hasta IP > s (multi-order).
                    # Cuando LT > R hay múltiples revisiones durante el lead time;
                    # la política canónica genera una orden por cada cruce de s,
                    # lo que en revisión periódica se traduce en: while IP <= s → pedir.
                    # (R,s,S): emite un solo lote hasta S (lote variable, una sola orden).
                    if Q_fijo is not None:
                        # (R,s,Q) — cantidad fija, múltiples órdenes posibles
                        while IP <= s:
                            IT += Q_fijo
                            bisect.insort(pending, (TNow + LT, Q_fijo))
                            CT += OC
                            IP += Q_fijo
                    else:
                        # (R,s,S) — cantidad variable hasta S, una sola orden
                        if IP <= s:
                            lote = max(0, S_obj - IP)
                            if lote > 0:
                                IT += lote
                                bisect.insort(pending, (TNow + LT, lote))
                                CT += OC
                else:
                    # (R,S): OC siempre; lote variable sin cap Q_max (notebook v2)
                    lote = max(0, S_obj - IP)
                    CT  += OC
                    if lote > 0:
                        IT += lote
                        bisect.insort(pending, (TNow + LT, lote))

                next_rev = TNow + R

            Inventario.append(oh_total(batches) + IT)
            InventarioOH.append(oh_total(batches))
            Tiempo.append(TNow)

        CostoDiarioReplica += CT / TiempoTotal
        CostoTotalReplica  += CT
        VencimientoTotal   += UV
        QuiebresTotal      += QQ
        Tiempo_out = Tiempo; Inventario_out = Inventario; OH_out = InventarioOH

    return (
        round(CostoDiarioReplica / NR),
        round(CostoTotalReplica  / NR),
        Tiempo_out, OH_out,
        round(QuiebresTotal      / NR),   # promedio de quiebres entre réplicas
        Inventario_out,
        round(VencimientoTotal   / NR),
    )

# ──────────────────────────────────────────────────────────────────────────────
# PRONÓSTICO BAYESIANO GAMMA-POISSON
# Prior conjugado Gamma(α=1, β=0.01) para demanda Poisson.
# Tomado directamente de Paracetamol_RH.py.
# ──────────────────────────────────────────────────────────────────────────────
_PRIOR_ALPHA = 1.0
_PRIOR_BETA  = 0.01

def bayesian_forecast(consumo_mensual: list, dias_por_mes: list):
    """Pronóstico Bayesiano Gamma-Poisson, igual que en Paracetamol_RH.py.

    Prior: λ_mensual ~ Gamma(PRIOR_ALPHA, 1/PRIOR_BETA)
    Posterior: λ_mensual | datos ~ Gamma(a_post, 1/b_post)
      a_post = PRIOR_ALPHA + Σ consumo_mensual
      b_post = PRIOR_BETA  + n_meses
    λ_diario = λ_mensual / días_mes_siguiente
    Nota: se usa el mes siguiente (no el promedio histórico) igual que en Paracetamol_RH.py.
    """
    n_meses    = len(consumo_mensual)
    a_post     = _PRIOR_ALPHA + sum(consumo_mensual)
    b_post     = _PRIOR_BETA  + n_meses
    # Tasa mensual posterior
    lam_mensual_hat           = a_post / b_post
    lam_mensual_lo, lam_mensual_hi = gamma_dist.ppf(
        [0.05, 0.95], a=a_post, scale=1 / b_post
    )
    # Días del mes siguiente: usar el último mes del historial + 1 mes (igual que Paracetamol_RH.py)
    if dias_por_mes:
        _ultimo_dias = int(dias_por_mes[-1])
        # Aproximar días del mes siguiente como el mismo número de días del último mes
        # (en producción se puede pasar el valor exacto desde la UI)
        dias_sig = _ultimo_dias
    else:
        dias_sig = 30
    lam_hat    = lam_mensual_hat / dias_sig
    lam_lo     = lam_mensual_lo  / dias_sig
    lam_hi     = lam_mensual_hi  / dias_sig

    media  = float(np.mean(consumo_mensual))
    desvio = float(np.std(consumo_mensual))
    cv     = desvio / media if media > 0 else 0.0
    return {
        "lambda_diario_hat":  lam_hat,
        "lambda_lo_diario":   lam_lo,
        "lambda_hi_diario":   lam_hi,
        "lambda_mensual_hat": lam_mensual_hat,
        "lambda_mensual_lo":  lam_mensual_lo,
        "lambda_mensual_hi":  lam_mensual_hi,
        "media_mensual":      media,
        "desvio_mensual":     desvio,
        "cv":                 cv,
        "a_post":             a_post,
        "b_post":             b_post,
    }

def _forecast_demand_rh(history: list):
    """Actualiza el pronóstico Bayesiano con el historial de demanda diaria."""
    n     = len(history)
    s_val = sum(history)
    a     = _PRIOR_ALPHA + s_val
    b     = _PRIOR_BETA  + n
    lhat  = a / b
    lo, hi = gamma_dist.ppf([0.05, 0.95], a=a, scale=1 / b)
    return round(lhat), round(lo), round(hi)

# ──────────────────────────────────────────────────────────────────────────────
# HORIZONTE RODANTE MIP (Gurobi) — Paracetamol_RH.py
# Solo disponible si gurobipy está instalado y licenciado.
# ──────────────────────────────────────────────────────────────────────────────
def _solve_horizon_rh(inv0, d_hat, period, pending, cooldown,
                      L, tl, R_rh, Qmax, h_cost, k_cost, w_cost, s_cost=None,
                      ss_units=0):
    """Horizonte rodante MIP resuelto con PuLP/CBC (sin licencia requerida).

    w_cost   : penalización por unidad VENCIDA (waste).
    s_cost   : penalización por unidad de demanda INSATISFECHA (shortage).
               Debe ser MUCHO mayor que k_cost. Por defecto: max(10_000_000, k_cost×100).
    ss_units : stock de seguridad mínimo deseado (unidades). Implementado como
               restricción blanda con la misma penalización que s_cost, de modo que
               el modelo SIEMPRE prefiere pedir antes que bajar del piso de seguridad.
               Con ss_units > 0 el stock nunca llega a 0 en régimen estacionario.
    """
    if s_cost is None:
        s_cost = max(10_000_000, k_cost * 100)
    # HORIZON debe cubrir al menos tl + R días para que el pedido de hoy
    # (que llega en tau=tl) alcance a cubrir el período completo hasta el
    # próximo pedido (R días después). Si HORIZON < tl + R + 1, el pedido
    # de hoy solo cubre HORIZON - tl - 1 días, menos que R, generando gaps.
    HORIZON = tl + max(5, R_rh + 1)
    A  = list(range(L))
    A1 = list(range(1, L))
    TH = list(range(HORIZON))

    arriving = {tau: 0 for tau in TH}
    for (arr_period, qty) in pending:
        tau = arr_period - period
        if 0 <= tau < HORIZON:
            arriving[tau] += qty

    mdl = _pulp.LpProblem("SAVIA_RH", _pulp.LpMinimize)

    I = {(a, t): _pulp.LpVariable(f"I_{a}_{t}", lowBound=0, cat="Integer") for a in A  for t in TH}
    D = {(a, t): _pulp.LpVariable(f"D_{a}_{t}", lowBound=0, cat="Integer") for a in A1 for t in TH}
    Q = {t:      _pulp.LpVariable(f"Q_{t}",     lowBound=0, cat="Integer") for t in TH}
    Y = {t:      _pulp.LpVariable(f"Y_{t}",     cat="Binary")              for t in TH}
    W = {t:      _pulp.LpVariable(f"W_{t}",     lowBound=0, cat="Integer") for t in TH}
    S = {t:      _pulp.LpVariable(f"S_{t}",     lowBound=0, cat="Integer") for t in TH}

    # Stock de seguridad: variables de slack ANTES del objetivo para incluirlas en él.
    # CRÍTICO: en PuLP, `mdl += expr` REEMPLAZA el objetivo si se hace después de
    # haberlo fijado. Por eso se construye el objetivo COMPLETO en una sola expresión.
    if ss_units > 0:
        UB = {t: _pulp.LpVariable(f"UB_{t}", lowBound=0, cat="Integer") for t in TH}

    # ── OBJETIVO COMPLETO (una sola asignación) ────────────────────────────
    _obj = (
        _pulp.lpSum(h_cost * I[a, tau] for a in A  for tau in TH) +
        _pulp.lpSum(k_cost * Y[tau]    for tau in TH) +
        _pulp.lpSum(w_cost * W[tau]    for tau in TH) +   # penaliza vencimientos
        _pulp.lpSum(s_cost * S[tau]    for tau in TH)     # penaliza quiebres de stock
    )
    if ss_units > 0:
        # Misma penalización que quiebre: el modelo SIEMPRE prefiere pedir
        # antes que bajar del piso de seguridad.
        _obj += _pulp.lpSum(s_cost * UB[tau] for tau in TH)
    mdl += _obj

    # ── RESTRICCIONES ─────────────────────────────────────────────────────
    for tau in TH:
        for a in range(L - 1):
            prev = inv0[a] if tau == 0 else I[a, tau - 1]
            mdl += I[a + 1, tau] == prev - D[a + 1, tau]

    for tau in TH:
        mdl += I[0, tau] == arriving[tau] + (Q[tau - tl] if tau >= tl else 0)

    for tau in TH:
        mdl += _pulp.lpSum(D[a, tau] for a in A1) + S[tau] == d_hat

    for tau in TH:
        for a in A1:
            prev = inv0[a - 1] if tau == 0 else I[a - 1, tau - 1]
            mdl += D[a, tau] <= prev

    for tau in TH:
        mdl += W[tau] == I[L - 1, tau]

    for tau in TH:
        mdl += Q[tau] <= Qmax * Y[tau]

    for tau in TH:
        if tau < cooldown:
            mdl += Y[tau] == 0

    for tau in TH:
        if tau >= cooldown:
            neighbors = [t for t in range(max(0, tau - R_rh + 1), tau) if t >= cooldown]
            if neighbors:
                mdl += _pulp.lpSum(Y[t] for t in neighbors) + Y[tau] <= 1

    # Restricción del stock de seguridad: stock_total[tau] + UB[tau] >= SS
    if ss_units > 0:
        for tau in TH:
            mdl += _pulp.lpSum(I[a, tau] for a in A) + UB[tau] >= ss_units

    mdl.solve(_pulp.PULP_CBC_CMD(msg=0))

    if _pulp.LpStatus[mdl.status] != "Optimal":
        return None

    return (
        round(_pulp.value(Q[0])),
        round(_pulp.value(Y[0])),
        round(_pulp.value(W[0])),
        round(_pulp.value(S[0])),
        {a: round(_pulp.value(I[a, 0])) for a in A},
    )


# ──────────────────────────────────────────────────────────────────────────────
# FUNCIONES PARA LEER EL FORMATO DEL HOSPITAL REGIONAL
# Los archivos del hospital tienen una columna por mes (formato "ancho"),
# en vez de una fila por dispensación (formato "largo" que usa la app).
# Estas funciones detectan ese formato y lo convierten automáticamente.
# ──────────────────────────────────────────────────────────────────────────────

MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
         "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]

def detectar_formato_hospital(df):
    """
    Devuelve True si el DataFrame tiene formato ancho del hospital:
    una columna por mes en lugar de una fila por dispensación.
    Se detecta contando cuántas columnas contienen nombres de meses.
    """
    columnas_con_mes = 0
    for col in df.columns:
        col_lower = str(col).lower()
        for mes in MESES:
            if mes in col_lower:
                columnas_con_mes += 1
                break
    return columnas_con_mes >= 3

def leer_con_encabezado_correcto(archivo_bytes, nombre_hoja):
    """
    Detecta si los encabezados reales están en la fila 1 (header=0) o en la fila 4 (header=3).
    El formato del hospital tiene un título fusionado en las primeras 3 filas.
    Cualquier otro archivo estándar tiene encabezados en la primera fila.
    """
    df_prueba = pd.read_excel(io.BytesIO(archivo_bytes), sheet_name=nombre_hoja, header=0, nrows=1)
    primera_col = _sin_tildes(str(df_prueba.columns[0]))
    # Palabras clave que indican que los encabezados ya están en la fila 1
    # Se normalizan con _sin_tildes para comparar sin importar si el Excel usa tildes o no
    _palabras_h0 = ["codigo", "sku", "clave", "f_pedido", "fecha", "matcod",
                    "pedido", "material", "id", "item", "producto"]
    if any(p in primera_col for p in _palabras_h0):
        return pd.read_excel(io.BytesIO(archivo_bytes), sheet_name=nombre_hoja, header=0)
    # Indicadores de que los encabezados reales están en la fila 4:
    # - primera columna es "unnamed" o NaN (celda vacía → título fusionado encima)
    # - primera columna tiene más de 25 caracteres (es un título largo, no un nombre de campo)
    # - primera columna es un número o fecha
    usa_header3 = (
        primera_col.startswith("unnamed")
        or primera_col == "nan"
        or len(primera_col) > 25
    )
    try:
        float(primera_col)
        usa_header3 = True
    except ValueError:
        pass
    if usa_header3:
        return pd.read_excel(io.BytesIO(archivo_bytes), sheet_name=nombre_hoja, header=3)
    return pd.read_excel(io.BytesIO(archivo_bytes), sheet_name=nombre_hoja, header=0)

def transformar_formato_ancho(df):
    """
    Convierte el formato ancho del hospital al formato largo que usa la app.

    Formato ancho (hospital):
      CODIGO | NOMBRE | CONSUMO Enero/2025 | ... | EXIST.HOSPITAL | PRECIO | StcMinimo | ...

    Retorna (mov_largo, inv_extra) donde:
      - mov_largo: DataFrame con CODIGO | NOMBRE | FECHA | CANTIDAD
      - inv_extra: DataFrame con CODIGO | STOCK_TOTAL | COSTO | STC_MIN | STC_MAX | STC_CRITICO | CONSUMO_PROM | ALCANCE | SUGERIDO
    """
    # Crear diccionario que mapea nombre de mes a número (enero → 1, febrero → 2, ...)
    MESES_NUM = {}
    for num, mes in enumerate(MESES):
        MESES_NUM[mes] = num + 1

    # Buscar columnas de código y nombre
    col_codigo = None
    col_nombre = None
    for col in df.columns:
        col_l = _sin_tildes(str(col)).strip()
        if "codigo" in col_l and col_codigo is None:
            col_codigo = col
        elif "nombre" in col_l and col_nombre is None:
            col_nombre = col

    if col_codigo is None or col_nombre is None:
        return None, None

    # Identificar columnas de meses (consumo mensual)
    cols_meses = {}
    for col in df.columns:
        col_str = str(col).lower()
        for mes_nombre, mes_num in MESES_NUM.items():
            if mes_nombre in col_str:
                match_año = re.search(r'20\d\d', str(col))
                año = int(match_año.group()) if match_año else 2024
                cols_meses[col] = (mes_num, año)
                break

    if len(cols_meses) == 0:
        return None, None

    # Identificar columnas de existencias (EXIST.*)
    # Recorremos todas las columnas y guardamos las que empiezan con "EXIST"
    cols_exist = []
    for c in df.columns:
        if str(c).strip().upper().startswith("EXIST"):
            cols_exist.append(c)

    # Buscar columnas de precio y parámetros de stock usando for loops
    col_precio = None
    for c in df.columns:
        if "precio" in str(c).lower():
            col_precio = c
            break

    col_stc_min = None
    for c in df.columns:
        nombre_c = str(c).lower().replace(" ", "").replace("í", "i").replace("ó", "o")
        if "stcminimo" in nombre_c:
            col_stc_min = c
            break

    col_stc_max = None
    for c in df.columns:
        nombre_c = str(c).lower().replace(" ", "").replace("í", "i").replace("ó", "o")
        if "stcmaximo" in nombre_c:
            col_stc_max = c
            break

    col_stc_crit = None
    for c in df.columns:
        nombre_c = str(c).lower().replace(" ", "").replace("í", "i").replace("ó", "o")
        if "stccrítico" in nombre_c:
            col_stc_crit = c
            break

    col_cons_prom = None
    for c in df.columns:
        if "consumo_promedio_sin_cero" in str(c).lower():
            col_cons_prom = c
            break
    if col_cons_prom is None:
        for c in df.columns:
            if "consumo_promedio" in str(c).lower():
                col_cons_prom = c
                break

    col_alcance = None
    for c in df.columns:
        if "alcance" in str(c).lower():
            col_alcance = c
            break

    col_sugerido = None
    for c in df.columns:
        if "sugerido" in str(c).lower():
            col_sugerido = c
            break

    # Convertir de ancho a largo: una fila por producto-mes
    filas_mov  = []
    filas_inv  = []
    for _, row in df.iterrows():
        código = row[col_codigo]
        nombre = row[col_nombre]
        if pd.isna(código) or pd.isna(nombre):
            continue
        cod = str(código).strip()
        nom = str(nombre).strip()

        # Movimientos mensuales
        for col_mes, (mes_num, año) in cols_meses.items():
            cantidad = pd.to_numeric(row[col_mes], errors="coerce")
            if pd.isna(cantidad):
                cantidad = 0
            filas_mov.append({
                "CODIGO":   cod,
                "NOMBRE":   nom,
                "FECHA":    pd.Timestamp(year=año, month=mes_num, day=1),
                "CANTIDAD": float(cantidad),
            })

        # Datos de inventario complementarios
        # Sumar todas las columnas de existencias (puede haber una por bodega)
        stock_total = 0
        per_bodega  = {}   # stock individual por bodega
        if cols_exist:
            lista_existencias = []
            for c in cols_exist:
                lista_existencias.append(row[c])
            vals = pd.to_numeric(pd.Series(lista_existencias), errors="coerce").fillna(0)
            stock_total = float(vals.sum())
            # Guardar cada bodega como columna separada (BOD_*)
            for c, v in zip(cols_exist, vals):
                raw = re.sub(r'^EXIST\.?\s*', '', str(c).strip(), flags=re.IGNORECASE).strip()
                key = "BOD_" + re.sub(r'[^A-Za-z0-9]', '_', raw).strip('_').upper()[:28]
                per_bodega[key] = float(v)

        # Función auxiliar para convertir un valor de celda a número sin romper si está vacío
        def a_numero(nombre_col):
            if nombre_col is None: return None
            valor = pd.to_numeric(row[nombre_col], errors="coerce")
            return float(valor) if not pd.isna(valor) else None

        _inv_row = {
            "CODIGO":       cod,
            "STOCK_TOTAL":  stock_total,
            "COSTO":        a_numero(col_precio),
            "STC_MIN":      a_numero(col_stc_min),
            "STC_MAX":      a_numero(col_stc_max),
            "STC_CRITICO":  a_numero(col_stc_crit),
            "CONS_PROM":    a_numero(col_cons_prom),
            "ALCANCE":      a_numero(col_alcance),
            "SUGERIDO":     a_numero(col_sugerido),
        }
        _inv_row.update(per_bodega)   # añadir columnas BOD_* al registro
        filas_inv.append(_inv_row)

    if len(filas_mov) == 0:
        return None, None

    mov_largo = pd.DataFrame(filas_mov)
    inv_extra = pd.DataFrame(filas_inv).drop_duplicates("CODIGO")
    return mov_largo, inv_extra

# ── Datos compartidos entre todos los usuarios ────────────────────────────────
@st.cache_resource
def _store_global():
    return {
        "inv": None, "mov": None, "fuente": None, "formato_hospital": False,
        "inv_lotes": None,   # DataFrame con lotes+vencimientos del archivo Inventario estándar
        "costo_orden": 40000, "costo_mantener": 10, "lead_time": 1.625, "periodo_revision": 0.5,
        "nivel_servicio_z": 1.645,
        "vida_util_dias": 0, "costo_desperdicio": 0, "beta_servicio": 0.95,
        "fecha_revision": date.today(), "hora_revision": None, "responsable": "",
        "archivos":       [],   # [{nombre, size, cargado_en, responsable, preview, n_productos, mov, inv_extra, inv_directo}]
        "historial":      [],   # [{Fecha, Responsable, Acción, Archivo, Productos}]
        "archivos_bytes": {},   # {nombre: bytes_originales} — para descargar el archivo original + filas nuevas
        "gh_gist_id":     None, # gist_id del Gist de SAVIA en GitHub
    }


def _guardar_params(fecha, hora, resp, c_orden, c_mant, lt, pr,
                    vida_util=0, c_desp=0, beta=0.95, z=1.645):
    store = _store_global()
    store["fecha_revision"]    = fecha
    store["hora_revision"]     = hora
    store["responsable"]       = resp
    store["costo_orden"]       = c_orden
    store["costo_mantener"]    = c_mant
    store["lead_time"]         = lt
    store["periodo_revision"]  = pr
    store["vida_util_dias"]    = vida_util
    store["costo_desperdicio"] = c_desp
    store["beta_servicio"]     = beta
    store["nivel_servicio_z"]  = z


def _excel_mov_actualizado(nuevos_movs: list) -> tuple:
    """Devuelve (bytes_excel, nombre_archivo) del archivo de movimientos original
    con las filas nuevas añadidas al final en el mismo formato del archivo cargado."""
    _bytes_map = _store_global().get("archivos_bytes", {})

    # Buscar el archivo de pedidos/movimientos (el que tiene columnas tipo F_PEDIDO, MATCODIGO, etc.)
    _archivo_mov_bytes = None
    _archivo_mov_nom   = None
    for _nom, _bts in _bytes_map.items():
        try:
            _df_test = pd.read_excel(io.BytesIO(_bts), nrows=1)
            _cols_l  = [str(c).lower() for c in _df_test.columns]
            if any("pedido" in c or "despacho" in c or "dispensad" in c or "matcod" in c for c in _cols_l):
                _archivo_mov_bytes = _bts
                _archivo_mov_nom   = _nom
                break
        except Exception:
            continue

    if _archivo_mov_bytes is None:
        # Fallback: exportar solo los movimientos manuales como Excel simple
        _buf = io.BytesIO()
        pd.DataFrame(nuevos_movs).drop(columns=["_ts"], errors="ignore").to_excel(_buf, index=False, engine="openpyxl")
        return _buf.getvalue(), f"movimientos_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx"

    # Leer archivo original completo
    _df_orig = pd.read_excel(io.BytesIO(_archivo_mov_bytes))

    # Detectar columnas clave del archivo original
    def _find_col(df, keywords):
        for c in df.columns:
            cn = _sin_tildes(str(c))
            if any(_sin_tildes(k) in cn for k in keywords):
                return c
        return None

    _c_cod  = _find_col(_df_orig, ["matcod", "código", "cod_mat"])
    _c_nom  = _find_col(_df_orig, ["matnombre", "nombre", "material", "medicamento"])
    _c_fpd  = _find_col(_df_orig, ["f_pedido", "fecha_pedido", "fecha"])
    _c_cant = _find_col(_df_orig, ["cant_despachada", "despachada", "dispensada", "cantidad"])
    _c_bod  = _find_col(_df_orig, ["bod", "destino", "bodega"])

    # Construir filas nuevas en el formato original
    _filas_nuevas = []
    for _m in nuevos_movs:
        _row = {c: None for c in _df_orig.columns}
        if _c_cod:  _row[_c_cod]  = _m.get("Código", "")
        if _c_nom:  _row[_c_nom]  = _m.get("Medicamento", "")
        if _c_fpd:  _row[_c_fpd]  = _m.get("Fecha", "")
        if _c_cant: _row[_c_cant] = _m.get("Cantidad", 0)
        if _c_bod:  _row[_c_bod]  = _m.get("Bodega", "")
        # Columnas extra para identificar lo añadido desde SAVIA
        _row["Tipo_SAVIA"]         = _m.get("Tipo", "")
        _row["Responsable_SAVIA"]  = _m.get("Responsable", "")
        _row["Obs_SAVIA"]          = _m.get("Observaciones", "")
        _filas_nuevas.append(_row)

    _df_final = pd.concat([_df_orig, pd.DataFrame(_filas_nuevas)], ignore_index=True) if _filas_nuevas else _df_orig

    _buf = io.BytesIO()
    _df_final.to_excel(_buf, index=False, engine="openpyxl")
    _nom_dl = _archivo_mov_nom.replace(".xlsx", f"_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx")
    return _buf.getvalue(), _nom_dl


def _excel_inv_actualizado() -> tuple:
    """Devuelve (bytes_excel, nombre_archivo) del archivo de inventario original
    con la columna de existencias actualizada según los movimientos registrados."""
    _bytes_map = _store_global().get("archivos_bytes", {})
    _movs      = _store_global().get("movimientos", [])  # lista interna

    # Buscar el archivo de inventario (tiene columnas tipo Existencia, Código, Material, etc.)
    _archivo_inv_bytes = None
    _archivo_inv_nom   = None
    for _nom, _bts in _bytes_map.items():
        try:
            # El inventario tiene cabecera en fila 2 (índice 2)
            _df_test = pd.read_excel(io.BytesIO(_bts), header=2, nrows=1)
            _cols_l  = [_sin_tildes(str(c)) for c in _df_test.columns]
            if any("existencia" in c or "codigo" in c or "material" in c for c in _cols_l):
                _archivo_inv_bytes = _bts
                _archivo_inv_nom   = _nom
                break
        except Exception:
            continue

    if _archivo_inv_bytes is None:
        # Fallback: exportar el inv procesado de SAVIA
        _buf = io.BytesIO()
        _store_global()["inv"].to_excel(_buf, index=False, engine="openpyxl")
        return _buf.getvalue(), f"inventario_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx"

    # Leer con header correcto
    _df_inv = pd.read_excel(io.BytesIO(_archivo_inv_bytes), header=2)

    def _find_col(df, keywords):
        for c in df.columns:
            cn = _sin_tildes(str(c))
            if any(_sin_tildes(k) in cn for k in keywords):
                return c
        return None

    _c_cod  = _find_col(_df_inv, ["código", "cod"])
    _c_nom  = _find_col(_df_inv, ["material", "nombre", "medicamento"])
    _c_exist = _find_col(_df_inv, ["existencia"])

    # Calcular delta por medicamento desde los movimientos manuales
    _smv_list = _store_global().get("movimientos", [])
    if _c_cod and _c_exist and _smv_list:
        for _m in _smv_list:
            _delta = _m["Cantidad"] if _m["Tipo"] == "Entrada" else -_m["Cantidad"]
            _mask  = _df_inv[_c_cod].astype(str).str.strip() == str(_m.get("Código","")).strip()
            if _mask.any():
                _cur = pd.to_numeric(_df_inv.loc[_mask, _c_exist], errors="coerce").fillna(0)
                _df_inv.loc[_mask, _c_exist] = (_cur + _delta).clip(lower=0)

    _buf = io.BytesIO()
    _df_inv.to_excel(_buf, index=False, engine="openpyxl")
    _nom_dl = _archivo_inv_nom.replace(".xlsx", f"_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx")
    return _buf.getvalue(), _nom_dl

# ── GitHub Gist helpers (persistencia gratuita, sin tarjeta) ───────────────────
import base64 as _b64
import json   as _json

_GH_GIST_DESC = "SAVIA_datos_inventario"   # identifica el gist en la cuenta del usuario


def _gh_token():
    """Retorna el Personal Access Token de GitHub desde st.secrets."""
    try:
        return str(st.secrets["github"]["token"])
    except Exception:
        return None


def _gh_headers():
    _t = _gh_token()
    if not _t:
        return None
    return {
        "Authorization": f"token {_t}",
        "Accept": "application/vnd.github.v3+json",
    }


def _gh_find_gist():
    """Busca el gist de SAVIA en la cuenta del usuario. Retorna gist_id o None."""
    _h = _gh_headers()
    if not _h:
        return None
    try:
        _r = _requests.get("https://api.github.com/gists?per_page=100",
                           headers=_h, timeout=15)
        if _r.status_code != 200:
            return None
        for _g in _r.json():
            if _g.get("description", "") == _GH_GIST_DESC:
                _store_global()["gh_gist_id"] = _g["id"]   # cachear en store
                return _g["id"]
        return None
    except Exception:
        return None


def _gh_guardar_en_gist():
    """Guarda archivos originales + movimientos en un Gist privado.
    Retorna (ok, mensaje)."""
    _h = _gh_headers()
    if not _h:
        return False, "Token de GitHub no configurado"

    _store = _store_global()
    _payload_files = {}

    # Codificar cada archivo Excel/CSV en base64
    for _nom_g, _bts_g in _store.get("archivos_bytes", {}).items():
        _safe = _nom_g.replace("/", "_").replace("\\", "_")
        _payload_files[f"SAVIA__{_safe}"] = {
            "content": _b64.b64encode(_bts_g).decode("ascii")
        }

    # Guardar movimientos manuales como JSON
    _movs_json = _json.dumps(
        _store.get("movimientos", []), default=str, ensure_ascii=False
    )
    _payload_files["SAVIA__movimientos.json"] = {"content": _movs_json or "[]"}

    if not _payload_files:
        return False, "No hay datos para guardar"

    try:
        _gist_id = _store.get("gh_gist_id") or _gh_find_gist()
        if _gist_id:
            _r = _requests.patch(
                f"https://api.github.com/gists/{_gist_id}",
                headers=_h, json={"files": _payload_files}, timeout=90,
            )
        else:
            _r = _requests.post(
                "https://api.github.com/gists",
                headers=_h,
                json={
                    "description": _GH_GIST_DESC,
                    "public": False,
                    "files": _payload_files,
                },
                timeout=90,
            )
        if _r.status_code in (200, 201):
            _store["gh_gist_id"] = _r.json()["id"]
            return True, "Guardado en GitHub Gist"
        return False, f"Error HTTP {_r.status_code}: {_r.text[:160]}"
    except Exception as _e:
        return False, str(_e)


def _gh_cargar_desde_gist():
    """Descarga y procesa los archivos del Gist de SAVIA.
    Retorna (n_archivos_cargados, mensaje)."""
    _h = _gh_headers()
    if not _h:
        return 0, "Token de GitHub no configurado"

    _store   = _store_global()
    _gist_id = _store.get("gh_gist_id") or _gh_find_gist()
    if not _gist_id:
        return 0, "No se encontró ningún Gist de SAVIA. Sube archivos primero."

    try:
        _r = _requests.get(f"https://api.github.com/gists/{_gist_id}",
                           headers=_h, timeout=30)
        if _r.status_code != 200:
            return 0, f"Error HTTP {_r.status_code}"

        _store["gh_gist_id"] = _gist_id
        _gist_files = _r.json().get("files", {})

        # Recuperar movimientos JSON
        if "SAVIA__movimientos.json" in _gist_files:
            _raw_url = _gist_files["SAVIA__movimientos.json"].get("raw_url")
            if _raw_url:
                _mr = _requests.get(_raw_url, timeout=20)
                if _mr.status_code == 200:
                    try:
                        _movs_rec = _json.loads(_mr.text)
                        if isinstance(_movs_rec, list):
                            _store["movimientos"] = _movs_rec
                    except Exception:
                        pass

        # Recuperar archivos Excel/CSV
        _ya       = {a["nombre"] for a in _store["archivos"]}
        _cargados = 0
        _tz_gh    = pytz.timezone("America/Santiago")
        _ahora_gh = pd.Timestamp.now(tz=_tz_gh).strftime("%Y-%m-%d %H:%M")
        _resp_gh  = _store.get("responsable", "") or "GitHub Gist"

        for _fname, _fdata in _gist_files.items():
            if not _fname.startswith("SAVIA__") or _fname == "SAVIA__movimientos.json":
                continue
            _nom_orig = _fname[len("SAVIA__"):]          # quitar prefijo
            if _nom_orig in _ya:
                continue
            # Usar raw_url para evitar contenido truncado en la API
            _raw_url = _fdata.get("raw_url")
            if not _raw_url:
                continue
            _raw_r = _requests.get(_raw_url, timeout=90)
            if _raw_r.status_code != 200:
                continue
            try:
                _bytes_rec = _b64.b64decode(_raw_r.content)
            except Exception:
                continue
            _rec = _parsear_archivo(_nom_orig, _bytes_rec)
            if _rec is None:
                continue
            if len(_bytes_rec) <= 5 * 1024 * 1024:
                _store.setdefault("archivos_bytes", {})[_nom_orig] = _bytes_rec
            _store["archivos"].append({
                "nombre":      _nom_orig,
                "size":        len(_bytes_rec),
                "mov":         _rec["mov"],
                "inv_extra":   _rec["inv_extra"],
                "inv_directo": _rec["inv_directo"],
                "cargado_en":  _ahora_gh,
                "responsable": _resp_gh,
                "preview":     _rec["preview"],
                "n_productos": _rec["n_productos"],
            })
            _store["historial"].append({
                "Fecha":       _ahora_gh,
                "Responsable": _resp_gh,
                "Acción":      "Carga desde GitHub Gist",
                "Archivo":     _nom_orig,
                "Productos":   _rec["n_productos"],
            })
            _ya.add(_nom_orig)
            _cargados += 1

        if _cargados:
            _recompute()

        _n_movs = len(_store.get("movimientos", []))
        if _cargados:
            _msg = f"{_cargados} archivo(s) cargado(s) desde GitHub Gist."
            if _n_movs:
                _msg += f" + {_n_movs} movimiento(s) recuperados."
        elif _n_movs:
            _msg = f"Sin archivos nuevos. {_n_movs} movimiento(s) recuperados."
        else:
            _msg = "No hay datos nuevos en el Gist."
        return _cargados, _msg

    except Exception as _e:
        return 0, str(_e)


def _df_a_preview(df):
    """Convierte un DataFrame de hasta 8 filas a lista de dicts con tipos básicos.
    Evita guardar DataFrames con tipos exóticos (datetime64, etc.) en el store global,
    lo que causaba fallos de serialización PyArrow al renderizar st.dataframe().
    """
    preview_df = _safe_df(df.head(8))
    # Convertir datetime/timedelta a str para que sean JSON-serializables
    for col in preview_df.columns:
        if pd.api.types.is_datetime64_any_dtype(preview_df[col]) or \
           pd.api.types.is_timedelta64_dtype(preview_df[col]):
            preview_df[col] = preview_df[col].astype(str)
    return preview_df.to_dict(orient="records")

def _parsear_archivo(nombre, contenido):
    """Parsea los bytes de un archivo UNA SOLA VEZ y retorna sus DataFrames.
    Los DataFrames resultantes se guardan en el store (no los bytes crudos),
    para que _recompute() solo combine sin necesitar re-parsear con openpyxl.
    """
    try:
        if nombre.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(contenido))
            result = {"mov": None, "inv_extra": None, "inv_directo": df,
                      "preview": _df_a_preview(df), "n_productos": len(df)}
            del df
            return result
        xls    = pd.ExcelFile(io.BytesIO(contenido))
        hojas  = xls.sheet_names
        df_pri = leer_con_encabezado_correcto(contenido, hojas[0])
        if detectar_formato_hospital(df_pri):
            todos_mov = [];  todos_inv_e = [];  cods = set()
            for hoja in hojas:
                df_h = leer_con_encabezado_correcto(contenido, hoja)
                if not detectar_formato_hospital(df_h):
                    continue
                mov_h, inv_h = transformar_formato_ancho(df_h)
                del df_h
                if mov_h is None:
                    continue
                nuevos = mov_h[~mov_h["CODIGO"].isin(cods)]
                if len(nuevos):
                    todos_mov.append(nuevos);  cods.update(nuevos["CODIGO"].unique())
                if inv_h is not None:
                    ya = {c for ie in todos_inv_e for c in ie["CODIGO"]}
                    n  = inv_h[~inv_h["CODIGO"].isin(ya)]
                    if len(n):
                        todos_inv_e.append(n)
                del mov_h, inv_h
            if not todos_mov:
                return None
            mov_df = pd.concat(todos_mov, ignore_index=True)
            del todos_mov
            ie_df  = pd.concat(todos_inv_e, ignore_index=True).drop_duplicates("CODIGO") if todos_inv_e else None
            del todos_inv_e
            prev = _df_a_preview(mov_df[["CODIGO","NOMBRE"]].drop_duplicates())
            result = {"mov": mov_df, "inv_extra": ie_df, "inv_directo": None,
                      "preview": prev, "n_productos": mov_df["CODIGO"].nunique()}
            gc.collect()
            return result
        result = {"mov": None, "inv_extra": None, "inv_directo": df_pri,
                  "preview": _df_a_preview(df_pri), "n_productos": len(df_pri)}
        return result
    except Exception:
        return None

def _recompute():
    """Combina los DataFrames ya parseados de cada archivo en inv/mov globales.
    NO re-parsea bytes (openpyxl ya corrió al subir); solo concatena DataFrames.
    """
    store    = _store_global()
    archivos = store["archivos"]
    if not archivos:
        for k in ("inv", "mov", "fuente"):
            store[k] = None
        store["formato_hospital"] = False
        return
    store["fuente"] = " + ".join(a["nombre"] for a in archivos)
    movs = [];  inv_exts = [];  inv_dirs = []
    for arec in archivos:
        if arec.get("mov")        is not None: movs.append(arec["mov"])
        if arec.get("inv_extra")  is not None: inv_exts.append(arec["inv_extra"])
        if arec.get("inv_directo") is not None: inv_dirs.append(arec["inv_directo"])
    if movs:
        mov_comb  = pd.concat(movs, ignore_index=True).drop_duplicates()
        productos = mov_comb.groupby("CODIGO").agg(NOMBRE=("NOMBRE","first")).reset_index()
        if inv_exts:
            inv_e = pd.concat(inv_exts, ignore_index=True).drop_duplicates("CODIGO")
            productos = productos.merge(inv_e, on="CODIGO", how="left")
            productos["STOCK"] = productos["STOCK_TOTAL"].fillna(0) if "STOCK_TOTAL" in productos.columns else 0
            productos["COSTO"] = productos["COSTO"].fillna(0)       if "COSTO"       in productos.columns else 0
        else:
            productos["STOCK"] = 0;  productos["COSTO"] = 0
        productos["VENCIMIENTO"] = pd.NaT
        # --- Enriquecer con datos del Inventario estándar si fue cargado junto ---
        if inv_dirs:
            _il_raw = pd.concat(inv_dirs, ignore_index=True)
            _il_raw.columns = [str(c) for c in _il_raw.columns]
            store["inv_lotes"] = _il_raw
            _il_cl = {_sin_tildes(str(c)): c for c in _il_raw.columns}
            def _find_il(kws):
                # Normaliza las palabras clave para comparar sin tildes
                kws_n = [_sin_tildes(k) for k in kws]
                # 1° coincidencia exacta  (ej: "código" == "codigo")
                for kw in kws_n:
                    for cl, co in _il_cl.items():
                        if cl == kw:
                            return co
                # 2° empieza con la palabra (ej: "código" en "codigoproducto")
                for kw in kws_n:
                    for cl, co in _il_cl.items():
                        if cl.startswith(kw):
                            return co
                # 3° contiene la palabra (ej: "código" en "matcodigo") — último recurso
                for kw in kws_n:
                    for cl, co in _il_cl.items():
                        if kw in cl:
                            return co
                return None
            _c_il_cod  = _find_il(["código", "sku", "clave"])
            _c_il_stk  = _find_il(["existencia", "stock"])
            _c_il_venc = _find_il(["fvenv", "vencimiento", "venc", "caducidad"])
            _c_il_prec = _find_il(["precio", "costo"])
            if _c_il_cod:
                _il_raw[_c_il_cod] = _il_raw[_c_il_cod].astype(str).str.strip()
                if _c_il_stk:
                    _il_raw[_c_il_stk] = pd.to_numeric(_il_raw[_c_il_stk], errors="coerce").fillna(0)
                if _c_il_venc:
                    _il_raw[_c_il_venc] = pd.to_datetime(_il_raw[_c_il_venc], dayfirst=True, errors="coerce")
                if _c_il_prec:
                    _il_raw[_c_il_prec] = pd.to_numeric(_il_raw[_c_il_prec], errors="coerce")
                _il_agg = {}
                if _c_il_stk:  _il_agg["STOCK"]           = (_c_il_stk,  "sum")
                if _c_il_venc: _il_agg["VENCIMIENTO"]      = (_c_il_venc, "min")
                if _c_il_venc: _il_agg["VENCIMIENTO_MAX"]  = (_c_il_venc, "max")
                if _c_il_prec: _il_agg["COSTO"]            = (_c_il_prec, "first")
                if _il_agg:
                    _il_grp = (_il_raw.groupby(_c_il_cod)
                                      .agg(**_il_agg)
                                      .reset_index()
                                      .rename(columns={_c_il_cod: "CODIGO"}))
                    _il_grp["CODIGO"] = _il_grp["CODIGO"].astype(str).str.strip()
                    productos["CODIGO"] = productos["CODIGO"].astype(str).str.strip()
                    # Merge con sufijos para no pisar columnas que ya existen
                    productos = productos.merge(_il_grp, on="CODIGO", how="left", suffixes=("", "_IL"))
                    # Aplicar valores del inventario con preferencia sobre los del archivo de consumos
                    for _col in list(_il_agg.keys()):
                        _col_il = _col + "_IL"
                        if _col_il in productos.columns:
                            if _col in ("VENCIMIENTO", "VENCIMIENTO_MAX"):
                                productos[_col] = productos[_col_il]
                            else:
                                productos[_col] = productos[_col_il].fillna(productos[_col].fillna(0))
                            productos.drop(columns=[_col_il], inplace=True)
                        elif _col in productos.columns and _col not in ("VENCIMIENTO", "VENCIMIENTO_MAX"):
                            productos[_col] = productos[_col].fillna(0)
        else:
            store["inv_lotes"] = None
        productos.columns = [str(c) for c in productos.columns]
        store["inv"] = productos;  store["mov"] = mov_comb;  store["formato_hospital"] = True
    elif inv_dirs:
        inv_comb = pd.concat(inv_dirs, ignore_index=True)
        inv_comb.columns = [str(c) for c in inv_comb.columns]
        store["inv"] = inv_comb;  store["mov"] = None;  store["formato_hospital"] = False
        store["inv_lotes"] = inv_comb   # en formato estándar, inv_lotes = inv
    gc.collect()

# Los DataFrames grandes (inv, mov) se leen siempre desde _store_global()
# y NUNCA se guardan en st.session_state para evitar serialización WebSocket.

# ──────────────────────────────────────────────────────────────────────────────
# ENCABEZADO DE LA APP
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-banner">
  <h1>SAVIA</h1>
  <p>Sistema de gestión y abastecimiento de medicamentos para centros de salud</p>
</div>
""", unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# SIDEBAR: CARGA DE DATOS Y PARÁMETROS
# ──────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    _s = _store_global()

    # ── Cargar datos ──────────────────────────────────────────────────────────
    st.header("Cargar datos")
    st.caption("Para selecciónar varios archivos a la vez: Cmd+clic (Mac) o Ctrl+clic (Windows).")
    archivos = st.file_uploader("Archivos Excel o CSV", type=["xlsx", "csv"],
                                accept_multiple_files=True, label_visibility="collapsed")

    # ── Detectar archivos nuevos y filtrar duplicados ─────────────────────────
    # IMPORTANTE: solo guardamos (nombre, size) en session_state, NUNCA los bytes.
    # Los bytes se leen desde `archivos` (file_uploader) en el mismo rerun donde
    # se procesan, evitando el error WebSocket de mensaje de 120+ MB.
    if archivos:
        _key = tuple(sorted((a.name, a.size) for a in archivos))
        if _key != st.session_state.get("_archivos_key"):
            st.session_state["_archivos_key"] = _key
            _ya   = {(a["nombre"], a["size"]) for a in _s["archivos"]}
            _meta = [(a.name, a.size) for a in archivos if (a.name, a.size) not in _ya]
            _dups = [a.name for a in archivos if (a.name, a.size) in _ya]
            if _dups:
                st.warning(f"Ya estaba(n) cargado(s): {', '.join(_dups)}")
            if _meta:
                st.session_state["_pendientes_meta"] = _meta   # solo nombres+tamaños
                if _s["archivos"]:
                    st.session_state["_esperando_modo"] = True
                else:
                    st.session_state["_modo_pendiente"] = "reemplazar"

    # ── Preguntar Agregar / Reemplazar ────────────────────────────────────────
    if st.session_state.get("_esperando_modo"):
        _pnames = [m[0] for m in st.session_state.get("_pendientes_meta", [])]
        _dnames = [a["nombre"] for a in _s["archivos"]]
        st.info(
            f"**Nuevo(s):** {', '.join(_pnames)}  \n"
            f"**Ya cargado(s):** {', '.join(_dnames)}"
        )
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button("Solo agregar nuevo(s)", use_container_width=True):
                st.session_state["_modo_pendiente"] = "agregar"
                st.session_state["_esperando_modo"] = False
                st.rerun()
        with _c2:
            if st.button("Reemplazar todo", use_container_width=True):
                st.session_state["_modo_pendiente"] = "reemplazar"
                st.session_state["_esperando_modo"] = False
                st.rerun()

    # ── Procesar archivos pendientes ──────────────────────────────────────────
    if st.session_state.get("_modo_pendiente") and archivos:
        _modo = st.session_state.pop("_modo_pendiente")
        _meta = st.session_state.pop("_pendientes_meta", [])
        if _modo == "reemplazar":
            _s["archivos"] = []
        # Construir mapa nombre→objeto para leer bytes ahora (sin guardarlos en session_state)
        _uploader_map = {(a.name, a.size): a for a in archivos}
        _tz_cl = pytz.timezone("America/Santiago")
        _ahora = pd.Timestamp.now(tz=_tz_cl).strftime("%Y-%m-%d %H:%M")
        _resp  = _s.get("responsable", "") or "sin especificar"
        _n_ok  = 0
        for _nom, _siz in _meta:
            _archivo = _uploader_map.get((_nom, _siz))
            if _archivo is None:
                continue
            _cont = _archivo.read()   # leer bytes aquí, sin guardar en session_state
            _rec  = _parsear_archivo(_nom, _cont)
            # Guardar bytes originales para descarga fiel (solo archivos ≤ 5 MB)
            if len(_cont) <= 5 * 1024 * 1024:
                if "archivos_bytes" not in _s:
                    _s["archivos_bytes"] = {}
                _s["archivos_bytes"][_nom] = _cont
            del _cont                 # liberar referencia local tras guardar en store
            gc.collect()
            if _rec is not None:
                _s["archivos"].append({
                    "nombre":      _nom,
                    "size":        _siz,
                    "mov":         _rec["mov"],
                    "inv_extra":   _rec["inv_extra"],
                    "inv_directo": _rec["inv_directo"],
                    "cargado_en":  _ahora,
                    "responsable": _resp,
                    "preview":     _rec["preview"],
                    "n_productos": _rec["n_productos"],
                })
                _s["historial"].append({
                    "Fecha":       _ahora,
                    "Responsable": _resp,
                    "Acción":      "Carga",
                    "Archivo":     _nom,
                    "Productos":   _rec["n_productos"],
                })
                _n_ok += 1
        gc.collect()
        _recompute()
        if _n_ok:
            st.success(f"{_n_ok} archivo(s) procesado(s) correctamente.")
            # Auto-guardar en GitHub Gist si está configurado
            if _gh_token():
                _gh_guardar_en_gist()
        else:
            st.error("No se pudo procesar ningún archivo. Verifica el formato.")

    # ── Archivos cargados ─────────────────────────────────────────────────────
    if _s["archivos"]:
        st.divider()
        st.subheader("Archivos cargados")
        for _i, _arec in enumerate(list(_s["archivos"])):
            with st.expander(f"{_arec['nombre']}  ({_arec['n_productos']} productos)"):
                _resp_str = _arec["responsable"] or "sin especificar"
                st.caption(f"Cargado: {_arec['cargado_en']}  |  Por: {_resp_str}")
                if _arec.get("preview"):
                    st.dataframe(pd.DataFrame(_arec["preview"]), use_container_width=True, hide_index=True)
                _del_key = f"_del_{_i}"
                if not st.session_state.get(_del_key):
                    if st.button("Eliminar este archivo", key=f"btn_del_{_i}",
                                 use_container_width=True):
                        st.session_state[_del_key] = True
                        st.rerun()
                else:
                    st.warning("¿Seguro que deseas eliminar este archivo?")
                    _d1, _d2 = st.columns(2)
                    with _d1:
                        if st.button("Si, eliminar", key=f"si_{_i}",
                                     use_container_width=True):
                            _eliminado = _s["archivos"].pop(_i)
                            _s["historial"].append({
                                "Fecha":       pd.Timestamp.now(tz=pytz.timezone("America/Santiago")).strftime("%Y-%m-%d %H:%M"),
                                "Responsable": _s.get("responsable", "") or "sin especificar",
                                "Acción":      "Eliminacion",
                                "Archivo":     _eliminado["nombre"],
                                "Productos":   _eliminado["n_productos"],
                            })
                            _recompute()
                            st.session_state[_del_key] = False
                            # Resetear la clave para que el uploader
                            # detecte correctamente los archivos al volver a subirlos
                            st.session_state["_archivos_key"] = None
                            st.rerun()
                    with _d2:
                        if st.button("Cancelar", key=f"no_{_i}",
                                     use_container_width=True):
                            st.session_state[_del_key] = False
                            st.rerun()

    # ── Historial de cargas ───────────────────────────────────────────────────
    if _s["historial"]:
        st.divider()
        with st.expander("Historial de cargas"):
            _hist_df = pd.DataFrame(_s["historial"]).iloc[::-1].reset_index(drop=True)
            st.dataframe(_safe_df(_hist_df), use_container_width=True, hide_index=True)

    st.divider()
    st.header("Registro")
    fecha_revision   = st.date_input("Fecha última revisión", value=_s["fecha_revision"])
    hora_revision    = st.time_input("Hora de la revisión",   value=_s["hora_revision"])
    responsable      = st.text_input("Responsable", value=_s["responsable"],
                                     placeholder="Nombre o cargo")
    st.divider()
    st.header("Parámetros configurables")
    costo_orden      = st.number_input("Costo por orden (CLP $)",           value=_s["costo_orden"],      step=1000)
    costo_mantener   = st.number_input("Costo mantener ($ / unidad / día)", value=_s["costo_mantener"],   step=1)
    lead_time        = st.number_input("Tiempo de entrega CENABAST (días)", value=float(_s["lead_time"]),        step=0.5, min_value=0.5)
    periodo_revision  = st.number_input("Período de revisión (días)",        value=float(_s["periodo_revision"]), step=0.5, min_value=0.5)
    st.divider()
    st.header("Perecibilidad")
    vida_util_dias    = st.number_input("Vida útil del producto (días)",      value=int(_s["vida_util_dias"]),    step=1,    min_value=0,
                                        help="Vida útil en días desde recepción. 0 = sin restricción de perecibilidad.")
    costo_desperdicio = st.number_input("Costo de desperdicio ($ / u vencida)", value=int(_s["costo_desperdicio"]), step=1000, min_value=0)
    beta_servicio     = float(_s.get("beta_servicio", 0.95))
    st.divider()
    st.header("Nivel de servicio")
    nivel_servicio_z  = st.number_input("Z — nivel de servicio",
                                        value=float(_s.get("nivel_servicio_z", 1.645)),
                                        step=0.001, min_value=0.5, max_value=3.5,
                                        help="Valor Z de la distribución normal. Ejemplos: 1.645 = 95%, 1.881 = 97%, 2.054 = 98%, 2.326 = 99%.")
    Z = nivel_servicio_z

_guardar_params(fecha_revision, hora_revision, responsable,
                costo_orden, costo_mantener, lead_time, periodo_revision,
                vida_util=vida_util_dias, c_desp=costo_desperdicio, beta=beta_servicio,
                z=nivel_servicio_z)


# ──────────────────────────────────────────────────────────────────────────────
# CARGA DE DATOS (función auxiliar para ejemplo)
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data
def cargar_ejemplo():
    inv = pd.read_excel("inventario_centro_salud.xlsx", sheet_name="Inventario")
    mov = pd.read_excel("inventario_centro_salud.xlsx", sheet_name="Movimientos")
    return inv, mov

_g = _store_global()
if _g["inv"] is None:
    # ── Opción de cargar desde GitHub Gist antes de pedir subida manual ──
    if _gh_token():
        _gh_gid_main = _store_global().get("gh_gist_id") or _gh_find_gist()
        if _gh_gid_main:
            st.info(
                "Se encontró un Gist de SAVIA guardado en GitHub. "
                "¿Deseas cargar los archivos automáticamente?"
            )
            _col_gh1, _col_gh2 = st.columns(2)
            with _col_gh1:
                if st.button("Cargar desde Gist", type="primary",
                             use_container_width=True, key="gh_autoload"):
                    with st.spinner("Descargando desde GitHub Gist…"):
                        _n_gh_main, _msg_gh_main = _gh_cargar_desde_gist()
                    if _n_gh_main:
                        st.success(_msg_gh_main)
                        st.rerun()
                    else:
                        st.warning(_msg_gh_main)
            with _col_gh2:
                if st.button("Subir archivo nuevo", use_container_width=True, key="gh_skip"):
                    st.info("Usa el panel izquierdo para subir tus archivos.")
            st.stop()
    st.info("Sube un archivo en el panel izquierdo")
    st.stop()

# Aviso cuando se cargó un archivo de consumos del hospital (sin stock ni vencimiento)
if _g.get("formato_hospital", False):
    if _g.get("inv_lotes") is None:
        st.info(
            "**Archivo de consumos cargado correctamente.**  \n"
            "Este tipo de archivo registra el **historial de consumo** de los medicamentos mes a mes, "
            "pero no incluye el inventario físico del establecimiento. "
            "Por eso las columnas de stock actual y fecha de vencimiento no están disponibles: "
            "esa información se lleva por separado en el registro de bodega.  \n"
            "Si tienes un archivo con las existencias actuales, puedes cargarlo adicionalmente desde el panel lateral."
        )

# Leer DataFrames directamente desde el store compartido (nunca desde session_state)
datos_inventario  = _g["inv"]
datos_movimientos = _g["mov"]
datos_inv_lotes   = _g.get("inv_lotes")  # lotes + vencimientos del archivo Inventario estándar

# Detectar columnas del archivo de lotes/vencimientos (si existe)
IL_COD  = None; IL_NOM  = None; IL_LOTE = None
IL_VENC = None; IL_STK  = None; IL_PREC = None; IL_UBIC = None
if datos_inv_lotes is not None and len(datos_inv_lotes) > 0:
    _il_usadas = set()
    IL_COD  = encontrar_columna(datos_inv_lotes, ["código", "sku", "clave"],                        _il_usadas)
    IL_NOM  = encontrar_columna(datos_inv_lotes, ["material", "nombre", "medicamento", "descripción"], _il_usadas)
    IL_LOTE = encontrar_columna(datos_inv_lotes, ["lote", "lotes", "batch", "partida"],              _il_usadas)
    IL_VENC = encontrar_columna(datos_inv_lotes, ["vencimiento", "venc", "caducidad", "expiry", "fvenv"], _il_usadas)
    IL_STK  = encontrar_columna(datos_inv_lotes, ["existencia", "stock", "cantidad", "cantporlote"], _il_usadas)
    IL_PREC = encontrar_columna(datos_inv_lotes, ["precio", "costo", "valor"],                       _il_usadas)
    IL_UBIC = encontrar_columna(datos_inv_lotes, ["ubicacion", "ubicación", "lugar", "pasillo"],     _il_usadas)

# ──────────────────────────────────────────────────────────────────────────────
# DETECCIÓN DE COLUMNAS
# Se recorre la tabla y se buscan columnas por palabras clave.
# La primera columna que coincide queda asignada y no se puede usar de nuevo.
# ──────────────────────────────────────────────────────────────────────────────
usadas_inv = set()  # rastrea qué columnas ya fueron asignadas
COL_CODIGO      = encontrar_columna(datos_inventario, ["código", "sku", "clave", "articulo", "referencia"],             usadas_inv)
COL_NOMBRE      = encontrar_columna(datos_inventario, ["nombre", "material", "medicamento", "fármaco", "descripción"],              usadas_inv)
COL_LOTE        = encontrar_columna(datos_inventario, ["lote", "batch", "partida"],                                     usadas_inv)
COL_VENCIMIENTO = encontrar_columna(datos_inventario, ["vencimiento", "vence", "caducidad", "expiry", "fec venc", "vto", "fvenv"], usadas_inv)
COL_STOCK       = encontrar_columna(datos_inventario, ["stock", "existencia", "disponible", "inventario", "saldo"],     usadas_inv)
COL_COSTO       = encontrar_columna(datos_inventario, ["costo", "cost", "precio compra", "valor compra", "precio"],     usadas_inv)
COL_MARCA       = encontrar_columna(datos_inventario, ["marca", "laboratorio", "fabricante"],                           usadas_inv)
COL_UNIDAD      = encontrar_columna(datos_inventario, ["unidad", "medida", "presentación"],                             usadas_inv)


# Si no se detectó alguna columna esencial, el usuario la elige manualmente
cols_disponibles = list(datos_inventario.columns)
if not COL_CODIGO:      COL_CODIGO      = st.selectbox("Columna de CÓDIGO:",      cols_disponibles)
if not COL_NOMBRE:      COL_NOMBRE      = st.selectbox("Columna de NOMBRE:",      cols_disponibles)
if not COL_VENCIMIENTO: COL_VENCIMIENTO = st.selectbox("Columna de VENCIMIENTO:", cols_disponibles)
if not COL_STOCK:       COL_STOCK       = st.selectbox("Columna de STOCK:",       cols_disponibles)

# Detectar columnas de movimientos (con su propio set para no mezclar con inventario)
if datos_movimientos is not None:
    usadas_mov       = set()
    COL_MOV_CODIGO   = encontrar_columna(datos_movimientos, ["código", "sku", "nombre", "medicamento"], usadas_mov)
    COL_MOV_FECHA    = encontrar_columna(datos_movimientos, ["fecha", "date", "período", "mes"],         usadas_mov)
    COL_MOV_CANTIDAD = encontrar_columna(datos_movimientos, ["dispensada", "dispensado", "demanda", "consumo", "cantidad"], usadas_mov)
    tiene_movimientos = (COL_MOV_CODIGO is not None and COL_MOV_FECHA is not None and COL_MOV_CANTIDAD is not None)
else:
    tiene_movimientos = False

# ──────────────────────────────────────────────────────────────────────────────
# PROCESAMIENTO DEL INVENTARIO
# Se convierte la tabla cruda en una versión limpia con columnas numéricas
# y se calcula cuántos días faltan para que venza cada producto.
# ──────────────────────────────────────────────────────────────────────────────
inv = datos_inventario.copy()
hoy = pd.Timestamp(date.today())

# Convertir la columna de vencimiento a formato fecha
inv[COL_VENCIMIENTO] = pd.to_datetime(inv[COL_VENCIMIENTO], dayfirst=True, errors="coerce")
# Convertir la columna de stock a número (los valores inválidos quedan en 0)
inv[COL_STOCK]       = pd.to_numeric(inv[COL_STOCK], errors="coerce").fillna(0)

# Si hay columna de costo, convertirla a número; si no, crear una columna con ceros
if COL_COSTO is not None:
    inv[COL_COSTO] = pd.to_numeric(inv[COL_COSTO], errors="coerce").fillna(0)
else:
    inv["_costo"] = 0
    COL_COSTO = "_costo"

# Calcular días que faltan para vencer y asignar estado a cada fila
inv["dias_vencer"] = (inv[COL_VENCIMIENTO] - hoy).dt.days
inv["estado"]      = inv["dias_vencer"].map(calcular_estado)

# Agrupar por medicamento (puede haber varios lotes del mismo)
# Se usa COL_STOCK para contar filas (n_lotes), ya que COL_CODIGO no puede usarse
# como clave de groupby y como columna a agregar al mismo tiempo (error de pandas)
agrupado_inv = inv.groupby([COL_CODIGO, COL_NOMBRE])
resumen = agrupado_inv.agg(
    stock_total     = (COL_STOCK,    "sum"),
    min_dias_vencer = ("dias_vencer", "min"),
    max_dias_vencer = ("dias_vencer", "max"),  # lote más fresco → aproxima vida útil real
    n_lotes         = (COL_STOCK,    "count"),
    costo_unitario  = (COL_COSTO,    "mean"),
).reset_index()
# sl_dias: días hasta el vencimiento del lote más fresco, por producto.
# Fuente prioritaria: VENCIMIENTO_MAX guardado en _recompute() desde max(FVenvimiento).
# Fallback: max_dias_vencer del agrupado (mismo valor si no hay lotes separados).
_hoy_ts = pd.Timestamp(date.today())
if "VENCIMIENTO_MAX" in datos_inventario.columns:
    _vm_map = (
        datos_inventario[[COL_CODIGO, "VENCIMIENTO_MAX"]]
        .drop_duplicates(COL_CODIGO)
        .copy()
    )
    _vm_map["VENCIMIENTO_MAX"] = pd.to_datetime(_vm_map["VENCIMIENTO_MAX"], errors="coerce")
    _vm_map["sl_dias"] = (_vm_map["VENCIMIENTO_MAX"] - _hoy_ts).dt.days.apply(
        lambda x: int(x) if pd.notna(x) and x > 0 else None
    )
    resumen = resumen.merge(_vm_map[[COL_CODIGO, "sl_dias"]], on=COL_CODIGO, how="left")
else:
    resumen["sl_dias"] = resumen["max_dias_vencer"].apply(
        lambda x: int(x) if pd.notna(x) and x > 0 else None
    )

# Agregar la columna de unidad de medida si existe
if COL_UNIDAD is not None:
    unidades = inv.groupby([COL_CODIGO, COL_NOMBRE])[COL_UNIDAD].first().reset_index()
    resumen  = resumen.merge(unidades, on=[COL_CODIGO, COL_NOMBRE], how="left")
    resumen  = resumen.rename(columns={COL_UNIDAD: "unidad"})
else:
    resumen["unidad"] = ""

# Calcular el estado de vencimiento y el valor en existencias para cada medicamento
resumen["estado"]           = resumen["min_dias_vencer"].map(calcular_estado)
resumen["valor_inventario"] = resumen["stock_total"] * resumen["costo_unitario"]

# Si el inventario del hospital tiene columnas ALCANCE y SUGERIDO, agregarlas al resumen
for col_extra in ["ALCANCE", "SUGERIDO", "STC_MIN", "STC_MAX", "STC_CRITICO", "CONS_PROM"]:
    if col_extra in datos_inventario.columns:
        col_mapa = datos_inventario[[COL_CODIGO, col_extra]].drop_duplicates(COL_CODIGO)
        resumen = resumen.merge(col_mapa, on=COL_CODIGO, how="left")

# Merge columnas BOD_* (stock por bodega) — se pierden en el groupby.agg() de arriba
_bod_extra_cols = [c for c in datos_inventario.columns if c.startswith("BOD_")]
if _bod_extra_cols:
    _bod_mapa = datos_inventario[[COL_CODIGO] + _bod_extra_cols].drop_duplicates(COL_CODIGO)
    resumen   = resumen.merge(_bod_mapa, on=COL_CODIGO, how="left")

# Si no hay existencias, la cobertura real es 0 aunque el archivo diga otra cosa
# (el ALCANCE del Programa de compras puede estar desactualizado)
for _col_cob in ["ALCANCE", "dias_cobertura", "min_dias_vencer"]:
    if _col_cob in resumen.columns:
        resumen.loc[resumen["stock_total"] == 0, _col_cob] = 0

# ──────────────────────────────────────────────────────────────────────────────
# PROCESAR MOVIMIENTOS (DEMANDA) — enfoque de tasa de llegada Poisson
#
# Lógica (equivalente al notebook de referencia):
#   1. Filtrar períodos con demanda > 0  ("pedidos")
#   2. lambda_i = demanda_i / días_desde_pedido_anterior
#   3. lambda_estable = mean(lambda_i)
#   4. Medía = ceil(lambda_estable)   [tasa diaria de la dist. Poisson]
#   5. V = min(Media, var(tamaños_de_lote))  [varianza de los lotes, no /30]
# ──────────────────────────────────────────────────────────────────────────────
if tiene_movimientos:
    mov = datos_movimientos.copy()
    mov[COL_MOV_CANTIDAD] = pd.to_numeric(mov[COL_MOV_CANTIDAD], errors="coerce").fillna(0)
    mov[COL_MOV_FECHA]    = pd.to_datetime(mov[COL_MOV_FECHA], dayfirst=True, errors="coerce")

    def _parámetros_llegada(df_prod):
        df_s    = df_prod.sort_values(COL_MOV_FECHA)
        pedidos = df_s[df_s[COL_MOV_CANTIDAD] > 0].copy()
        n       = len(pedidos)

        if n == 0:
            return pd.Series({"media_diaria": 0.0, "var_diaria": 0.0})

        batch_vals = pedidos[COL_MOV_CANTIDAD].values.astype(float)

        # Con un solo período no se puede calcular días entre llegadas → asumir 30 días
        if n == 1:
            lam   = batch_vals[0] / 30.0
            media = max(math.ceil(lam), 1)
            return pd.Series({"media_diaria": float(media), "var_diaria": float(media)})

        # Días reales entre llegadas consecutivas (se requieren fechas válidas)
        fechas = pedidos[COL_MOV_FECHA]
        if fechas.notna().all():
            dias_raw = (fechas - fechas.shift(1)).dt.days.dropna().values.astype(float)
            dias_entre = dias_raw[dias_raw > 0]
        else:
            dias_entre = np.full(n - 1, 30.0)

        if len(dias_entre) == 0:
            dias_entre = np.array([30.0])

        # Detectar datos mensuales (fechas en el día 1 del mes, gaps ~28-31 días).
        # En ese caso se aplica la misma lógica del notebook:
        #   lambda_i = demanda_mes_i / días_calendario_del_mes_i  (incluye TODOS los meses)
        # Para datos no mensuales se mantiene el enfoque de tasa inter-llegada.
        _es_mensual = (
            fechas.notna().all()
            and (fechas.dt.day == 1).all()
            and len(dias_entre) > 0
            and float(dias_entre.mean()) <= 32
        )
        if _es_mensual:
            _dias_mes = fechas.apply(
                lambda d: float(calendar.monthrange(d.year, d.month)[1])
            ).values
            lambdas = batch_vals / _dias_mes   # incluye el primer mes (igual que notebook)
        else:
            # lambda_i = demanda_i / días_desde_pedido_anterior
            k       = min(len(dias_entre), n - 1)
            lambdas = batch_vals[1: k + 1] / dias_entre[:k]

        lambda_estable = lambdas.mean()
        if lambda_estable <= 0 or np.isnan(lambda_estable):
            return pd.Series({"media_diaria": 0.0, "var_diaria": 0.0})

        media     = math.ceil(lambda_estable)
        var_diaria = float(pd.Series(lambdas).var())   # var de tasas diarias, igual que notebook
        if np.isnan(var_diaria) or var_diaria <= 0:
            var_diaria = float(media)
        V = min(float(media), var_diaria)

        return pd.Series({"media_diaria": float(media), "var_diaria": V})

    # Calcular parámetros para cada producto sin deprecaciones de pandas 2.x
    filas_params = []
    for codigo_p, df_grupo in mov.groupby(COL_MOV_CODIGO):
        params = _parámetros_llegada(df_grupo)
        filas_params.append({
            COL_CODIGO:      codigo_p,
            "media_diaria":  params["media_diaria"],
            "var_diaria":    params["var_diaria"],
        })
    tabla_parámetros = pd.DataFrame(filas_params)

    resumen = resumen.merge(tabla_parámetros, on=COL_CODIGO, how="left")
    resumen["media_diaria"]   = resumen["media_diaria"].fillna(0)
    resumen["var_diaria"]     = resumen["var_diaria"].fillna(0)
    resumen["dias_cobertura"] = (resumen["stock_total"] / resumen["media_diaria"].replace(0, np.nan)).round(1)
else:
    resumen["media_diaria"]   = 0
    resumen["var_diaria"]     = 0
    resumen["dias_cobertura"] = None

# ──────────────────────────────────────────────────────────────────────────────
# KPIs GLOBALES
# ──────────────────────────────────────────────────────────────────────────────
valor_total   = resumen["valor_inventario"].sum()
n_vencidos    = (resumen["estado"] == "VENCIDO").sum()
n_criticos    = (resumen["estado"] == "CRITICO").sum()
n_advertencia = (resumen["estado"] == "ADVERTENCIA").sum()
n_normales    = (resumen["estado"] == "NORMAL").sum()

# KPIs adicionales para formato hospital (basados en ALCANCE y SUGERIDO)
formato_hospital = _store_global().get("formato_hospital", False)
if formato_hospital:
    tiene_alcance  = "ALCANCE"  in resumen.columns
    tiene_sugerido = "SUGERIDO" in resumen.columns
    if tiene_alcance:
        alcance_num = pd.to_numeric(resumen["ALCANCE"], errors="coerce")
        n_sin_stock    = int((resumen["stock_total"] == 0).sum())
        n_cob_critica  = int(((alcance_num > 0) & (alcance_num <= 1)).sum())   # ≤ 1 mes
        n_cob_baja     = int(((alcance_num > 1) & (alcance_num <= 3)).sum())   # 1-3 meses
        n_cob_ok       = int((alcance_num > 3).sum())                          # > 3 meses
    if tiene_sugerido:
        sugerido_num   = pd.to_numeric(resumen["SUGERIDO"], errors="coerce").fillna(0).clip(lower=0)
        n_pedir_ahora  = int((sugerido_num > 0).sum())
        valor_pedido   = float((sugerido_num * resumen["costo_unitario"]).sum())

# ──────────────────────────────────────────────────────────────────────────────
# TABS
# ──────────────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs([
    "Panel Principal",
    "Seguimiento",
    "Planificación",
])

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 1 — PANEL PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    # _estado_cob requerido por tab2; se calcula en cada rerun
    if formato_hospital:
        _alc_all = pd.to_numeric(resumen.get("ALCANCE", pd.Series(dtype=float)), errors="coerce")
        _sug_all = pd.to_numeric(resumen.get("SUGERIDO", pd.Series(dtype=float)), errors="coerce").fillna(0)
        def _clasificar_cob(row, alc):
            if row["stock_total"] == 0:        return "Sin existencias"
            if not pd.isna(alc) and alc <= 1:  return "Crítico (≤1 mes)"
            if not pd.isna(alc) and alc <= 3:  return "Bajo (1–3 meses)"
            if not pd.isna(alc) and alc > 3:   return "Adecuado (>3 meses)"
            return "Sin datos"
        resumen["_estado_cob"]      = [_clasificar_cob(resumen.iloc[i], _alc_all.iloc[i]) for i in range(len(resumen))]
        resumen["_requiere_pedido"] = _sug_all > 0

    # ── Datos auxiliares ──────────────────────────────────────────────────────
    PALETA = {"sin_stock": "#E53E3E", "crítico": "#DD6B20", "bajo": "#D69E2E",
              "adecuado": "#38A169", "normal": "#3182CE", "gris": "#94a3b8"}

    _tiene_alc = formato_hospital and "ALCANCE" in resumen.columns
    if _tiene_alc:
        _alc_sem   = pd.to_numeric(resumen["ALCANCE"], errors="coerce")
        _sem_rojo  = int((resumen["stock_total"] == 0).sum() + ((_alc_sem > 0) & (_alc_sem <= 1)).sum())
        _sem_amari = int(((_alc_sem > 1) & (_alc_sem <= 3)).sum())
        _sem_verde = int((_alc_sem > 3).sum())
    else:
        _sem_rojo  = int(n_vencidos + n_criticos)
        _sem_amari = int(n_advertencia)
        _sem_verde = int(n_normales)

    _valor_vencido = float(resumen[resumen["estado"] == "VENCIDO"]["valor_inventario"].sum())
    _pct_perdida   = round(_valor_vencido / valor_total * 100, 1) if valor_total > 0 else 0.0
    _n_quiebre     = int((resumen["stock_total"] == 0).sum())
    _n_prox_ven    = int(n_criticos + n_advertencia)

    _dias_rev = (date.today() - fecha_revision).days
    _prox_rev = fecha_revision + timedelta(days=int(periodo_revision))
    _resp_str = responsable if responsable else "No especificado"
    if _dias_rev <= periodo_revision:
        _dot_color = "#38A169"
    elif _dias_rev <= periodo_revision * 2:
        _dot_color = "#D69E2E"
    else:
        _dot_color = "#E53E3E"

    # ── 1. Banner ─────────────────────────────────────────────────────────────
    _n_crit_b = _sem_rojo  if _tiene_alc else int(n_vencidos + n_criticos)
    _n_adv_b  = _sem_amari if _tiene_alc else int(n_advertencia)
    if _n_crit_b > 0:
        _bn_bg, _bn_border, _bn_color = "#FED7D7", "#E53E3E", "#C53030"
        _bn_label = "ALERTA CRITICA"
        _bn_msg   = f"{_n_crit_b} medicamento(s) vencido(s) o con vencimiento crítico (menos de 30 días)"
    elif _n_adv_b > 0:
        _bn_bg, _bn_border, _bn_color = "#FEFCBF", "#D69E2E", "#B7791F"
        _bn_label = "ADVERTENCIA"
        _bn_msg   = f"{_n_adv_b} medicamento(s) con vencimiento próximo (31 a 90 días)"
    else:
        _bn_bg, _bn_border, _bn_color = "#C6F6D5", "#38A169", "#276749"
        _bn_label = "ESTADO OK"
        _bn_msg   = "Sin alertas de vencimiento activas. Todos los medicamentos se encuentran dentro del rango normal."

    st.markdown(f"""
    <div style="background:{_bn_bg};border-left:6px solid {_bn_border};border-radius:10px;
                padding:12px 22px;margin-bottom:16px;display:flex;align-items:center;gap:12px;">
      <span style="font-weight:700;font-size:0.78rem;color:{_bn_color};text-transform:uppercase;
                   letter-spacing:0.06em;white-space:nowrap">{_bn_label}</span>
      <span style="color:#1a202c;font-size:0.9rem">{_bn_msg}</span>
    </div>
    """, unsafe_allow_html=True)

    # ── 2. Fila superior: 3 items de revisión + Valor total grande + 2 KPIs ────
    def _info_card(label, value, sub, border="#3182CE"):
        return (
            f'<div style="background:white;border-radius:12px;padding:12px 16px;'
            f'box-shadow:0 1px 3px rgba(0,0,0,0.07);border-left:4px solid {border};">'
            f'<div style="font-size:0.63rem;color:#64748b;font-weight:600;'
            f'text-transform:uppercase;margin-bottom:3px">{label}</div>'
            f'<div style="font-size:0.96rem;font-weight:700;color:#0f172a">{value}</div>'
            f'<div style="font-size:0.65rem;color:#94a3b8;margin-top:2px">{sub}</div>'
            f'</div>'
        )

    _fi1, _fi2, _fi3, _fi4, _fi5, _fi6 = st.columns([1, 1, 1, 1.7, 1, 1])

    _fi1.markdown(_info_card(
        "Última revisión",
        fecha_revision.strftime("%d/%m/%Y"),
        f"Hace {_dias_rev} día(s)"
    ), unsafe_allow_html=True)

    _prox_dot = (f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
                 f'background:{_dot_color};margin-right:4px;vertical-align:middle"></span>')
    _fi2.markdown(_info_card(
        "Próxima revisión",
        f"{_prox_dot}{_prox_rev.strftime('%d/%m/%Y')}",
        f"En {periodo_revision} días"
    ), unsafe_allow_html=True)

    _fi3.markdown(_info_card("Responsable", _resp_str, "&nbsp;"), unsafe_allow_html=True)

    with _fi4:
        st.markdown(f"""
        <div style="background:white;border-radius:12px;padding:12px 18px;
                    box-shadow:0 1px 3px rgba(0,0,0,0.07);border-left:4px solid #38A169;
                    text-align:center;">
          <div style="font-size:0.63rem;color:#64748b;font-weight:600;
                      text-transform:uppercase;margin-bottom:4px">Valor total en existencias</div>
          <div style="font-size:1.55rem;font-weight:800;color:#0f172a;line-height:1.15">
            ${valor_total:,.0f}
          </div>
          <div style="font-size:0.7rem;color:#64748b;font-weight:500">CLP</div>
        </div>
        """, unsafe_allow_html=True)

    _fi5.metric("Total productos",  f"{_m(len(resumen))}",
                help="Cantidad de medicamentos distintos actualmente en el inventario.")
    if formato_hospital and datos_inv_lotes is None:
        # Solo consumos: sin datos de vencimiento → mostrar quiebres de stock
        _fi6.metric(
            "Sin existencias",
            f"{_m(_n_quiebre)}",
            delta=f"{_n_quiebre / len(resumen) * 100:.1f}% del total" if len(resumen) else None,
            delta_color="off",
            help="Cantidad de medicamentos con stock igual a cero. "
                 "El archivo cargado no contiene datos de vencimiento.",
        )
    else:
        _vv_fmt = (f"${_valor_vencido/1_000_000:.1f}M" if _valor_vencido >= 1_000_000
                   else f"${_valor_vencido/1_000:.0f}K"  if _valor_vencido >= 100_000
                   else f"${_valor_vencido:,.0f}")
        _fi6.metric(
            "Valor vencido",
            f"{_vv_fmt} CLP" if _valor_vencido > 0 else "$0 CLP",
            delta=f"{_pct_perdida:.1f}% del inventario" if _valor_vencido > 0 else "Sin vencidos registrados",
            delta_color="off",
            help="Valor económico (en pesos chilenos) de los medicamentos cuya fecha de vencimiento ya superó la fecha actual. "
                 "Representa pérdida directa de recursos del establecimiento.",
        )

    st.markdown("<div style='margin:12px 0'></div>", unsafe_allow_html=True)

    # ── 3. Semáforo — un círculo por estado ──────────────────────────────────
    st.markdown(_ayuda(
        "<b>Semáforo de cobertura</b> — Cada círculo muestra cuántos medicamentos se encuentran en ese estado. "
        "<span style='color:#E53E3E;font-weight:700'>Rojo</span> = sin existencias o vencidos (acción inmediata). "
        "<span style='color:#DD6B20;font-weight:700'>Naranja</span> = cobertura crítica, menos de 1 mes de existencias. "
        "<span style='color:#D69E2E;font-weight:700'>Amarillo</span> = cobertura baja, entre 1 y 3 meses. "
        "<span style='color:#38A169;font-weight:700'>Verde</span> = cobertura adecuada, más de 3 meses."
    ), unsafe_allow_html=True)
    if _tiene_alc:
        _alc_s2 = pd.to_numeric(resumen["ALCANCE"], errors="coerce")
        _sem_items = [
            (int((resumen["stock_total"] == 0).sum()),                          "#E53E3E", "Sin existencias"),
            (int(((_alc_s2 > 0) & (_alc_s2 <= 1)).sum()),                      "#DD6B20", "Cobertura crítica (≤1 mes)"),
            (int(((_alc_s2 > 1) & (_alc_s2 <= 3)).sum()),                      "#D69E2E", "Cobertura baja (1–3 meses)"),
            (int((_alc_s2 > 3).sum()),                                          "#38A169", "Cobertura adecuada (>3 meses)"),
        ]
    else:
        _sem_items = [
            (int(n_vencidos),    "#E53E3E", "Vencidos"),
            (int(n_criticos),    "#DD6B20", "Vencimiento crítico (<30 días)"),
            (int(n_advertencia), "#D69E2E", "Vencimiento próximo (31–90 días)"),
            (int(n_normales),    "#38A169", "Existencias adecuadas"),
        ]

    _circles = ""
    for _cnt, _clr, _lbl_s in _sem_items:
        _r, _g, _b = int(_clr[1:3], 16), int(_clr[3:5], 16), int(_clr[5:7], 16)
        _circles += (
            f'<div style="text-align:center;">'
            f'<div style="width:84px;height:84px;border-radius:50%;background:{_clr};display:flex;'
            f'align-items:center;justify-content:center;margin:0 auto 8px;'
            f'box-shadow:0 4px 12px rgba({_r},{_g},{_b},0.35);">'
            f'<span style="font-size:1.6rem;font-weight:800;color:white">{_cnt}</span>'
            f'</div>'
            f'<div style="font-size:0.73rem;color:#4A5568;font-weight:600;'
            f'max-width:105px;line-height:1.35">{_lbl_s}</div>'
            f'</div>'
        )

    st.markdown(
        f'<div style="display:flex;justify-content:center;gap:36px;background:white;'
        f'border-radius:14px;padding:20px 0;box-shadow:0 1px 4px rgba(0,0,0,0.07);'
        f'margin-bottom:20px;">{_circles}</div>',
        unsafe_allow_html=True
    )

    # ── 4. Contenido principal: [donut interactivo + tabla | top 10 + alertas] ─
    _col_L, _col_R = st.columns([55, 45])

    with _col_L:
        # Datos del donut
        if formato_hospital and _tiene_alc:
            _alc_n  = pd.to_numeric(resumen["ALCANCE"], errors="coerce")
            _cats_d = ["Sin existencias", "Crítica (<1 mes)", "Baja (1–3 meses)", "Adecuada (>3 meses)"]
            _cont_d = [
                int((resumen["stock_total"] == 0).sum()),
                int(((_alc_n > 0) & (_alc_n <= 1)).sum()),
                int(((_alc_n > 1) & (_alc_n <= 3)).sum()),
                int((_alc_n > 3).sum()),
            ]
            _col_d = [PALETA["sin_stock"], PALETA["crítico"], PALETA["bajo"], PALETA["adecuado"]]
            _cat_map = {
                "Sin existencias":     "Sin existencias",
                "Crítica (<1 mes)":    "Crítico (≤1 mes)",
                "Baja (1–3 meses)":    "Bajo (1–3 meses)",
                "Adecuada (>3 meses)": "Adecuado (>3 meses)",
            }
        else:
            _orden_e = ["VENCIDO", "CRITICO", "ADVERTENCIA", "NORMAL", "Sin fecha"]
            _vc      = resumen["estado"].value_counts()
            _cats_d  = [e for e in _orden_e if e in _vc.index]
            _cont_d  = [int(_vc[e]) for e in _cats_d]
            _col_map_e = {"VENCIDO": PALETA["sin_stock"], "CRITICO": PALETA["crítico"],
                          "ADVERTENCIA": PALETA["bajo"], "NORMAL": PALETA["adecuado"],
                          "Sin fecha": PALETA["gris"]}
            _col_d   = [_col_map_e.get(e, PALETA["gris"]) for e in _cats_d]
            _cat_map = None

        # Selector de estado (con "Todos")
        _opts = ["Todos"] + _cats_d
        _sel  = st.radio("Cobertura de existencias — filtrar por estado:",
                         _opts, horizontal=True, key="donut_filter")

        # Donut con slice resaltado
        _pull = [0.09 if c == _sel else 0 for c in _cats_d]
        _fig_pie = go.Figure(go.Pie(
            labels=_cats_d, values=_cont_d, marker_colors=_col_d, pull=_pull,
            textinfo="percent+value", hole=0.45,
            hovertemplate="<b>%{label}</b><br>%{value} productos (%{percent})<extra></extra>",
        ))
        _fig_pie.update_layout(
            height=270, margin=dict(t=6, b=0, l=6, r=6),
            legend=dict(orientation="h", y=-0.14, font=dict(size=11)),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(_fig_pie, use_container_width=True)
        st.caption("Haz clic en una categoría del gráfico para filtrar la tabla de productos por ese estado.")

        # Tabla filtrada por estado selecciónado
        if _sel != "Todos":
            if formato_hospital and _cat_map and "_estado_cob" in resumen.columns:
                _cob_val  = _cat_map.get(_sel, _sel)
                _tbl_filt = resumen[resumen["_estado_cob"] == _cob_val].copy()
            else:
                _tbl_filt = resumen[resumen["estado"] == _sel].copy()

            _c_show = [COL_CODIGO, COL_NOMBRE, "stock_total"]
            if not formato_hospital or datos_inv_lotes is not None:
                for _c in ["min_dias_vencer", "estado"]:
                    if _c in _tbl_filt.columns: _c_show.append(_c)
            if formato_hospital:
                for _c in ["ALCANCE", "SUGERIDO"]:
                    if _c in _tbl_filt.columns: _c_show.append(_c)
            _c_show   = [c for c in _c_show if c in _tbl_filt.columns]
            _tbl_show = _tbl_filt[_c_show].rename(columns={
                COL_CODIGO: "Código", COL_NOMBRE: "Medicamento",
                "stock_total": "Existencias", "min_dias_vencer": "Días p/Vencer",
                "estado": "Estado", "ALCANCE": "Cobertura (meses)", "SUGERIDO": "Cant. sugerida",
            }).reset_index(drop=True)
            st.caption(f"{len(_tbl_show)} producto(s) en estado '{_sel}'")
            st.dataframe(_safe_df(_tbl_show), use_container_width=True, hide_index=True, height=260)
        else:
            # Sin filtro: mostrar top 10 más urgentes (sin stock → más días vencidos)
            if not formato_hospital:
                _urg = resumen[resumen["estado"].isin(["VENCIDO", "CRITICO"])].head(10)
            elif "_estado_cob" in resumen.columns:
                _urg = resumen[resumen["_estado_cob"].isin(["Sin existencias", "Crítico (≤1 mes)"])].head(10)
            else:
                _urg = pd.DataFrame()
            if len(_urg) > 0:
                _uc = [COL_CODIGO, COL_NOMBRE, "stock_total"]
                if "min_dias_vencer" in _urg.columns and (not formato_hospital or datos_inv_lotes is not None): _uc.append("min_dias_vencer")
                if "ALCANCE" in _urg.columns: _uc.append("ALCANCE")
                _uc = [c for c in _uc if c in _urg.columns]
                _urg_show = _urg[_uc].rename(columns={
                    COL_CODIGO: "Código", COL_NOMBRE: "Medicamento",
                    "stock_total": "Existencias", "min_dias_vencer": "Días p/Vencer",
                    "ALCANCE": "Cobertura (meses)",
                }).reset_index(drop=True)
                st.caption("Productos sin existencias / más urgentes")
                st.dataframe(_safe_df(_urg_show), use_container_width=True, hide_index=True, height=220)

    with _col_R:
        # Top 10 consumo mensual
        if tiene_movimientos:
            _top10 = resumen[resumen["media_diaria"] > 0].nlargest(10, "media_diaria").copy()
            _top10["consumo_mensual"] = (_top10["media_diaria"] * 30).round(0)
            _n10  = len(_top10)
            _noms = [n[:30] + "…" if len(n) > 30 else n for n in _top10[COL_NOMBRE]]
            _cb   = [f"rgba(49,130,206,{1 - i * 0.06})" for i in range(_n10)]
            _lb   = [f"{_m(int(v))}" for v in _top10["consumo_mensual"]]
            _fig_bar = go.Figure(go.Bar(
                x=_top10["consumo_mensual"], y=_noms,
                orientation="h", marker_color=_cb, text=_lb, textposition="outside",
                hovertemplate="<b>%{y}</b><br>%{x:,} u/mes<extra></extra>",
            ))
            _fig_bar.update_layout(
                title=dict(text="Top 10 — Mayor consumo mensual", font=dict(size=13, color="#0f172a")),
                height=290, margin=dict(t=32, b=8, l=8, r=50),
                xaxis_title="Unidades / mes", yaxis=dict(autorange="reversed"),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(_fig_bar, use_container_width=True)
            st.caption("Consumo promedio mensual estimado a partir del historial de movimientos. Permite identificar qué medicamentos ejercen mayor presión sobre el inventario.")
        else:
            st.info("Sube el archivo de movimientos para ver el consumo mensual.")

        # ── Valor económico del inventario por estado ──────────────────────────
        if formato_hospital and "_estado_cob" in resumen.columns:
            _vc_col = "_estado_cob"
            _vc_pal = {
                "Sin existencias":     "#E53E3E",
                "Crítico (≤1 mes)":    "#DD6B20",
                "Bajo (1–3 meses)":    "#D69E2E",
                "Adecuado (>3 meses)": "#38A169",
            }
        elif "estado" in resumen.columns:
            _vc_col = "estado"
            _vc_pal = {
                "VENCIDO":     "#E53E3E",
                "CRITICO":     "#DD6B20",
                "ADVERTENCIA": "#D69E2E",
                "NORMAL":      "#38A169",
            }
        else:
            _vc_col = None
            _vc_pal = {}

        if _vc_col:
            _tiene_costo = (
                "costo_unitario" in resumen.columns and
                pd.to_numeric(resumen["costo_unitario"], errors="coerce").fillna(0).sum() > 0
            )
            if _tiene_costo:
                _res_vc = resumen.copy()
                _res_vc["_valor"] = (
                    pd.to_numeric(_res_vc["stock_total"],   errors="coerce").fillna(0) *
                    pd.to_numeric(_res_vc["costo_unitario"], errors="coerce").fillna(0)
                )
                _vc_df = (
                    _res_vc.groupby(_vc_col)["_valor"].sum()
                    .reset_index()
                    .rename(columns={_vc_col: "Estado", "_valor": "Valor"})
                )
                # Quitar estados con valor 0 (ej. Sin existencias — obvio que es $0)
                _vc_df = _vc_df[_vc_df["Valor"] > 0]
                # Orden del semáforo: de peor a mejor (izq → der)
                _vc_orden = {"Sin existencias": 0, "Crítico (≤1 mes)": 1,
                             "Bajo (1–3 meses)": 2, "Adecuado (>3 meses)": 3,
                             "VENCIDO": 0, "CRITICO": 1, "ADVERTENCIA": 2, "NORMAL": 3}
                _vc_df["_ord"] = _vc_df["Estado"].map(_vc_orden).fillna(9)
                _vc_df = _vc_df.sort_values("_ord").reset_index(drop=True)
                _vc_title = "Valor del inventario por estado (CLP)"
                def _fmt_clp(v):
                    if v >= 1_000_000_000: return f"${v/1_000_000_000:.1f}B"
                    if v >= 1_000_000:     return f"${v/1_000_000:.1f}M"
                    return f"${v:,.0f}"
                _vc_fmt   = [_fmt_clp(v) for v in _vc_df["Valor"]]
                _vc_hover = "<b>%{x}</b><br>$%{y:,.0f} CLP<extra></extra>"
            else:
                # Fallback: unidades en stock por estado
                _vc_df = (
                    resumen.groupby(_vc_col)["stock_total"].sum()
                    .reset_index()
                    .rename(columns={_vc_col: "Estado", "stock_total": "Valor"})
                )
                _vc_df = _vc_df[_vc_df["Valor"] > 0]
                _vc_orden = {"Sin existencias": 0, "Crítico (≤1 mes)": 1,
                             "Bajo (1–3 meses)": 2, "Adecuado (>3 meses)": 3,
                             "VENCIDO": 0, "CRITICO": 1, "ADVERTENCIA": 2, "NORMAL": 3}
                _vc_df["_ord"] = _vc_df["Estado"].map(_vc_orden).fillna(9)
                _vc_df = _vc_df.sort_values("_ord").reset_index(drop=True)
                _vc_title = "Unidades en existencias por estado"
                _vc_fmt   = [f"{_m(int(v))}" for v in _vc_df["Valor"]]
                _vc_hover = "<b>%{x}</b><br>%{y:,} unidades<extra></extra>"

            _vc_colors = [_vc_pal.get(e, "#A0AEC0") for e in _vc_df["Estado"]]
            _fig_vc = go.Figure(go.Bar(
                x=_vc_df["Estado"], y=_vc_df["Valor"],
                marker_color=_vc_colors,
                text=_vc_fmt, textposition="outside",
                cliponaxis=False,
                hovertemplate=_vc_hover,
            ))
            _fig_vc.update_layout(
                title=dict(text=_vc_title, font=dict(size=13, color="#0f172a")),
                height=310, margin=dict(t=36, b=8, l=8, r=8),
                yaxis=dict(showticklabels=False, range=[0, _vc_df["Valor"].max() * 1.22]),
                xaxis=dict(tickfont=dict(size=11)),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(_fig_vc, use_container_width=True)
            st.caption("Muestra cuánto dinero (CLP) representa cada categoría del semáforo. Las barras más altas en rojo/naranja indican mayor riesgo económico por productos en estado crítico.")


    # ── 5. Resumen por estado (formato hospital) ──────────────────────────────
    if formato_hospital and "_estado_cob" in resumen.columns:
        _alc_all2 = pd.to_numeric(resumen.get("ALCANCE",  pd.Series(dtype=float)), errors="coerce")
        _sug_all2 = pd.to_numeric(resumen.get("SUGERIDO", pd.Series(dtype=float)), errors="coerce").fillna(0)

        st.divider()
        st.subheader("Resumen por estado")

        _est_opc  = ["Sin existencias", "Crítico (≤1 mes)", "Bajo (1–3 meses)", "Adecuado (>3 meses)"]
        _est_disp = [e for e in _est_opc if e in resumen["_estado_cob"].values]
        _est_def  = [e for e in ["Sin existencias", "Crítico (≤1 mes)"] if e in _est_disp]

        _est_sel = st.multiselect(
            "Seleccionar estados a visualizar:",
            _est_disp, default=_est_def, key="kpi_estados"
        )

        # Colorear chips del multiselect según el estado
        _components.html("""
<script>
(function() {
  var cfg = {
    'Sin existencias':     {bg:'#FED7D7', fg:'#C53030', border:'#E53E3E'},
    'Crítico (≤1 mes)': {bg:'#FEEBC8', fg:'#C05621', border:'#DD6B20'},
    'Bajo (1–3 meses)':  {bg:'#FEFCBF', fg:'#B7791F', border:'#D69E2E'},
    'Adecuado (>3 meses)':{bg:'#C6F6D5', fg:'#276749', border:'#38A169'}
  };
  function paint() {
    var tags = window.parent.document.querySelectorAll('[data-baseweb="tag"]');
    tags.forEach(function(tag) {
      var txt = tag.innerText || tag.textContent || '';
      txt = txt.replace(/×/g,'').trim();
      for (var k in cfg) {
        if (txt.indexOf(k) !== -1) {
          tag.style.background    = cfg[k].bg;
          tag.style.borderColor   = cfg[k].border;
          tag.style.color         = cfg[k].fg;
          tag.querySelectorAll('span').forEach(function(s){
            s.style.color = cfg[k].fg;
          });
          break;
        }
      }
    });
  }
  paint();
  setTimeout(paint, 200);
  setTimeout(paint, 600);
  new MutationObserver(paint).observe(
    window.parent.document.body,
    {childList:true, subtree:true, attributes:true}
  );
})();
</script>
""", height=0)

        if _est_sel:
            _df_sel  = resumen[resumen["_estado_cob"].isin(_est_sel)]
            _n_prod  = len(_df_sel)
            _n_pedir = int((_sug_all2[_df_sel.index] > 0).sum())
            _val_sel = float((_df_sel["stock_total"] * _df_sel["costo_unitario"]).sum()) if "costo_unitario" in _df_sel.columns else 0
            _val_ped = float((_sug_all2[_df_sel.index] * _df_sel["costo_unitario"]).sum()) if "costo_unitario" in _df_sel.columns else 0

            _rk1, _rk2, _rk3, _rk4 = st.columns(4)
            _rk1.metric("Productos en estado selecciónado", f"{_m(_n_prod)}")
            _rk2.metric("Requieren pedido",                 f"{_m(_n_pedir)}")
            _rk3.metric("Valor en existencias (selección)", f"${_val_sel:,.0f} CLP")
            _rk4.metric("Valor estimado a pedir",           f"${_val_ped:,.0f} CLP")

            _desglose = _df_sel.groupby("_estado_cob").agg(
                Productos=("stock_total", "count"),
                Unidades_totales=("stock_total", "sum"),
            ).reset_index().rename(columns={"_estado_cob": "Estado"})

            _badge_cfg = {
                "Sin existencias":     ("#FED7D7", "#C53030"),
                "Crítico (≤1 mes)":    ("#FEEBC8", "#C05621"),
                "Bajo (1–3 meses)":    ("#FEFCBF", "#B7791F"),
                "Adecuado (>3 meses)": ("#C6F6D5", "#276749"),
                "Sin datos":           ("#EDF2F7", "#718096"),
            }
            _tbl_html = (
                '<table style="width:100%;border-collapse:collapse;font-size:0.85rem;">'
                '<thead><tr style="background:#f8fafc;border-bottom:2px solid #e2e8f0;">'
                '<th style="padding:8px 12px;text-align:left;color:#64748b;font-weight:600">Estado</th>'
                '<th style="padding:8px 12px;text-align:right;color:#64748b;font-weight:600">Productos</th>'
                '<th style="padding:8px 12px;text-align:right;color:#64748b;font-weight:600">Unidades totales</th>'
                '</tr></thead><tbody>'
            )
            for _, _drow in _desglose.iterrows():
                _bg, _fg = _badge_cfg.get(_drow["Estado"], ("#EDF2F7", "#718096"))
                _badge = (f'<span style="background:{_bg};color:{_fg};border-radius:4px;'
                          f'padding:2px 9px;font-weight:600;font-size:0.78rem">{_drow["Estado"]}</span>')
                _tbl_html += (
                    f'<tr style="border-bottom:1px solid #e2e8f0;">'
                    f'<td style="padding:8px 12px">{_badge}</td>'
                    f'<td style="padding:8px 12px;text-align:right;font-weight:600">{_m(int(_drow["Productos"]))}</td>'
                    f'<td style="padding:8px 12px;text-align:right">{_m(int(_drow["Unidades_totales"]))}</td>'
                    f'</tr>'
                )
            _tbl_html += '</tbody></table>'
            st.markdown(_tbl_html, unsafe_allow_html=True)
        else:
            st.info("Selecciona al menos un estado para ver los KPIs.")

    # ── Diagrama: ciclo de vida de un lote ───────────────────────────────────
    st.divider()
    st.markdown("#### Flujo del ciclo de vida de un lote")
    # Nodos: (x, y, etiqueta, color_fondo, color_texto)
    # Después de Bodega el lote puede tener 3 destinos posibles
    _NODES_P1 = [
        (0.5, 2.2, "Pedido OC",              "#3182CE", "white"),   # 0
        (2.0, 2.2, "Llegada",                "#3182CE", "white"),   # 1
        (3.5, 2.2, "Control de\nCalidad",    "#3182CE", "white"),   # 2
        (5.0, 3.0, "Aprobado",               "#38A169", "white"),   # 3
        (6.5, 3.0, "Bodega",                 "#38A169", "white"),   # 4
        (8.0, 3.7, "Entrega al\npaciente",   "#276749", "white"),   # 5  ← destino 1
        (8.0, 3.0, "Bodega\nsecundaria",     "#276749", "white"),   # 6  ← destino 2
        (8.0, 2.3, "Despacho a\notra bodega","#276749", "white"),   # 7  ← destino 3
        (5.0, 1.4, "Rechazado",              "#C53030", "white"),   # 8
        (6.5, 1.4, "Reg. Pérdida",           "#C53030", "white"),   # 9
        (8.0, 1.4, "Desecho",                "#742A2A", "white"),   # 10
    ]
    # Aristas: (desde, hasta)
    _EDGES_P1 = [
        (0,1),(1,2),           # Pedido OC → Llegada → Control de Calidad
        (2,3),(3,4),           # → Aprobado → Bodega
        (4,5),(4,6),(4,7),     # Bodega → 3 destinos posibles
        (2,8),(8,9),(9,10),    # Control de Calidad → Rechazado → Reg. Pérdida → Desecho
    ]
    _fig_flow_p1 = go.Figure()
    for (_x1,_y1,_,_,_), (_x2,_y2,_,_,_) in [(_NODES_P1[a], _NODES_P1[b]) for a,b in _EDGES_P1]:
        _fig_flow_p1.add_trace(go.Scatter(
            x=[_x1+0.5, _x2-0.5], y=[_y1, _y2],
            mode="lines", line=dict(color="#A0AEC0", width=2),
            showlegend=False, hoverinfo="skip",
        ))
    for _nx,_ny,_nlbl,_nc,_ntc in _NODES_P1:
        _fig_flow_p1.add_shape(type="rect",
            x0=_nx-0.48, y0=_ny-0.32, x1=_nx+0.48, y1=_ny+0.32,
            fillcolor=_nc, line_color=_nc, line_width=0, layer="above",
        )
        _fig_flow_p1.add_annotation(x=_nx, y=_ny, text=_nlbl.replace("\n","<br>"),
            showarrow=False, font=dict(size=10, color=_ntc), align="center",
        )
    _fig_flow_p1.update_layout(
        height=260, margin=dict(t=10, b=10, l=10, r=10),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.1, 8.6]),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.9, 4.1]),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    )
    st.plotly_chart(_fig_flow_p1, use_container_width=True)
    st.caption("Flujo del ciclo de vida de un lote: tras pasar el control de calidad, el lote se almacena en bodega y puede destinarse a la entrega directa al paciente, quedarse en la bodega central o despacharse a otra bodega del establecimiento.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — INVENTARIO Y PRONÓSTICO
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    _t2_bod, _t2_inv, _t2_venc, _t2_det = st.tabs([
        "Existencias por Bodega",
        "Inventario",
        "Vencimientos",
        "Detalle por Medicamento",
    ])

    # ══════════════════════════════════════════════════════════════════════════
    # SUB-TAB 0 — STOCK Y BODEGA
    # ══════════════════════════════════════════════════════════════════════════
    with _t2_bod:
        _bod_cols = [c for c in resumen.columns if c.startswith("BOD_")]

        if not _bod_cols:
            st.markdown(
                '<div style="background:#EBF8FF;border-left:4px solid #3182CE;border-radius:8px;'
                'padding:18px 22px;margin:12px 0">'
                '<div style="font-size:0.88rem;font-weight:700;color:#2B6CB0;margin-bottom:6px">'
                'Datos de bodegas no disponibles</div>'
                '<div style="font-size:0.83rem;color:#2C5282;line-height:1.6">'
                'Carga el <strong>Programa de compras</strong> para ver la distribución '
                'de existencias por bodega y el diagrama de red.<br>'
                'El archivo debe contener columnas <code>EXIST.&lt;BODEGA&gt;</code> para cada bodega.'
                '</div></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(_ayuda(
                "<b>Diagrama de red de bodegas</b> — Muestra cómo están distribuidas las existencias físicas entre las distintas bodegas del establecimiento. "
                "El nodo <b>central</b> corresponde a la bodega con mayor volumen de existencias. Los nodos <b>periféricos</b> son las demás bodegas. "
                "El <b>color</b> indica el nivel de existencias relativo: <span style='color:#38A169'><b>verde</b></span> = existencias altas, "
                "<span style='color:#D69E2E'><b>amarillo</b></span> = medio, "
                "<span style='color:#DD6B20'><b>naranja</b></span> = bajo, "
                "<span style='color:#E53E3E'><b>rojo</b></span> = sin existencias. "
                "Usa el filtro para ver la distribución de un medicamento específico."
            ), unsafe_allow_html=True)
            # ── Filtro por medicamento ────────────────────────────────────────
            _bd_all_names = ["— Todos los medicamentos —"] + sorted(
                resumen[COL_NOMBRE].dropna().unique().tolist()
            )
            _bd_col_filt, _bd_col_info = st.columns([3, 2])
            _bd_sel = _bd_col_filt.selectbox(
                "Filtrar por medicamento:", _bd_all_names, key="bod_med_sel"
            )

            # Helper: BOD_CARRUSEL_ABIERTA → Carrusel Abierta
            def _bod_clean_name(k):
                return k[4:].replace("_", " ").title()

            # ── Stock por bodega según filtro ─────────────────────────────────
            if _bd_sel and _bd_sel != "— Todos los medicamentos —":
                _bd_row = resumen[resumen[COL_NOMBRE] == _bd_sel]
                _bd_stk = {
                    c: float(pd.to_numeric(
                        _bd_row[c].iloc[0] if len(_bd_row) > 0 else 0,
                        errors="coerce") or 0)
                    for c in _bod_cols
                }
                _bd_mode = "med"
            else:
                _bd_stk = {
                    c: float(pd.to_numeric(resumen[c], errors="coerce").fillna(0).sum())
                    for c in _bod_cols
                }
                _bd_mode = "all"
            _bd_total = max(sum(_bd_stk.values()), 1)

            # ── Info card ─────────────────────────────────────────────────────
            _bd_col_info.markdown(
                f'<div style="background:white;border-radius:8px;padding:10px 14px;margin-top:24px;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.07)">'
                f'<div style="font-size:0.60rem;color:#94a3b8;font-weight:600;text-transform:uppercase">Unidades totales en existencia</div>'
                f'<div style="font-size:1.15rem;font-weight:800;color:#0f172a">{_m(int(_bd_total))} u</div>'
                f'<div style="font-size:0.75rem;color:#64748b">{len(_bod_cols)} bodegas · {_m(len(resumen))} medicamentos</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # ── Posiciones (círculo): nodo central = bodega con más stock ─────
            _bd_totals_global = {
                c: float(pd.to_numeric(resumen[c], errors="coerce").fillna(0).sum())
                for c in _bod_cols
            }
            _bd_center_key = max(_bd_totals_global, key=_bd_totals_global.get)
            _bd_perif = [c for c in _bod_cols if c != _bd_center_key]
            _bd_n  = max(len(_bd_perif), 1)
            _BD_R  = 2.2

            _bd_pos = {_bd_center_key: (0.0, 0.0)}
            for _bi, _bk in enumerate(_bd_perif):
                _bang = 2 * math.pi * _bi / _bd_n - math.pi / 2
                _bd_pos[_bk] = (_BD_R * math.cos(_bang), _BD_R * math.sin(_bang))

            # ── Colores de nodos ──────────────────────────────────────────────
            def _bd_node_color(stk_val, total):
                if stk_val <= 0:     return "#E53E3E"
                r = stk_val / total
                if r < 0.04:         return "#DD6B20"
                if r < 0.13:         return "#D69E2E"
                return "#38A169"

            # ── Figura Plotly ─────────────────────────────────────────────────
            _bd_fig = go.Figure()

            # Aristas
            for _bk in _bd_perif:
                _bx0, _by0 = _bd_pos[_bd_center_key]
                _bx1, _by1 = _bd_pos[_bk]
                _bd_fig.add_trace(go.Scatter(
                    x=[_bx0, _bx1, None], y=[_by0, _by1, None],
                    mode="lines",
                    line=dict(color="#CBD5E0", width=2.5),
                    hoverinfo="skip", showlegend=False,
                ))

            # Nodos
            _bd_nx   = [_bd_pos[k][0] for k in _bod_cols]
            _bd_ny   = [_bd_pos[k][1] for k in _bod_cols]
            _bd_nc   = [_bd_node_color(_bd_stk[k], _bd_total) for k in _bod_cols]
            _bd_sz   = [58 if k == _bd_center_key else 44 for k in _bod_cols]
            _bd_lbl  = [_bod_clean_name(k) for k in _bod_cols]
            _bd_pct  = [
                f"{_bd_stk[k] / _bd_total * 100:.1f}%" for k in _bod_cols
            ]
            _bd_hover = [
                f"<b>{_bod_clean_name(k)}</b><br>"
                f"Existencias: <b>{_m(int(_bd_stk[k]))}</b> u<br>"
                f"Participación: {_bd_pct[i]}<extra></extra>"
                for i, k in enumerate(_bod_cols)
            ]
            _bd_tpos = [
                "middle center" if k == _bd_center_key else "bottom center"
                for k in _bod_cols
            ]

            _bd_fig.add_trace(go.Scatter(
                x=_bd_nx, y=_bd_ny,
                mode="markers+text",
                marker=dict(
                    color=_bd_nc, size=_bd_sz,
                    line=dict(color="white", width=3),
                    opacity=0.93,
                ),
                text=_bd_lbl,
                textfont=dict(size=10, color="#0f172a"),
                textposition=_bd_tpos,
                hovertemplate=_bd_hover,
                showlegend=False,
            ))

            # Leyenda de color
            for _bl_color, _bl_name in [
                ("#38A169", "Existencias altas"), ("#D69E2E", "Existencias medias"),
                ("#DD6B20", "Existencias bajas"), ("#E53E3E", "Sin existencias"),
            ]:
                _bd_fig.add_trace(go.Scatter(
                    x=[None], y=[None], mode="markers",
                    marker=dict(color=_bl_color, size=10),
                    name=_bl_name, showlegend=True,
                ))

            _bd_titulo = (
                f"Distribución de existencias — {_bd_sel}"
                if _bd_mode == "med"
                else "Distribución de existencias por bodega (todos los productos)"
            )
            _bd_fig.update_layout(
                title=dict(text=_bd_titulo, font=dict(size=13, color="#0f172a")),
                height=460,
                margin=dict(t=36, b=20, l=20, r=20),
                xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-3.4, 3.4]),
                yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-3.4, 3.4]),
                legend=dict(orientation="h", y=-0.03, x=0.5, xanchor="center", font=dict(size=11)),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            )
            st.plotly_chart(_bd_fig, use_container_width=True)
            st.caption("Pasa el cursor sobre cada nodo para ver el nombre de la bodega, las unidades en existencia y su participación porcentual sobre el total.")

            # ── Tabla de detalle por bodega ───────────────────────────────────
            st.markdown(
                '<div style="font-size:0.82rem;font-weight:700;color:#64748b;'
                'text-transform:uppercase;letter-spacing:0.06em;margin:14px 0 8px 0">'
                'Detalle de inventario por bodega</div>',
                unsafe_allow_html=True,
            )
            _bd_det_opts   = ["— Selecciona una bodega —"] + [_bod_clean_name(k) for k in _bod_cols]
            _bd_key_map    = {_bod_clean_name(k): k for k in _bod_cols}
            _bd_det_sel    = st.selectbox("Seleccionar bodega:", _bd_det_opts, key="bod_det_sel")

            if _bd_det_sel and _bd_det_sel != "— Selecciona una bodega —":
                _bd_det_col = _bd_key_map[_bd_det_sel]
                _bd_det_df  = resumen[
                    pd.to_numeric(resumen[_bd_det_col], errors="coerce").fillna(0) > 0
                ].copy().sort_values(_bd_det_col, ascending=False)

                _bd_show_cols = [COL_NOMBRE, _bd_det_col]
                for _bsc in ["COSTO", "costo_unitario", "STC_MIN", "STC_MAX", "ALCANCE"]:
                    if _bsc in _bd_det_df.columns:
                        _bd_show_cols.append(_bsc)
                    if len(_bd_show_cols) >= 6:
                        break
                _bd_show = _bd_det_df[
                    [c for c in _bd_show_cols if c in _bd_det_df.columns]
                ].rename(columns={
                    COL_NOMBRE: "Medicamento",
                    _bd_det_col: f"Existencias ({_bd_det_sel})",
                    "COSTO": "Costo unit.", "costo_unitario": "Costo unit.",
                    "STC_MIN": "Exist. mín.", "STC_MAX": "Exist. máx.",
                    "ALCANCE": "Cobertura (meses)",
                }).reset_index(drop=True)

                st.markdown(
                    f'<div style="font-size:0.80rem;color:#64748b;margin-bottom:6px">'
                    f'<b>{_m(len(_bd_show))}</b> productos con existencias en <b>{_bd_det_sel}</b></div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(_safe_df(_bd_show), use_container_width=True, hide_index=True, height=320)

    # ══════════════════════════════════════════════════════════════════════════
    # SUB-TAB 1 — INVENTARIO
    # ══════════════════════════════════════════════════════════════════════════
    with _t2_inv:
        st.markdown(_ayuda(
            "<b>Tabla de inventario</b> — Lista completa de medicamentos con sus existencias actuales y cobertura estimada. "
            "La tabla está ordenada por <b>urgencia</b>: primero aparecen los productos "
            "<span style='color:#E53E3E;font-weight:700'>sin existencias</span>, "
            "luego los <span style='color:#DD6B20;font-weight:700'>críticos</span>, "
            "y al final los que están <span style='color:#38A169;font-weight:700'>bien abastecidos</span>. "
            "<b>Cobertura (meses)</b>: tiempo estimado que duran las existencias actuales al ritmo de consumo histórico. "
            "<b>Cant. sugerida</b>: unidades recomendadas a pedir según el modelo de inventario configurado. "
            "Usa el buscador y el filtro de estado para enfocarte en productos específicos."
        ), unsafe_allow_html=True)

        t2_busq, t2_fil = st.columns([3, 2])
        busq_inv = t2_busq.text_input(
            "Buscar producto:", placeholder="Escribe parte del nombre...", key="busq_inv"
        )

        if formato_hospital and "_estado_cob" in resumen.columns:
            _cats_t2 = [c for c in ["Sin existencias", "Crítico (≤1 mes)", "Bajo (1–3 meses)", "Adecuado (>3 meses)", "Sin datos"]
                        if c in resumen["_estado_cob"].values]
            filtro_cob = t2_fil.multiselect(
                "Estado de cobertura:", _cats_t2, default=_cats_t2, key="filtro_cob_inv"
            )
            tabla_base = resumen[resumen["_estado_cob"].isin(filtro_cob)].copy()
        else:
            filtro_estado = t2_fil.multiselect(
                "Estado:", ["VENCIDO", "CRITICO", "ADVERTENCIA", "NORMAL", "Sin fecha"],
                default=["VENCIDO", "CRITICO", "ADVERTENCIA", "NORMAL", "Sin fecha"],
                key="filtro_est_inv"
            )
            tabla_base = resumen[resumen["estado"].isin(filtro_estado)].copy()

        _components.html("""<script>
(function() {
  var cfg = {
    'Sin existencias':     {bg:'#FED7D7', fg:'#C53030', border:'#E53E3E'},
    'Crítico (≤1 mes)':    {bg:'#FEEBC8', fg:'#C05621', border:'#DD6B20'},
    'Bajo (1–3 meses)':    {bg:'#FEFCBF', fg:'#B7791F', border:'#D69E2E'},
    'Adecuado (>3 meses)': {bg:'#C6F6D5', fg:'#276749', border:'#38A169'}
  };
  function paint() {
    var tags = window.parent.document.querySelectorAll('[data-baseweb="tag"]');
    tags.forEach(function(tag) {
      var txt = (tag.innerText||tag.textContent||'').replace(/×/g,'').trim();
      for (var k in cfg) {
        if (txt.indexOf(k) !== -1) {
          tag.style.background  = cfg[k].bg;
          tag.style.borderColor = cfg[k].border;
          tag.style.color       = cfg[k].fg;
          tag.querySelectorAll('span').forEach(function(s){s.style.color=cfg[k].fg;});
          break;
        }
      }
    });
  }
  paint(); setTimeout(paint,200); setTimeout(paint,600);
  new MutationObserver(paint).observe(window.parent.document.body,
    {childList:true,subtree:true,attributes:true});
})();
</script>""", height=0)

        if busq_inv.strip():
            tabla_base = tabla_base[
                tabla_base[COL_NOMBRE].str.contains(busq_inv.strip(), case=False, na=False)
            ]

        _t2n    = len(tabla_base)
        _t2_sin = int((tabla_base["stock_total"] == 0).sum())
        _t2_pct = f"{_t2_sin / _t2n * 100:.1f}% del total" if _t2n > 0 else ""
        _t2_ped = 0
        if "SUGERIDO" in tabla_base.columns:
            _t2_ped = int((pd.to_numeric(tabla_base["SUGERIDO"], errors="coerce").fillna(0) > 0).sum())
        _t2_val = 0.0
        if "costo_unitario" in tabla_base.columns:
            _t2_val = float(
                (pd.to_numeric(tabla_base["stock_total"],    errors="coerce").fillna(0) *
                 pd.to_numeric(tabla_base["costo_unitario"], errors="coerce").fillna(0)).sum()
            )
        _t2_val_s = (f"${_t2_val/1e9:.1f}B" if _t2_val >= 1e9
                     else f"${_t2_val/1e6:.1f}M" if _t2_val >= 1e6 else f"${_t2_val:,.0f}")

        _t2c1, _t2c2, _t2c3, _t2c4 = st.columns(4)
        _t2c1.metric("Productos en vista",   f"{_m(_t2n)}",    delta="según filtros activos",
                     delta_color="off",
                     help="Total de medicamentos visibles con los filtros de estado y búsqueda activos.")
        _t2c2.metric("Sin existencias",      f"{_m(_t2_sin)}", delta=_t2_pct if _t2_pct else None,
                     delta_color="off",
                     help="Medicamentos con stock igual a cero dentro de la selección actual.")
        _t2c3.metric("Requieren pedido",     f"{_m(_t2_ped)}", delta="cant. sugerida > 0",
                     delta_color="off",
                     help="Medicamentos con cantidad sugerida mayor a cero en la selección actual.")
        _t2c4.metric("Valor en existencias", _t2_val_s,      delta="CLP — selección actual",
                     delta_color="off",
                     help="Valor económico total (existencias × costo unitario) de los productos en vista.")

        if formato_hospital and "_estado_cob" in tabla_base.columns:
            _ord2 = {"Sin existencias": 0, "Crítico (≤1 mes)": 1, "Bajo (1–3 meses)": 2, "Adecuado (>3 meses)": 3}
            tabla_base["_sort"] = tabla_base["_estado_cob"].map(_ord2).fillna(9)
            tabla_base = tabla_base.sort_values(["_sort", "stock_total"]).drop(columns=["_sort"])
        elif "estado" in tabla_base.columns:
            _ord3 = {"VENCIDO": 0, "CRITICO": 1, "ADVERTENCIA": 2, "NORMAL": 3}
            tabla_base["_sort"] = tabla_base["estado"].map(_ord3).fillna(9)
            tabla_base = tabla_base.sort_values(["_sort", "stock_total"]).drop(columns=["_sort"])

        if formato_hospital:
            _cols_t2 = [COL_CODIGO, COL_NOMBRE, "stock_total", "_estado_cob"]
            for _xc in ["ALCANCE", "SUGERIDO", "costo_unitario", "valor_inventario"]:
                if _xc in tabla_base.columns: _cols_t2.append(_xc)
            # Si también se cargó el archivo de inventario, mostrar vencimiento y estado
            if datos_inv_lotes is not None:
                for _xc in ["min_dias_vencer", "estado"]:
                    if _xc in tabla_base.columns: _cols_t2.append(_xc)
        else:
            _cols_t2 = [COL_CODIGO, COL_NOMBRE, "stock_total"]
            for _xc in ["n_lotes", "min_dias_vencer", "estado", "costo_unitario", "valor_inventario"]:
                if _xc in tabla_base.columns: _cols_t2.append(_xc)

        tabla = tabla_base[[c for c in _cols_t2 if c in tabla_base.columns]].copy()
        if "SUGERIDO" in tabla.columns:
            tabla["SUGERIDO"] = pd.to_numeric(tabla["SUGERIDO"], errors="coerce").fillna(0).clip(lower=0).apply(math.ceil)
        if "ALCANCE" in tabla.columns:
            tabla["ALCANCE"] = pd.to_numeric(tabla["ALCANCE"], errors="coerce")
        if "costo_unitario" in tabla.columns:
            tabla["costo_unitario"] = pd.to_numeric(tabla["costo_unitario"], errors="coerce").fillna(0)
        if "valor_inventario" in tabla.columns:
            tabla["valor_inventario"] = pd.to_numeric(tabla["valor_inventario"], errors="coerce").fillna(0)
        # Pre-formatear columnas de dinero con separador de miles
        if "costo_unitario" in tabla.columns:
            tabla["costo_unitario"] = tabla["costo_unitario"].apply(
                lambda v: f"${_m(int(v))}" if pd.notna(v) and v > 0 else "—"
            )
        if "valor_inventario" in tabla.columns:
            tabla["valor_inventario"] = tabla["valor_inventario"].apply(
                lambda v: f"${_m(int(v))}" if pd.notna(v) and v > 0 else "—"
            )

        tabla = tabla.rename(columns={
            COL_CODIGO: "Código", COL_NOMBRE: "Medicamento", "stock_total": "Existencias",
            "n_lotes": "Lotes", "min_dias_vencer": "Días p/Vencer",
            "costo_unitario": "Costo unit.", "valor_inventario": "Valor en exist.",
            "estado": "Estado", "_estado_cob": "Cobertura",
            "ALCANCE": "Cobertura (meses)", "SUGERIDO": "Cant. sugerida",
        })

        _ccfg = {
            "Código":      st.column_config.TextColumn("Código", width="small",
                           help="Código interno del medicamento en el sistema."),
            "Medicamento": st.column_config.TextColumn("Medicamento", width="large"),
            "Existencias": st.column_config.NumberColumn("Existencias", format="%d u",
                           help="Unidades fisicas disponibles en todas las bodegas combinadas."),
        }
        if "Cobertura (meses)" in tabla.columns:
            _ccfg["Cobertura (meses)"] = st.column_config.NumberColumn(
                "Cobertura (meses)", format="%.1f m",
                help="Meses estimados que duran las existencias actuales al ritmo de consumo promedio. Menos de 1 mes = crítico; 1-3 meses = bajo; más de 3 meses = adecuado.",
            )
        if "Cant. sugerida" in tabla.columns:
            _ccfg["Cant. sugerida"] = st.column_config.NumberColumn("Cant. sugerida", format="%d u",
                           help="Cantidad recomendada a pedir en la próxima orden, calculada por el modelo de inventario.")
        if "Costo unit." in tabla.columns:
            _ccfg["Costo unit."] = st.column_config.TextColumn("Costo unit.",
                           help="Precio unitario del medicamento en CLP, según el Programa de compras.")
        if "Valor en exist." in tabla.columns:
            _ccfg["Valor en exist."] = st.column_config.TextColumn("Valor en exist.",
                           help="Valor económico total: existencias × costo unitario (CLP).")
        if "Días p/Vencer" in tabla.columns:
            _ccfg["Días p/Vencer"] = st.column_config.NumberColumn("Días p/Vencer", format="%d d",
                           help="Días que faltan para que venza el lote más próximo a caducar. Negativo = ya vencido.")

        st.caption(f"{_m(_t2n)} producto(s) — ordenados por urgencia")
        st.dataframe(_safe_df(tabla), use_container_width=True, hide_index=True,
                     height=520, column_config=_ccfg)
        _buf_inv_dl = io.BytesIO()
        _safe_df(tabla).to_excel(_buf_inv_dl, index=False, engine="openpyxl")
        st.download_button(
            label=f"Descargar tabla con filtros aplicados ({_m(_t2n)} productos)",
            data=_buf_inv_dl.getvalue(),
            file_name=f"inventario_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_inventario",
        )

    # ══════════════════════════════════════════════════════════════════════════
    # SUB-TAB 2 — VENCIMIENTOS
    # ══════════════════════════════════════════════════════════════════════════
    with _t2_venc:
        # ── Explicación al tope ───────────────────────────────────────────────
        st.markdown(_ayuda(
            "<b>Control de fechas de caducidad</b> — Esta pestaña muestra cuándo vencen los lotes de medicamentos, "
            "independientemente de si hay o no existencias. "
            "La lógica recomendada es <span style='color:#3182CE;font-weight:700'>FEFO</span> (First Expired, First Out): "
            "el lote que vence primero debe despacharse primero para evitar pérdidas. "
            "Un mismo medicamento puede aparecer varias veces si tiene múltiples lotes con fechas distintas. "
            "<b>Días restantes</b>: días entre hoy y la fecha de caducidad. "
            "Un valor <span style='color:#E53E3E;font-weight:700'>negativo</span> significa que ese lote <span style='color:#E53E3E;font-weight:700'>ya caducó</span> "
            "y debe retirarse de bodega."
        ), unsafe_allow_html=True)
        # ── Tarjetas conceptuales con botones de filtro ─────────────────────
        st.markdown(
            '<div style="font-size:0.72rem;font-weight:700;color:#94A3B8;text-transform:uppercase;'
            'letter-spacing:0.07em;margin:8px 0 8px 0">'
            'Esta pestaña trata de fechas de caducidad — no de cantidades en bodega</div>',
            unsafe_allow_html=True,
        )
        _vc1, _vc2 = st.columns(2)
        with _vc1:
            st.markdown(
                '<div style="background:#FFF5F5;border-radius:8px;padding:12px 14px;'
                'border-top:3px solid #E53E3E;margin-bottom:6px">'
                '<div style="font-size:0.82rem;font-weight:700;color:#C53030;margin-bottom:5px">Vencido</div>'
                '<div style="font-size:0.79rem;color:#742A2A;line-height:1.55">'
                'La fecha de caducidad ya pasó. <b>No se puede usar</b>, aunque haya unidades en bodega. '
                'Esas unidades deben darse de baja.</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("Ver lotes vencidos", key="btn_vpanel_venc", use_container_width=True):
                st.session_state["_venc_panel"] = (
                    None if st.session_state.get("_venc_panel") == "vencidos" else "vencidos"
                )
        with _vc2:
            st.markdown(
                '<div style="background:#EBF8FF;border-radius:8px;padding:12px 14px;'
                'border-top:3px solid #3182CE;margin-bottom:6px">'
                '<div style="font-size:0.82rem;font-weight:700;color:#2B6CB0;margin-bottom:5px">Sin stock</div>'
                '<div style="font-size:0.79rem;color:#2C5282;line-height:1.55">'
                'No hay unidades disponibles en bodega. El medicamento puede estar <b>vigente pero agotado</b>. '
                'Es un quiebre de abastecimiento, no un vencimiento.</div></div>',
                unsafe_allow_html=True,
            )
            if st.button("Ver sin existencias", key="btn_vpanel_stk", use_container_width=True):
                st.session_state["_venc_panel"] = (
                    None if st.session_state.get("_venc_panel") == "sin_stock" else "sin_stock"
                )
        # ── Origen de datos ───────────────────────────────────────────────────
        _venc_df   = pd.DataFrame()
        _venc_nom  = COL_NOMBRE
        _venc_lote = COL_LOTE if COL_LOTE else None
        _venc_stk  = ("stock_total" if inv is not None and "stock_total" in inv.columns
                      else COL_STOCK)

        if datos_inv_lotes is not None and IL_VENC and IL_NOM and len(datos_inv_lotes) > 0:
            _vdf_il = datos_inv_lotes.copy()
            _vdf_il[IL_VENC] = pd.to_datetime(_vdf_il[IL_VENC], dayfirst=True, errors="coerce")
            _vdf_il["dias_vencer"] = (
                _vdf_il[IL_VENC] - pd.Timestamp.today().normalize()
            ).dt.days
            # Filtrar fechas inválidas: nulas o anteriores a 2000 (son celdas vacías del Excel)
            _venc_df = _vdf_il[
                (_vdf_il[IL_VENC].notna()) &
                (_vdf_il[IL_VENC] >= pd.Timestamp("2000-01-01"))
            ].copy()
            _venc_nom  = IL_NOM
            _venc_lote = IL_LOTE
            _vcpl = next(
                (c for c in _venc_df.columns
                 if "cantporlote" in c.lower().replace("_", "").replace(" ", "")),
                None,
            )
            _venc_stk = _vcpl if _vcpl else IL_STK
        elif COL_VENCIMIENTO and inv is not None and "dias_vencer" in inv.columns:
            _venc_df  = inv[
                inv["dias_vencer"].notna() &
                (inv[COL_VENCIMIENTO] >= pd.Timestamp("2000-01-01"))
            ].copy()
            _venc_nom  = COL_NOMBRE
            _venc_lote = COL_LOTE if COL_LOTE else None
            _venc_stk  = "stock_total" if "stock_total" in inv.columns else COL_STOCK

        # ── Panel de detalle según botón activo ─────────────────────────────
        _venc_panel = st.session_state.get("_venc_panel")
        if _venc_panel is not None:
            st.markdown("<div style='margin-top:8px'></div>", unsafe_allow_html=True)

            def _venc_dl_button(df_export, label, fname, key):
                _buf = io.BytesIO()
                _safe_df(df_export).to_excel(_buf, index=False, engine="openpyxl")
                st.download_button(
                    label=f"Descargar Excel — {label}",
                    data=_buf.getvalue(),
                    file_name=fname,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=key, use_container_width=True,
                )

            if _venc_panel == "sin_stock":
                # ── Sin stock: usa resumen (independiente de _venc_df) ─────────
                _ps_df = resumen[resumen["stock_total"] == 0].copy()
                _ps_cols = [COL_CODIGO, COL_NOMBRE, "stock_total"]
                for _xc in ["ALCANCE", "SUGERIDO", "costo_unitario", "valor_inventario", "estado"]:
                    if _xc in _ps_df.columns: _ps_cols.append(_xc)
                _ps_df = _ps_df[[c for c in _ps_cols if c in _ps_df.columns]]
                _ps_ren = {
                    COL_CODIGO: "Código", COL_NOMBRE: "Medicamento", "stock_total": "Existencias",
                    "ALCANCE": "Cobertura (meses)", "SUGERIDO": "Cant. sugerida",
                    "costo_unitario": "Costo unit.", "valor_inventario": "Valor en exist.", "estado": "Estado",
                }
                _ps_show = _ps_df.rename(columns=_ps_ren).reset_index(drop=True)
                st.markdown(
                    f'<div style="background:#EBF8FF;border-left:4px solid #3182CE;border-radius:8px;'
                    f'padding:10px 16px;margin:4px 0 6px 0">'
                    f'<span style="font-size:0.84rem;font-weight:700;color:#2B6CB0">'
                    f'Sin existencias — {_m(len(_ps_show))} medicamentos con stock igual a cero</span></div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(_safe_df(_ps_show), use_container_width=True, hide_index=True, height=320)
                _venc_dl_button(_ps_show, f"{_m(len(_ps_show))} sin existencias",
                                f"sin_existencias_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx",
                                "dl_panel_sinstock")

            elif len(_venc_df) == 0:
                st.info("Carga el archivo de inventario con fechas de vencimiento para ver esta información.")

            elif _venc_panel == "vencidos":
                # ── Lotes vencidos ────────────────────────────────────────────
                _pv_df = _venc_df[_venc_df["dias_vencer"] < 0].copy().sort_values("dias_vencer")
                _pv_cols = [c for c in [_venc_nom, _venc_lote, IL_VENC, _venc_stk, "dias_vencer"]
                            if c and c in _pv_df.columns]
                _pv_ren  = {
                    _venc_nom: "Medicamento", _venc_lote: "Lote",
                    IL_VENC:   "Fecha vencimiento", _venc_stk: "Unidades",
                    "dias_vencer": "Días vencido",
                }
                _pv_show = _pv_df[_pv_cols].rename(
                    columns={k: v for k, v in _pv_ren.items() if k}
                ).reset_index(drop=True)
                if "Fecha vencimiento" in _pv_show.columns:
                    _pv_show["Fecha vencimiento"] = (
                        pd.to_datetime(_pv_show["Fecha vencimiento"], errors="coerce")
                        .dt.strftime("%d/%m/%Y").fillna("—")
                    )
                st.markdown(
                    f'<div style="background:#FFF5F5;border-left:4px solid #E53E3E;border-radius:8px;'
                    f'padding:10px 16px;margin:4px 0 6px 0">'
                    f'<span style="font-size:0.84rem;font-weight:700;color:#C53030">'
                    f'Lotes vencidos — {_m(len(_pv_show))} lotes cuya fecha de caducidad ya pasó</span></div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(_safe_df(_pv_show), use_container_width=True, hide_index=True, height=320)
                _venc_dl_button(_pv_show, f"{_m(len(_pv_show))} lotes vencidos",
                                f"lotes_vencidos_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx",
                                "dl_panel_vencidos")

            st.divider()

        if len(_venc_df) == 0:
            st.markdown(
                '<div style="background:#EBF8FF;border-left:4px solid #3182CE;border-radius:8px;'
                'padding:18px 22px;margin:12px 0">'
                '<div style="font-size:0.88rem;font-weight:700;color:#2B6CB0;margin-bottom:6px">'
                'Datos de vencimiento no disponibles</div>'
                '<div style="font-size:0.83rem;color:#2C5282;line-height:1.6">'
                'Para activar esta sección, carga el <strong>archivo de inventario</strong> '
                'con columnas: <code>FVenvimiento</code>, <code>Lotes</code>, <code>Existencia</code>.'
                '</div></div>',
                unsafe_allow_html=True,
            )
        else:
            _venc_vis = _venc_df.copy()

            # ── 2 tarjetas adicionales: próximo a vencer + no tan próximo ─────
            _vc3, _vc4 = st.columns(2)
            with _vc3:
                st.markdown(
                    '<div style="background:#FFFAF0;border-radius:8px;padding:12px 14px;'
                    'border-top:3px solid #DD6B20;margin-bottom:6px">'
                    '<div style="font-size:0.82rem;font-weight:700;color:#C05621;margin-bottom:5px">Próximo a vencer</div>'
                    '<div style="font-size:0.79rem;color:#7B341E;line-height:1.55">'
                    'Vence en menos de 30 días. Debe despacharse <b>antes que cualquier otro lote</b> '
                    '(principio FEFO: primero en vencer, primero en salir).</div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Ver próximos a vencer (<30 d)", key="btn_vpanel_crit", use_container_width=True):
                    st.session_state["_venc_panel"] = (
                        None if st.session_state.get("_venc_panel") == "kpi_criticos" else "kpi_criticos"
                    )
            with _vc4:
                st.markdown(
                    '<div style="background:#FEFCBF;border-radius:8px;padding:12px 14px;'
                    'border-top:3px solid #D69E2E;margin-bottom:6px">'
                    '<div style="font-size:0.82rem;font-weight:700;color:#975A16;margin-bottom:5px">Vencimiento no tan próximo</div>'
                    '<div style="font-size:0.79rem;color:#744210;line-height:1.55">'
                    'Vence entre 30 y 90 días. No es urgente hoy, pero <b>hay que planificar</b> '
                    'su uso o devolución antes de que llegue a estado crítico.</div></div>',
                    unsafe_allow_html=True,
                )
                if st.button("Ver vencimientos próximos (30–90 d)", key="btn_vpanel_adv", use_container_width=True):
                    st.session_state["_venc_panel"] = (
                        None if st.session_state.get("_venc_panel") == "kpi_proximos" else "kpi_proximos"
                    )

            # ── Panel para los 4 KPI ──────────────────────────────────────────
            _vp = st.session_state.get("_venc_panel")
            _kpi_ranges = {
                "kpi_vencidos":  (None, 0,   "#E53E3E", "#C53030", "Lotes vencidos"),
                "kpi_criticos":  (0,   30,   "#DD6B20", "#C05621", "Vencen en menos de 30 días"),
                "kpi_proximos":  (30,  90,   "#D69E2E", "#975A16", "Vencen entre 30 y 90 días"),
                "kpi_ok":        (90,  None, "#38A169", "#276749", "Vencen en más de 90 días"),
            }
            if _vp in _kpi_ranges:
                _r_lo, _r_hi, _r_border, _r_text, _r_title = _kpi_ranges[_vp]
                if _r_lo is None:
                    _mask_kv = _venc_df["dias_vencer"] < _r_hi
                elif _r_hi is None:
                    _mask_kv = _venc_df["dias_vencer"] >= _r_lo
                else:
                    _mask_kv = (_venc_df["dias_vencer"] >= _r_lo) & (_venc_df["dias_vencer"] < _r_hi)
                _kv_df = _venc_df[_mask_kv].copy().sort_values("dias_vencer")
                # Columnas a mostrar
                _kv_cols = [c for c in [_venc_nom, _venc_lote, IL_VENC, _venc_stk, "dias_vencer"]
                            if c and c in _kv_df.columns]
                _kv_ren  = {
                    _venc_nom: "Medicamento", _venc_lote: "Lote",
                    IL_VENC: "Fecha vencimiento", _venc_stk: "Unidades",
                    "dias_vencer": "Días",
                }
                _kv_show = _kv_df[_kv_cols].rename(
                    columns={k: v for k, v in _kv_ren.items() if k}
                ).reset_index(drop=True)
                if "Fecha vencimiento" in _kv_show.columns:
                    _kv_show["Fecha vencimiento"] = (
                        pd.to_datetime(_kv_show["Fecha vencimiento"], errors="coerce")
                        .dt.strftime("%d/%m/%Y").fillna("—")
                    )
                st.markdown(
                    f'<div style="border-left:4px solid {_r_border};border-radius:6px;'
                    f'background:white;padding:10px 16px;margin:8px 0 6px 0">'
                    f'<span style="font-size:0.84rem;font-weight:700;color:{_r_text}">'
                    f'{_r_title} — {_m(len(_kv_show))} lotes</span></div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(_safe_df(_kv_show), use_container_width=True, hide_index=True,
                             height=min(400, max(80, len(_kv_show) * 35 + 40)))
                _buf_kv = io.BytesIO()
                _safe_df(_kv_show).to_excel(_buf_kv, index=False, engine="openpyxl")
                st.download_button(
                    label=f"Descargar Excel — {_r_title} ({_m(len(_kv_show))} lotes)",
                    data=_buf_kv.getvalue(),
                    file_name=f"vencimientos_{_vp}_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"dl_kv_{_vp}",
                )
                st.divider()



    # ══════════════════════════════════════════════════════════════════════════
    # SUB-TAB 3 — DETALLE POR MEDICAMENTO
    # ══════════════════════════════════════════════════════════════════════════
    with _t2_det:
        st.markdown(_ayuda(
            "<b>Ficha completa de medicamento</b> — Selecciona cualquier producto para ver todos sus indicadores en detalle. "
            "El <b>termómetro</b> muestra visualmente si las existencias están en zona "
            "<span style='color:#E53E3E;font-weight:700'>crítica</span>, "
            "de <span style='color:#DD6B20;font-weight:700'>alerta</span> o "
            "<span style='color:#38A169;font-weight:700'>adecuada</span> "
            "respecto a las existencias mínimas y máximas definidas. "
            "La <b>tabla de información</b> resume parámetros operativos como existencias mínimas, máximas y críticas. "
            "El <b>historial mensual</b> permite identificar estacionalidad o tendencias de consumo. "
            "El buscador filtra el listado en tiempo real; el listado muestra primero los medicamentos de mayor consumo."
        ), unsafe_allow_html=True)
        # Ordenar por consumo descendente (medicamentos más relevantes primero)
        if "media_diaria" in resumen.columns:
            _det_ord = resumen.sort_values("media_diaria", ascending=False)[COL_NOMBRE].tolist()
        else:
            _det_ord = resumen[COL_NOMBRE].sort_values().tolist()

        # Search + selectbox
        _det_busq = st.text_input(
            "Buscar:", placeholder="Nombre del producto...", key="det_busq"
        )
        if _det_busq.strip():
            _det_filt = [n for n in _det_ord if _det_busq.strip().lower() in n.lower()]
        else:
            _det_filt = _det_ord
        _sel_med = st.selectbox(
            "Medicamento:", _det_filt if _det_filt else _det_ord, key="det_med_sel"
        )

        if _sel_med:
            _row_d   = resumen[resumen[COL_NOMBRE] == _sel_med].iloc[0]
            _cod_d   = _row_d[COL_CODIGO]
            # Helper: convierte a float de forma segura — NaN y None → 0.0
            # float(NaN or 0) NO funciona porque NaN es truthy en Python
            def _n0(v):
                _x = pd.to_numeric(v, errors="coerce")
                return 0.0 if pd.isna(_x) else float(_x)
            _d_stk   = _n0(_row_d.get("stock_total",       0))
            _d_alc   = _n0(_row_d.get("ALCANCE",        None))
            _d_smin  = _n0(_row_d.get("STC_MIN",        None))
            _d_smax  = _n0(_row_d.get("STC_MAX",        None))
            _d_scrit = _n0(_row_d.get("STC_CRITICO",    None))
            _d_med   = _n0(_row_d.get("media_diaria",      0))
            _d_sug   = _n0(_row_d.get("SUGERIDO",          0))
            _d_costo = _n0(_row_d.get("costo_unitario",    0))
            _d_dcob  = _n0(_row_d.get("dias_cobertura",    0))
            _d_est   = str(_row_d.get("_estado_cob", _row_d.get("estado", "—")))

            # ── KPI strip ─────────────────────────────────────────────────────
            _dk1, _dk2, _dk3, _dk4 = st.columns(4)
            _dk1.metric("Existencias actuales", f"{_m(math.floor(_d_stk))} u",
                        help="Total de unidades fisicas disponibles en todas las bodegas para este medicamento.")
            _dk2.metric("Consumo prom. mensual", f"{_d_med*30:,.0f} u/mes" if _d_med > 0 else "—",
                        help="Promedio de unidades dispensadas por mes, calculado a partir del historial de movimientos.")
            if _d_alc > 0:
                _dk3.metric("Cobertura", f"{round(_d_alc, 1)} meses",
                            help="Meses que duran las existencias actuales al ritmo de consumo promedio. Menos de 1 mes = crítico.")
            elif _d_dcob > 0:
                _dk3.metric("Días de cobertura", f"{_d_dcob:.0f} días",
                            help="Días que duran las existencias actuales al ritmo de consumo promedio.")
            else:
                _dk3.metric("Cobertura", "—",
                            help="No hay datos suficientes para estimar la cobertura (sin historial de consumo).")
            _dk4.metric("Sugerido pedir", f"{_m(math.ceil(_d_sug))} u" if _d_sug > 0 else "No requerido",
                        help="Cantidad recomendada para la próxima orden de compra, según el modelo de inventario y los parámetros configurados.")

            # ── Fila adicional: quiebres históricos + comparativa mensual ─────
            if tiene_movimientos and datos_movimientos is not None and _d_med > 0:
                _hmov_q = datos_movimientos[
                    datos_movimientos[COL_MOV_CODIGO] == _cod_d
                ].copy()
                _hmov_q[COL_MOV_FECHA]    = pd.to_datetime(_hmov_q[COL_MOV_FECHA], dayfirst=True, errors="coerce")
                _hmov_q[COL_MOV_CANTIDAD] = pd.to_numeric(_hmov_q[COL_MOV_CANTIDAD], errors="coerce").fillna(0)
                _hmov_q = _hmov_q.dropna(subset=[COL_MOV_FECHA])
                _hoy_q      = pd.Timestamp.today().normalize()
                _hace_12m_q = _hoy_q - pd.DateOffset(months=12)
                _hm_q = (
                    _hmov_q[_hmov_q[COL_MOV_FECHA] >= _hace_12m_q]
                    .set_index(COL_MOV_FECHA)
                    .resample("MS")[COL_MOV_CANTIDAD].sum()
                )
                _mes_act_ts_q  = _hoy_q.to_period("M").to_timestamp()
                _meses_hist_q  = _hm_q[_hm_q.index < _mes_act_ts_q]
                _dias_transc_q = max((_hoy_q - _mes_act_ts_q).days + 1, 1)
                _dias_en_mes_q = ((_mes_act_ts_q + pd.DateOffset(months=1)) - _mes_act_ts_q).days
                _consumo_mes_q = float(
                    _hmov_q[_hmov_q[COL_MOV_FECHA] >= _mes_act_ts_q][COL_MOV_CANTIDAD].sum()
                )
                _dkq1, _dkq2 = st.columns(2)

                # KPI: meses sin consumo (posibles quiebres)
                if len(_meses_hist_q) > 0:
                    _n_quiebres_q = int((_meses_hist_q == 0).sum())
                    _dkq1.metric(
                        "Meses sin actividad (últ. 12 m.)",
                        f"{_n_quiebres_q} meses",
                        delta=f"de {len(_meses_hist_q)} meses analizados",
                        delta_color="off",
                        help="Cuántos meses del último año no hubo ningún consumo registrado. "
                             "0 = siempre tuvo movimiento (ideal). "
                             "Un número alto puede indicar quiebres de stock o que el producto dejó de usarse.",
                    )
                else:
                    _dkq1.metric("Meses sin actividad (últ. 12 m.)", "—")

                # KPI: consumo mes actual vs promedio histórico (por tasa diaria)
                if len(_meses_hist_q) >= 2:
                    _avg_hist_q    = float(_meses_hist_q.mean())
                    _tasa_actual_q = _consumo_mes_q / _dias_transc_q
                    _tasa_hist_q   = _avg_hist_q / max(_dias_en_mes_q, 1)
                    if _tasa_hist_q > 0:
                        _pct_q = (_tasa_actual_q - _tasa_hist_q) / _tasa_hist_q * 100
                        _signo = "+" if _pct_q >= 0 else ""
                        _dkq2.metric(
                            "Consumo del mes en curso",
                            f"{_m(int(_consumo_mes_q))} u",
                            delta=f"{_signo}{_pct_q:.1f}% vs promedio mensual histórico",
                            delta_color="off",
                            help=f"Unidades consumidas en lo que va del mes ({_dias_transc_q} de {_dias_en_mes_q} días). "
                                 f"Tasa diaria actual: {_tasa_actual_q:.1f} u/día. "
                                 f"Promedio histórico: {_tasa_hist_q:.1f} u/día. "
                                 f"Un valor negativo no indica problema si el mes no ha terminado.",
                        )
                    else:
                        _dkq2.metric(
                            "Consumo del mes en curso",
                            f"{_m(int(_consumo_mes_q))} u",
                            delta=f"{_dias_transc_q} de {_dias_en_mes_q} días transcurridos",
                            delta_color="off",
                        )
                else:
                    _dkq2.metric(
                        "Consumo del mes en curso",
                        f"{_m(int(_consumo_mes_q))} u",
                        help="Historial insuficiente para calcular la comparativa mensual.",
                    )

            st.divider()

            # ── Gauge (izq) + Tabla info / Lotes (der) ───────────────────────
            _gcol, _tcol = st.columns([1, 1])

            with _gcol:
                if _d_smax > 0 and _d_smin > 0:
                    _gmax   = max(_d_smax, _d_stk) * 1.15
                    _gcolor = "#E53E3E" if _d_stk <= _d_scrit else "#DD6B20" if _d_stk <= _d_smin else "#38A169"
                    _gsteps = [{"range": [0, _d_scrit], "color": "#FED7D7"}]
                    if _d_smin > _d_scrit:
                        _gsteps.append({"range": [_d_scrit, _d_smin], "color": "#FEEBC8"})
                    _gsteps.append({"range": [_d_smin, _gmax], "color": "#C6F6D5"})
                    _gval   = _d_stk
                    _gtitle = "Nivel de existencias (unidades)"
                    _gsufx  = " u"
                    _gthr   = {"line": {"color": "#DD6B20", "width": 4}, "thickness": 0.75, "value": _d_smin}
                else:
                    _gmax   = max(6.0, _d_alc * 1.3)
                    _gcolor = "#E53E3E" if _d_alc <= 1 else "#DD6B20" if _d_alc <= 3 else "#38A169"
                    _gsteps = [
                        {"range": [0, 1], "color": "#FED7D7"},
                        {"range": [1, 3], "color": "#FEEBC8"},
                        {"range": [3, _gmax], "color": "#C6F6D5"},
                    ]
                    _gval   = _d_alc
                    _gtitle = "Cobertura estimada (meses)"
                    _gsufx  = " m"
                    _gthr   = {"line": {"color": "#DD6B20", "width": 4}, "thickness": 0.75, "value": 3}

                _fig_g = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=_gval,
                    number={"suffix": _gsufx, "font": {"size": 28, "color": _gcolor}},
                    gauge={
                        "axis":       {"range": [0, _gmax], "tickwidth": 1, "tickcolor": "#64748b"},
                        "bar":        {"color": _gcolor, "thickness": 0.28},
                        "bgcolor":    "white",
                        "borderwidth": 1, "bordercolor": "#E2E8F0",
                        "steps":      _gsteps,
                        "threshold":  _gthr,
                    },
                    title={"text": f"<b>{_gtitle}</b>", "font": {"size": 12, "color": "#64748b"}},
                    domain={"x": [0, 1], "y": [0, 1]},
                ))
                _fig_g.update_layout(
                    height=270, margin=dict(t=40, b=10, l=20, r=20),
                    paper_bgcolor="white",
                )
                st.plotly_chart(_fig_g, use_container_width=True)
                if _d_smax > 0 and _d_smin > 0:
                    _stk_fmt = f"{_m(int(_d_stk))}"
                    _min_fmt = f"{_m(int(_d_smin))}"
                    if _d_scrit > 0 and _d_stk <= _d_scrit:
                        _gauge_txt = (
                            f"Existencias actuales: {_stk_fmt} u — nivel crítico. "
                            f"El stock ha caído por debajo del umbral de emergencia ({_m(int(_d_scrit))} u). "
                            f"Se requiere pedido urgente para evitar quiebre total."
                        )
                    elif _d_stk <= _d_smin:
                        _falta = int(_d_smin - _d_stk)
                        _gauge_txt = (
                            f"Existencias actuales: {_stk_fmt} u — por debajo del mínimo recomendado. "
                            f"Se necesitan al menos {_min_fmt} u para estar cubiertos; faltan {_m(_falta)} u. "
                            f"Se recomienda realizar un pedido pronto."
                        )
                    else:
                        _sobre = int(_d_stk - _d_smin)
                        _gauge_txt = (
                            f"Existencias actuales: {_stk_fmt} u — nivel adecuado. "
                            f"Se superan las {_min_fmt} u mínimas recomendadas en {_m(_sobre)} u. "
                            f"No se requiere pedido en este momento."
                        )
                    st.caption(_gauge_txt)
                else:
                    if _d_alc <= 1:
                        _cob_txt = (
                            f"Cobertura estimada: {round(_d_alc, 1)} meses — nivel crítico. "
                            f"Las existencias actuales alcanzan para menos de 1 mes. "
                            f"Se recomienda solicitar reabastecimiento de forma urgente."
                        )
                    elif _d_alc <= 3:
                        _cob_txt = (
                            f"Cobertura estimada: {round(_d_alc, 1)} meses — nivel bajo. "
                            f"Las existencias cubren entre 1 y 3 meses de consumo. "
                            f"Conviene planificar un pedido pronto."
                        )
                    else:
                        _cob_txt = (
                            f"Cobertura estimada: {round(_d_alc, 1)} meses — nivel adecuado. "
                            f"Las existencias cubren más de 3 meses de consumo. "
                            f"No se requiere pedido en este momento."
                        )
                    st.caption(_cob_txt)

            with _tcol:
                if formato_hospital:
                    _info_rows = [
                        ("Código",              str(_cod_d)),
                        ("Existencias actuales", f"{_m(math.floor(_d_stk))} u"),
                    ]
                    _badge_colors_d = {
                        "Sin existencias":   ("#FED7D7","#C53030"),
                        "Crítico (≤1 mes)":  ("#FEEBC8","#C05621"),
                        "Bajo (1–3 meses)":  ("#FEFCBF","#B7791F"),
                        "Adecuado (>3 meses)": ("#C6F6D5","#276749"),
                        "VENCIDO":   ("#FED7D7","#C53030"), "CRITICO": ("#FEEBC8","#C05621"),
                        "ADVERTENCIA": ("#FEFCBF","#B7791F"), "NORMAL": ("#C6F6D5","#276749"),
                    }
                    _bg_d, _fg_d = _badge_colors_d.get(_d_est, ("#EDF2F7","#718096"))
                    _info_rows.append(("Estado", _d_est))
                    for _campo, _col_r in [
                        ("Cobertura (meses)",   "ALCANCE"),
                        ("Existencias mínimas", "STC_MIN"),
                        ("Existencias máximas", "STC_MAX"),
                        ("Existencias críticas","STC_CRITICO"),
                        ("Consumo promedio",    "CONS_PROM"),
                    ]:
                        if _col_r in _row_d.index and not pd.isna(_row_d.get(_col_r)):
                            _info_rows.append((_campo, f"{float(_row_d[_col_r]):,.1f}"))
                    if _d_costo > 0:
                        _info_rows.append(("Precio unitario",     f"${_m(int(_d_costo))} CLP"))
                        _info_rows.append(("Valor en existencias", f"${_m(int(_d_stk * _d_costo))} CLP"))
                    # Render as a styled HTML table (no gray DataFrame headers)
                    _rows_html = ""
                    for _campo_h, _valor_h in _info_rows:
                        if _campo_h == "Estado":
                            _val_cell = (
                                f'<span style="background:{_bg_d};color:{_fg_d};'
                                f'padding:2px 8px;border-radius:12px;font-size:0.78rem;font-weight:700">'
                                f'{_valor_h}</span>'
                            )
                        else:
                            _val_cell = f'<span style="font-weight:600;color:#0f172a">{_valor_h}</span>'
                        _rows_html += (
                            f'<tr>'
                            f'<td style="padding:7px 12px;color:#64748b;font-size:0.82rem;'
                            f'border-bottom:1px solid #F1F5F9;white-space:nowrap">{_campo_h}</td>'
                            f'<td style="padding:7px 12px;font-size:0.82rem;'
                            f'border-bottom:1px solid #F1F5F9">{_val_cell}</td>'
                            f'</tr>'
                        )
                    st.markdown(
                        f'<div style="font-size:0.78rem;font-weight:700;color:#64748b;'
                        f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:10px">'
                        f'Información del producto</div>'
                        f'<table style="width:100%;border-collapse:collapse">'
                        f'{_rows_html}'
                        f'</table>',
                        unsafe_allow_html=True,
                    )
                else:
                    st.markdown("**Lotes (FEFO: primero en vencer, primero en salir)**")
                    _cols_lotes = [c for c in [COL_LOTE, COL_MARCA, COL_VENCIMIENTO, COL_STOCK, "dias_vencer", "estado"]
                                   if c is not None and c in inv.columns]
                    _lotes_med = inv[inv[COL_NOMBRE] == _sel_med][_cols_lotes].copy().sort_values("dias_vencer")
                    if COL_VENCIMIENTO in _lotes_med.columns:
                        _lotes_med[COL_VENCIMIENTO] = _lotes_med[COL_VENCIMIENTO].dt.strftime("%d/%m/%Y")
                    st.dataframe(_safe_df(_lotes_med), use_container_width=True, hide_index=True)


            # ── Historial de consumo mensual ──────────────────────────────────
            st.markdown(
                '<div style="font-size:0.82rem;font-weight:700;color:#64748b;'
                'text-transform:uppercase;letter-spacing:0.06em;margin:14px 0 6px 0">'
                'Historial de consumo mensual</div>',
                unsafe_allow_html=True,
            )
            if tiene_movimientos and datos_movimientos is not None:
                _hmov = datos_movimientos[datos_movimientos[COL_MOV_CODIGO] == _cod_d].copy()
                if len(_hmov) > 0:
                    _hmov[COL_MOV_FECHA]    = pd.to_datetime(_hmov[COL_MOV_FECHA], dayfirst=True, errors="coerce")
                    _hmov[COL_MOV_CANTIDAD] = pd.to_numeric(_hmov[COL_MOV_CANTIDAD], errors="coerce").fillna(0)
                    _hm = (
                        _hmov.dropna(subset=[COL_MOV_FECHA])
                        .set_index(COL_MOV_FECHA)
                        .resample("MS")[COL_MOV_CANTIDAD].sum()
                        .reset_index().tail(18)
                    )
                    if len(_hm) > 0:
                        _hm["lbl"] = _hm[COL_MOV_FECHA].dt.strftime("%b %Y")
                        _fig_h = go.Figure()
                        _fig_h.add_trace(go.Bar(
                            x=_hm["lbl"], y=_hm[COL_MOV_CANTIDAD],
                            marker_color="#2563eb", name="Consumo mensual",
                            hovertemplate="%{x}: %{y:,.0f} u<extra></extra>",
                        ))
                        if _d_med > 0:
                            _fig_h.add_hline(
                                y=_d_med * 30,
                                line_dash="dash", line_color="#dc2626", line_width=1.5,
                                annotation_text=f"Prom: {_d_med*30:,.0f}", annotation_position="top right",
                            )
                        _fig_h.update_layout(
                            height=280, margin=dict(t=20, b=20, l=10, r=10),
                            xaxis_title="Mes", yaxis_title="Unidades dispensadas",
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#f8fafc", showlegend=False,
                        )
                        st.plotly_chart(_fig_h, use_container_width=True)
                        st.caption("Barras azules = unidades dispensadas cada mes. Linea roja punteada = promedio mensual histórico. Meses por encima del promedio pueden indicar estacionalidad o picos de demanda que deben considerarse al planificar el siguiente pedido.")
                    else:
                        st.info("Sin fechas válidas para construir el historial.")
                else:
                    st.info("Sin movimientos registrados para este medicamento.")
            else:
                st.info("Sube el archivo de movimientos para ver el historial de consumo.")

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 3 — PLANIFICACIÓN
# ══════════════════════════════════════════════════════════════════════════════
def _disparar_webhook_plan(payload: dict):
    """Dispara un webhook a Make.com con el payload dado. Retorna (ok, msg)."""
    _wh = _store_global().get("webhook_url", "").strip()
    if not _wh:
        return False, "Sin URL configurada"
    try:
        _r = _requests.post(_wh, json=payload, timeout=6)
        return _r.status_code < 300, f"HTTP {_r.status_code}"
    except Exception as _e:
        return False, str(_e)

with tab3:
    _t3_ab, _t3_rh = st.tabs(["Abastecimiento", "Horizonte Rodante"])

    # ══════════════════════════════════════════════════════════════════════
    # SUB-TAB: ABASTECIMIENTO
    # ══════════════════════════════════════════════════════════════════════
    with _t3_ab:
        st.markdown(_ayuda(
            "<b>Módulo de Abastecimiento</b> — Calcula automáticamente las políticas de pedido recomendadas para cada medicamento, basándose en el historial de consumo y los parámetros configurados en el panel lateral. "
            "<span style='color:#3182CE;font-weight:700'>Punto de reorden (s)</span>: nivel de existencias al que se debe emitir un nuevo pedido para no quedarse sin existencias durante el tiempo de entrega. "
            "<span style='color:#3182CE;font-weight:700'>Cantidad a pedir (EOQ)</span>: cantidad económicamente recomendada que minimiza la suma de costos de ordenar y de mantener inventario. "
            "<span style='color:#3182CE;font-weight:700'>Reserva de seguridad (SS)</span>: existencias extra para absorber variaciones inesperadas en la demanda o en el tiempo de entrega. "
            "<span style='color:#3182CE;font-weight:700'>Nivel máximo (S)</span>: techo de inventario para evitar exceso de existencias. "
            "La tabla está ordenada por urgencia: primero los productos que requieren "
            "<span style='color:#E53E3E;font-weight:700'>acción inmediata</span>."
        ), unsafe_allow_html=True)
        if not tiene_movimientos:
            st.warning("Se requiere el archivo de movimientos para calcular las políticas.")
        else:
            # Calcular políticas para todos los productos (una sola vez)
            filas_politicas = []
            for i in range(len(resumen)):
                fila = resumen.iloc[i]
                if fila["media_diaria"] <= 0:
                    continue
                var_d      = max(fila["var_diaria"], 0.001)
                p          = calcular_politicas(fila["media_diaria"], var_d, costo_orden, costo_mantener, lead_time, periodo_revision, Z)
                R_etiqueta = f"Cada {int(periodo_revision)} días"
                dias_cob = fila["dias_cobertura"]
                if fila["estado"] == "VENCIDO":
                    acción = "Dar de baja"
                elif fila["stock_total"] < p["s"]:
                    acción = "Pedir ahora"
                elif dias_cob is not None and not pd.isna(dias_cob) and dias_cob < (lead_time + periodo_revision) * 1.5:
                    acción = "Pedir pronto"
                else:
                    acción = "Existencias suficientes"
                filas_politicas.append({
                    "Código":                       fila[COL_CODIGO],
                    "Medicamento":                  fila[COL_NOMBRE],
                    "Consumo diario promedio":       str(round(fila["media_diaria"], 1)) + " u/día",
                    "Existencias actuales":          math.floor(fila["stock_total"]),
                    "Pedir cuando queden menos de": math.ceil(p["s"]),
                    "Cuánto pedir":                 math.ceil(p["Q"]),
                    "Nivel máximo recomendado":      math.ceil(p["S"]),
                    "Reserva de seguridad":         math.ceil(p["SS"]),
                    "Días de existencias disponibles": dias_cob if dias_cob is not None and not pd.isna(dias_cob) else "—",
                    "Revisar cada":                 R_etiqueta,
                    "Acción recomendada":           acción,
                    "_media":                       fila["media_diaria"],
                })

            if len(filas_politicas) == 0:
                st.warning("No hay medicamentos con datos de demanda suficientes.")
            else:
                df_politicas = pd.DataFrame(filas_politicas)
                orden_accion = {"Dar de baja": 0, "Pedir ahora": 1, "Pedir pronto": 2, "Existencias suficientes": 3}
                df_politicas["_orden"] = df_politicas["Acción recomendada"].map(orden_accion).fillna(4)
                df_politicas = df_politicas.sort_values("_orden").drop(columns="_orden")

                NOMBRES = {"(R,s,Q)": "Cantidad fija", "(R,S)": "Reponer hasta el máximo", "(R,s,S)": "Variable hasta el máximo"}
                DESCRIPCION = {
                    "(R,s,Q)": "Si las existencias están bajas, pide siempre la misma cantidad fija.",
                    "(R,S)":   "Pide lo necesario para llegar al nivel máximo de existencias.",
                    "(R,s,S)": "Si las existencias están bajas, pide lo necesario para llegar al máximo.",
                }

                # ── SECCIÓN 2: frecuencia de revisión ──────────────────────────────

                # ── SECCIÓN 3: simulación de estrategias ───────────────────────────
                with st.expander("Comparación de estrategias de pedido"):
                    st.caption("Simula el costo anual de tres estrategias distintas para un medicamento.")
                    # Ordenar los medicamentos de mayor a menor consumo para que el default sea relevante
                    meds_sim_ord = df_politicas.sort_values("_media", ascending=False)["Medicamento"].tolist()
                    med_sim = st.selectbox("Medicamento a simular:", meds_sim_ord, key="sim_med")
                    # Obtener los datos del medicamento selecciónado
                    fila_simulación = resumen[resumen[COL_NOMBRE] == med_sim].iloc[0]
                    media_sim = max(fila_simulación["media_diaria"], 0.001)
                    # var_diaria ya contiene min(Media, var_batch) del proceso de estimación
                    var_diaria_raw = fila_simulación["var_diaria"]
                    var_sim = max(float(var_diaria_raw) if not pd.isna(var_diaria_raw) else media_sim, 0.001)
                    params_sim = calcular_politicas(media_sim, var_sim, costo_orden, costo_mantener, lead_time, periodo_revision, Z)
                    R_rec_sim, _ = recomendar_periodo(media_sim, var_sim, costo_orden, costo_mantener, lead_time)

                    # Niveles según el notebook de referencia:
                    #   (R,s,Q) → inventario inicial = s+Q+U; pide Q* fija cuando IP ≤ s
                    #   (R,S)   → S = s+Q*; repone hasta S en CADA revisión (cap Q_max)
                    #   (R,s,S) → S = s+Q*; repone hasta S solo cuando IP ≤ s (cap Q_max)
                    s_sim  = params_sim["s"]
                    Q_sim  = params_sim["Q"]
                    U_sim  = params_sim["U"]

                    # Parámetros de perecibilidad — solo desde sidebar (Programa de compras no tiene FVenvimiento)
                    SL_sim = int(vida_util_dias) if vida_util_dias > 0 else None
                    WC_sim   = float(costo_desperdicio)
                    beta_sim = float(beta_servicio)
                    _per_sim = calcular_perecibilidad(media_sim, var_sim, Q_sim,
                                                      SL_sim if SL_sim else 3650,
                                                      beta=beta_sim)
                    Q_star_sim = _per_sim["Q_star"]
                    Q_max_sim  = _per_sim["Q_max"]
                    E_O_sim    = _per_sim["E_O"]

                    # Inventarios iniciales — notebook v2 (parten del nivel máximo de cada política):
                    #   (R,s,Q)  cell_005: OH_init = s + Q* + U
                    #   (R,S)    cell_007: OH_init = S_RS = s      ← nivel objetivo = s
                    #   (R,s,S)  cell_009: OH_init = S  = s + Q + U  ← usa Q (EOQ), no Q*
                    #
                    # CORRECCIÓN (R,s,Q): limitar OH_init a Media*SL_eff para evitar que
                    # el lote inicial sea mayor que lo que se puede consumir antes de vencer.
                    # Si S_rsq > Media*SL, el exceso se purga al día SL generando un
                    # vacío de stock antes de que llegue el primer pedido → quiebres artificiales.
                    _SL_eff_sim = float(SL_sim) if SL_sim and SL_sim > 0 else 1e6
                    S_rsq_raw  = s_sim + Q_star_sim + U_sim
                    S_rsq  = int(min(S_rsq_raw,  media_sim * _SL_eff_sim)) if _SL_eff_sim < 1e5 else S_rsq_raw
                    # (R,S): nivel objetivo = S = s+Q+U para cubrir el período LT+R completo
                    S_rs_raw   = s_sim + Q_sim + U_sim
                    S_rs   = int(min(S_rs_raw, media_sim * _SL_eff_sim)) if _SL_eff_sim < 1e5 else S_rs_raw
                    S_rss_raw  = s_sim + Q_sim + U_sim
                    S_rss  = int(min(S_rss_raw,  media_sim * _SL_eff_sim)) if _SL_eff_sim < 1e5 else S_rss_raw

                    # ── Resumen de parámetros de simulación ───────────────────────
                    st.markdown(
                        "<p style='font-size:13px;color:#64748b;margin:0 0 12px 0;'>"
                        "Parámetros calculados automáticamente a partir del historial de "
                        "consumo y la configuración ingresada.</p>",
                        unsafe_allow_html=True,
                    )

                    # Fila 1 — parámetros clave de política
                    _pa, _pb, _pc, _pd = st.columns(4)
                    _pa.metric(
                        "Demanda diaria (λ)", f"{round(media_sim, 1):,.1f} u/día",
                        help="Tasa media de consumo diario estimada con el historial del medicamento.",
                    )
                    _pb.metric(
                        "Punto de reorden (s)", f"{s_sim:,} u",
                        help="Cuando el inventario disponible cae a este nivel, se emite un pedido.",
                    )
                    _pc.metric(
                        "Cantidad a pedir (Q*)", f"{Q_star_sim:,} u",
                        help="Lote de pedido económicamente óptimo, ajustado por perecibilidad.",
                    )
                    _pd.metric(
                        "Reserva de seguridad (SS)", f"{params_sim['SS']:,} u",
                        help="Colchón extra de stock para absorber variaciones en demanda o entrega.",
                    )

                    st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)

                    # Fila 2 — parámetros operacionales y costos
                    _po1, _po2, _po3, _po4, _po5 = st.columns(5)
                    _po1.metric(
                        "Tiempo entrega (LT)", f"{round(lead_time, 1)} días",
                        help="Días entre emitir el pedido y recibirlo en bodega.",
                    )
                    _po2.metric(
                        "Período revisión (R)", f"c/{round(periodo_revision, 1)} días",
                        help="Frecuencia con que se revisa el nivel de stock.",
                    )
                    _sl_label = f"{SL_sim} días" if SL_sim else "Sin límite"
                    _po3.metric(
                        "Vida útil (SL)", _sl_label,
                        help="Vida útil en días desde recepción. 'Sin límite' = no perecible.",
                    )
                    _po4.metric(
                        "Costo por orden", f"${_m(costo_orden)} CLP",
                        help="Costo fijo administrativo cada vez que se emite un pedido.",
                    )
                    _po5.metric(
                        "Costo mantener", f"${_m(costo_mantener)} CLP/u/día",
                        help="Costo diario de mantener una unidad en bodega.",
                    )

                    # Detalles técnicos (checkbox: expander no se puede anidar dentro de otro expander)
                    if st.checkbox("Ver parámetros técnicos completos", value=False, key="chk_tech_params"):
                        _sl_fuente = " (desde sidebar)" if SL_sim else ""
                        _sl_str = f"{SL_sim} días{_sl_fuente}" if SL_sim else "Sin restricción"
                        _dt1, _dt2, _dt3 = st.columns(3)
                        with _dt1:
                            st.markdown("**Demanda**")
                            st.markdown(f"""
| Parámetro | Valor |
|---|---|
| Varianza diaria (V) | {round(var_sim, 2)} u²/día |
| Horizonte simulado | 360 días |
| Réplicas | 5 |
""")
                        with _dt2:
                            st.markdown("**Operación**")
                            st.markdown(f"""
| Parámetro | Valor |
|---|---|
| LT efectivo (LT_ef) | {round(params_sim['LT_ef'], 3)} días |
| Nivel servicio (Z) | {Z} |
| Costo desperdicio (WC) | ${_m(int(WC_sim))} CLP/u |
""")
                        with _dt3:
                            st.markdown("**Política y perecibilidad**")
                            st.markdown(f"""
| Parámetro | Valor |
|---|---|
| EOQ base (Q) | {Q_sim:,} u |
| Undershoot (U) | {params_sim['U']:,} u |
| Q_max (restricción SL) | {Q_max_sim:,} u |
| E[O] caducidad | {E_O_sim:.2f} u/pedido |
| Inv. inicial (R,s,Q) | {S_rsq:,} u |
| Inv. inicial (R,S) | {S_rs:,} u |
| Inv. inicial (R,s,S) | {S_rss:,} u |
""")

                    st.divider()

                    # Limpiar resultados si el usuario cambia de medicamento
                    if st.session_state.get("_sim_med") != med_sim:
                        st.session_state.pop("_sim_cache", None)

                    if st.button("Ejecutar simulación", key="btn_sim", use_container_width=True):
                        def _recortar_sim(resultado, n_dias):
                            t_fin   = resultado[2][-1] if resultado[2] else 360
                            t_ini   = max(0.0, t_fin - n_dias)
                            idx_ini = next((i for i, t in enumerate(resultado[2]) if t >= t_ini), 0)
                            x  = resultado[2][idx_ini:]
                            oh = resultado[3][idx_ini:]
                            ip = resultado[5][idx_ini:]
                            if len(x) > 5000:           # limitar a 5000 puntos para no saturar WebSocket
                                step = len(x) // 5000
                                x, oh, ip = x[::step], oh[::step], ip[::step]
                            return x, oh, ip

                        _n_dias = max(periodo_revision * 4,
                                      min(max(float(periodo_revision), params_sim["Q"] / max(media_sim, 0.001)) * 15, 360.0))
                        _sl_arg = SL_sim if SL_sim else None
                        # Se pasa el LT real (no LT_ef) al simulador.
                        # LT_ef solo se usa en calcular_politicas() para dimensionar s y S.
                        # En simular() el LT debe ser el real para que los pedidos lleguen
                        # en el momento correcto (TNow + LT días).
                        LT_sim = lead_time
                        with st.spinner("Ejecutando simulaciónes..."):
                            r_rsq = simular(S_rsq, Q_star_sim, True,  None,
                                            media_sim, var_sim, costo_orden, costo_mantener,
                                            LT_sim, periodo_revision, s_sim, Q_max_sim,
                                            SL=_sl_arg, WC=WC_sim)
                            r_rs  = simular(S_rs,  None,        False, S_rs,
                                            media_sim, var_sim, costo_orden, costo_mantener,
                                            LT_sim, periodo_revision, s_sim, Q_max_sim,
                                            SL=_sl_arg, WC=WC_sim)
                            r_rss = simular(S_rss, None,        True,  S_rss,
                                            media_sim, var_sim, costo_orden, costo_mantener,
                                            LT_sim, periodo_revision, s_sim, Q_max_sim,
                                            SL=_sl_arg, WC=WC_sim)
                        st.session_state["_sim_med"]   = med_sim
                        st.session_state["_sim_cache"] = {
                            "rsq": (_recortar_sim(r_rsq, _n_dias), r_rsq[0], r_rsq[1], r_rsq[4], r_rsq[6]),
                            "rs":  (_recortar_sim(r_rs,  _n_dias), r_rs[0],  r_rs[1],  r_rs[4],  r_rs[6]),
                            "rss": (_recortar_sim(r_rss, _n_dias), r_rss[0], r_rss[1], r_rss[4], r_rss[6]),
                        }

                    if "_sim_cache" not in st.session_state:
                        st.info("Selecciona un medicamento y haz clic en **Ejecutar simulación**.")
                    else:
                        _sc = st.session_state["_sim_cache"]
                        costos_anuales  = {"(R,s,Q)": _sc["rsq"][2], "(R,S)": _sc["rs"][2], "(R,s,S)": _sc["rss"][2]}
                        quiebres_pol    = {"(R,s,Q)": _sc["rsq"][3], "(R,S)": _sc["rs"][3], "(R,s,S)": _sc["rss"][3]}
                        costos_diarios  = {"(R,s,Q)": _sc["rsq"][1], "(R,S)": _sc["rs"][1], "(R,s,S)": _sc["rss"][1]}
                        vencidas_pol    = {"(R,s,Q)": _sc["rsq"][4], "(R,S)": _sc["rs"][4], "(R,s,S)": _sc["rss"][4]}

                        # ── Selección jerárquica de la mejor política ─────────────────
                        # Nivel 1 (error tipo 1): mínimos quiebres de stock
                        min_quiebres = min(quiebres_pol.values())
                        cands_q      = [p for p, q in quiebres_pol.items() if q == min_quiebres]

                        # Nivel 2 (error tipo 2): entre iguales en quiebres, mínimos vencimientos
                        min_vencidas = min(vencidas_pol[p] for p in cands_q)
                        cands_v      = [p for p in cands_q if vencidas_pol[p] == min_vencidas]

                        # Nivel 3 (error tipo 3): entre iguales en quiebres y vencidos, menor costo
                        mejor        = min(cands_v, key=lambda p: costos_anuales[p])

                        # ── Tarjetas comparativas (una por política) ──────────────────
                        _eval_pol   = {}
                        _lcolor_pol = {"(R,s,Q)": "#1a3a5c", "(R,S)": "#2563eb", "(R,s,S)": "#16a34a"}

                        for pol in ["(R,s,Q)", "(R,S)", "(R,s,S)"]:
                            q_pol = quiebres_pol[pol]
                            if pol == mejor:
                                _eval_pol[pol] = "RECOMENDADA"
                            elif q_pol > min_quiebres:
                                _eval_pol[pol] = f"Más quiebres (+{q_pol - min_quiebres:,} u.)"
                            elif vencidas_pol[pol] > min_vencidas:
                                _eval_pol[pol] = f"Más vencimientos (+{vencidas_pol[pol] - min_vencidas:,} u.)"
                            else:
                                _dif_c = round((costos_anuales[pol] - costos_anuales[mejor]) / max(costos_anuales[mejor], 1) * 100, 1)
                                _eval_pol[pol] = f"Más costosa (+{_dif_c} %)"

                        _card_cols = st.columns(3)
                        for _col_c, pol in zip(_card_cols, ["(R,s,Q)", "(R,S)", "(R,s,S)"]):
                            _ev  = _eval_pol[pol]
                            _q   = quiebres_pol[pol]
                            _v   = vencidas_pol[pol]
                            _ca  = costos_anuales[pol]
                            _cd  = costos_diarios[pol]
                            _lc  = _lcolor_pol[pol]

                            if _ev == "RECOMENDADA":
                                _bc="#16a34a"; _bbg="#f0fdf4"; _bdg="#dcfce7"; _btx="#15803d"; _ico="★"
                            elif "quiebres" in _ev.lower():
                                _bc="#dc2626"; _bbg="white";   _bdg="#fee2e2"; _btx="#dc2626"; _ico="✕"
                            elif "vencimiento" in _ev.lower():
                                _bc="#d97706"; _bbg="white";   _bdg="#fef3c7"; _btx="#b45309"; _ico="!"
                            else:
                                _bc="#94a3b8"; _bbg="white";   _bdg="#f1f5f9"; _btx="#475569"; _ico="↑$"

                            _q_txt   = "Sin quiebres ✓" if _q == 0 else f"{_q:,} u. sin atender"
                            _q_color = "#16a34a" if _q == 0 else "#dc2626"

                            with _col_c:
                                st.markdown(
                                    f"<div style='border:2.5px solid {_bc};border-radius:14px;"
                                    f"padding:18px 20px;background:{_bbg};height:100%'>"
                                    # Código y nombre
                                    f"<div style='font-size:23px;font-weight:800;color:{_lc};"
                                    f"letter-spacing:-0.5px;margin-bottom:2px'>{pol}</div>"
                                    f"<div style='font-size:15px;font-weight:700;color:#1e293b;"
                                    f"margin-bottom:4px'>{NOMBRES[pol]}</div>"
                                    f"<div style='font-size:12px;color:#64748b;margin-bottom:14px;"
                                    f"line-height:1.4'>{DESCRIPCION[pol]}</div>"
                                    # Métricas
                                    f"<div style='border-top:1px solid #e2e8f0;padding-top:12px;"
                                    f"display:flex;flex-direction:column;gap:9px;margin-bottom:14px'>"
                                    f"<div style='display:flex;justify-content:space-between'>"
                                    f"<span style='color:#64748b;font-size:13px'>Quiebres de stock</span>"
                                    f"<span style='font-weight:700;color:{_q_color};font-size:13px'>{_q_txt}</span></div>"
                                    f"<div style='display:flex;justify-content:space-between'>"
                                    f"<span style='color:#64748b;font-size:13px'>Unidades vencidas</span>"
                                    f"<span style='font-weight:700;color:#1e293b;font-size:13px'>{_v:,} u.</span></div>"
                                    f"<div style='display:flex;justify-content:space-between'>"
                                    f"<span style='color:#64748b;font-size:13px'>Costo diario</span>"
                                    f"<span style='font-weight:700;color:#1e293b;font-size:13px'>${_cd:,.0f}</span></div>"
                                    f"<div style='display:flex;justify-content:space-between'>"
                                    f"<span style='color:#64748b;font-size:13px'>Costo anual</span>"
                                    f"<span style='font-weight:700;color:#1e293b;font-size:13px'>${_ca:,.0f}</span></div>"
                                    f"</div>"
                                    # Badge evaluación
                                    f"<div style='background:{_bdg};color:{_btx};font-weight:700;"
                                    f"font-size:14px;text-align:center;padding:8px 12px;border-radius:8px'>"
                                    f"{_ico} {_ev}</div>"
                                    f"</div>",
                                    unsafe_allow_html=True,
                                )

                        # ── Explicación del criterio que determinó la recomendación ───
                        criterios_aplicados = []
                        if min_quiebres == 0:
                            criterios_aplicados.append("sin quiebres de stock")
                        else:
                            criterios_aplicados.append(f"menor quiebres de stock ({min_quiebres} u.)")
                        if len(cands_q) > 1:
                            # El criterio de quiebres no alcanzó para desempatar
                            criterios_aplicados.append(f"menor unidades vencidas ({min_vencidas} u.)")
                        if len(cands_v) > 1:
                            # Tampoco el de vencidos; el costo fue el desempate final
                            criterios_aplicados.append("menor costo como criterio de desempate")

                        st.success(
                            f"**Estrategia recomendada: {NOMBRES[mejor]} ({mejor})** — {DESCRIPCION[mejor]}  \n"
                            f"Criterios aplicados (en orden de prioridad): "
                            f"{' → '.join(criterios_aplicados)}.  \n"
                            f"Quiebres: **{quiebres_pol[mejor]} u.** · "
                            f"Unidades vencidas: **{vencidas_pol[mejor]} u.** · "
                            f"Costo anual: **${costos_anuales[mejor]:,.0f} CLP**"
                        )

                        # ═══════════════════════════════════════════════════════
                        # SECCIÓN: RECOMENDACIÓN DE PEDIDO
                        # ═══════════════════════════════════════════════════════
                        st.divider()
                        st.subheader("Recomendación de pedido")
                        st.markdown(
                            "Ingresa el stock actual de **" + med_sim + "** para obtener una recomendación "
                            "concreta basada en la estrategia recomendada por la simulación."
                        )

                        _stock_act = st.number_input(
                            "Stock actual en bodega (unidades)",
                            min_value=0, value=int(s_sim), step=100,
                            key="rec_stock_act",
                            help="Unidades fisicamente disponibles en bodega en este momento.",
                        )

                        _ip_rec = int(_stock_act)
                        _dem_per   = int(round(media_sim * periodo_revision))   # demanda 1 período
                        _min_2per  = int(round(media_sim * 2 * periodo_revision))  # demanda 2 períodos

                        # Cantidad recomendada según mejor política
                        if mejor == "(R,s,Q)":
                            _q_pol  = int(Q_star_sim) if _ip_rec <= s_sim else 0
                            _s_obj  = S_rsq
                        elif mejor == "(R,S)":
                            _q_pol  = max(0, int(S_rs - _ip_rec))
                            _s_obj  = S_rs
                        else:  # (R,s,S)
                            _q_pol  = max(0, int(S_rss - _ip_rec)) if _ip_rec <= s_sim else 0
                            _s_obj  = S_rss

                        # Ajuste al mínimo de 2 períodos
                        _q_final_rec = max(_q_pol, _min_2per) if _q_pol > 0 else 0
                        _q_ajustado  = (_q_final_rec > _q_pol) and (_q_pol > 0)

                        # Proyecciones
                        _stock_prox_rev = max(0, int(_stock_act) - _dem_per)
                        _stock_tras_ped = int(min(_stock_act + _q_final_rec, _s_obj)) if _q_final_rec > 0 else int(_stock_act)

                        # Días hasta que la posición de inventario baja al umbral
                        if _ip_rec > s_sim and media_sim > 0:
                            _dias_al_umbral = (_ip_rec - s_sim) / media_sim
                        else:
                            _dias_al_umbral = 0.0

                        # Estado (semaforo)
                        if _ip_rec <= s_sim:
                            _sbg, _sbord = "#fee2e2", "#dc2626"
                            _stit = "Atención: se recomienda pedir ahora"
                            _smsg = (
                                f"Tu posición de inventario (<b>{_ip_rec:,} u.</b>) "
                                f"ya bajo el umbral de pedido (<b>{s_sim:,} u.</b>). "
                                f"Genera la orden de compra lo antes posible."
                            )
                        elif _dias_al_umbral < periodo_revision * 2:
                            _sbg, _sbord = "#fef9c3", "#d97706"
                            _stit = "Proximo pedido: en menos de 2 períodos"
                            _smsg = (
                                f"Tu stock llegara al umbral de pedido en aproximadamente "
                                f"<b>{_dias_al_umbral:.0f} días</b> "
                                f"({_dias_al_umbral / max(periodo_revision, 0.001):.1f} períodos de revisión). "
                                f"Considera preparar el pedido en la proxima revisión."
                            )
                        else:
                            _sbg, _sbord = "#dcfce7", "#16a34a"
                            _stit = "Stock en buen nivel"
                            _smsg = (
                                f"Tu stock esta <b>{int(_ip_rec - s_sim):,} u.</b> sobre el umbral de pedido, "
                                f"equivalente a aproximadamente <b>{_dias_al_umbral:.0f} días</b> de consumo adicional. "
                                f"No se requiere acción inmediata."
                            )

                        # ── Título de estado (grande y llamativo, sin caja) ───────────
                        if _ip_rec <= s_sim:
                            st.markdown(
                                f"<p style='color:#dc2626;font-size:22px;font-weight:700;"
                                f"margin:12px 0 4px 0;'>&#9888; {_stit}</p>"
                                f"<p style='color:#6b7280;font-size:14px;margin:0 0 12px 0;'>{_smsg}</p>",
                                unsafe_allow_html=True,
                            )
                        elif _sbord == "#d97706":
                            st.markdown(
                                f"<p style='color:#d97706;font-size:22px;font-weight:700;"
                                f"margin:12px 0 4px 0;'>&#9889; {_stit}</p>"
                                f"<p style='color:#6b7280;font-size:14px;margin:0 0 12px 0;'>{_smsg}</p>",
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                f"<p style='color:#16a34a;font-size:22px;font-weight:700;"
                                f"margin:12px 0 4px 0;'>&#10003; {_stit}</p>"
                                f"<p style='color:#6b7280;font-size:14px;margin:0 0 12px 0;'>{_smsg}</p>",
                                unsafe_allow_html=True,
                            )

                        # ── Métricas clave en tarjetas ────────────────────────────────
                        _ncols = 4 if _q_final_rec > 0 else 3
                        if _ncols == 4:
                            _mc1, _mc2, _mc3, _mc4 = st.columns(4)
                        else:
                            _mc1, _mc2, _mc3 = st.columns(3)

                        with _mc1:
                            if _q_final_rec > 0:
                                st.metric(
                                    "Pedir ahora",
                                    f"{_q_final_rec:,} u.",
                                    help="Cantidad recomendada a ordenar. Cubre al menos 2 períodos de demanda.",
                                )
                            else:
                                st.metric(
                                    "Estado del stock",
                                    "Sin pedido urgente",
                                    help="El inventario actual supera el umbral de pedido.",
                                )

                        with _mc2:
                            _delta_prox = _stock_prox_rev - s_sim
                            st.metric(
                                "Stock en proxima revisión",
                                f"~{_stock_prox_rev:,} u.",
                                delta=f"{_delta_prox:+,} vs umbral",
                                delta_color="normal" if _delta_prox >= 0 else "inverse",
                                help="Stock fisico estimado al llegar la proxima revisión (descontando demanda esperada).",
                            )

                        with _mc3:
                            if _q_final_rec > 0:
                                st.metric(
                                    "Stock tras llegada del pedido",
                                    f"~{_stock_tras_ped:,} u.",
                                    help="Stock estimado cuando llegue el pedido ordenado hoy.",
                                )
                            else:
                                st.metric(
                                    "Demanda por período",
                                    f"~{_dem_per:,} u.",
                                    help=f"Demanda esperada en {periodo_revision} día(s).",
                                )

                        if _ncols == 4:
                            with _mc4:
                                st.metric(
                                    "Demanda por período",
                                    f"~{_dem_per:,} u.",
                                    help=f"Demanda esperada en {periodo_revision} día(s).",
                                )

                        # ── Barra de contexto secundario ──────────────────────────────
                        _ctx_parts = [
                            f"<b>Estrategia:</b> {NOMBRES[mejor]} ({mejor})",
                            f"<b>Umbral de pedido:</b> {s_sim:,} u.",
                            f"<b>Revisión cada:</b> {periodo_revision} día(s)",
                        ]
                        if _q_ajustado:
                            _ctx_parts.append(
                                f"<b>Cant. según política:</b> {_q_pol:,} u. "
                                f"<i>(ajustado a min. 2 períodos: {_q_final_rec:,} u.)</i>"
                            )
                        if _dias_al_umbral > 0 and _q_final_rec == 0:
                            _prox_ord_d = math.ceil(_dias_al_umbral / max(periodo_revision, 0.001)) * periodo_revision
                            _ctx_parts.append(f"<b>Proximo pedido estimado:</b> en ~{_prox_ord_d:.0f} días")
                        st.markdown(
                            "<div style='background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;"
                            "padding:10px 16px;font-size:13px;color:#475569;margin-top:8px;'>"
                            + " &nbsp;|&nbsp; ".join(_ctx_parts)
                            + "</div>",
                            unsafe_allow_html=True,
                        )

                        # ═══════════════════════════════════════════════════════
                        # SECCIÓN: GRAFICOS
                        # ═══════════════════════════════════════════════════════
                        st.divider()
                        st.markdown("### Evolucion del stock en bodega — ultimas semanas de simulación")
                        st.markdown(
                            "Los gráficos muestran como sube y baja el stock de medicamento a lo largo del tiempo "
                            "bajo cada estrategia de pedido. El patron en **dientes de sierra** es normal: "
                            "el stock baja con la demanda diaria y sube cuando llega un pedido."
                        )

                        # ── Referencias horizontales con etiquetas legibles ───────────────
                        refs_por_politica = {
                            "(R,s,Q)": [
                                (params_sim["SS"], "#d97706", f"Reserva mínima: {params_sim['SS']:,} u."),
                                (s_sim,            "#dc2626", f"Umbral de pedido: {s_sim:,} u."),
                                (S_rsq,            "#16a34a", f"Nivel máximo: {S_rsq:,} u."),
                            ],
                            "(R,S)": [
                                (params_sim["SS"], "#d97706", f"Reserva mínima: {params_sim['SS']:,} u."),
                                (S_rs,             "#16a34a", f"Nivel máximo: {S_rs:,} u."),
                            ],
                            "(R,s,S)": [
                                (params_sim["SS"], "#d97706", f"Reserva mínima: {params_sim['SS']:,} u."),
                                (s_sim,            "#dc2626", f"Umbral de pedido: {s_sim:,} u."),
                                (S_rss,            "#16a34a", f"Nivel máximo: {S_rss:,} u."),
                            ],
                        }

                        _colores_pol = {
                            "(R,s,Q)": "#1a3a5c",
                            "(R,S)":   "#2563eb",
                            "(R,s,S)": "#16a34a",
                        }
                        _titulos_sim = [
                            "Estrategia 1 — Pedido de cantidad fija  (R,s,Q)",
                            "Estrategia 2 — Reponer hasta el nivel máximo  (R,S)",
                            "Estrategia 3 — Pedido variable hasta el nivel máximo  (R,s,S)",
                        ]

                        fig_sim = make_subplots(
                            rows=3, cols=1,
                            shared_xaxes=True,
                            subplot_titles=_titulos_sim,
                            vertical_spacing=0.10,
                        )

                        _pols_orden = [("(R,s,Q)", 1), ("(R,S)", 2), ("(R,s,S)", 3)]
                        for pol, num_fila in _pols_orden:
                            _clave = pol.lower().replace(",", "").replace("(", "").replace(")", "")
                            x_datos, y_oh, y_ip = _sc[_clave][0]
                            _col = _colores_pol[pol]
                            _mostrar_leyenda = (num_fila == 1)

                            # Línea sólida: stock físico en bodega
                            fig_sim.add_trace(go.Scatter(
                                x=x_datos, y=y_oh, mode="lines",
                                name="Stock físico en bodega",
                                legendgroup="oh",
                                line=dict(color=_col, width=2.2),
                                showlegend=_mostrar_leyenda,
                                hovertemplate=(
                                    "<b>Día %{x:.0f}</b><br>"
                                    "Stock en bodega: <b>%{y:,.0f} u.</b><extra></extra>"
                                ),
                            ), row=num_fila, col=1)

                            # Línea punteada: posición de inventario (incluye pedidos en camino)
                            fig_sim.add_trace(go.Scatter(
                                x=x_datos, y=y_ip, mode="lines",
                                name="Stock + pedidos en camino",
                                legendgroup="ip",
                                line=dict(color=_col, width=1.3, dash="dot"),
                                opacity=0.6,
                                showlegend=_mostrar_leyenda,
                                hovertemplate=(
                                    "<b>Día %{x:.0f}</b><br>"
                                    "Stock + pedidos en camino: <b>%{y:,.0f} u.</b><extra></extra>"
                                ),
                            ), row=num_fila, col=1)

                            # Líneas de referencia con etiquetas claras
                            for _nivel, _color_ref, _etiqueta in refs_por_politica[pol]:
                                fig_sim.add_hline(
                                    y=_nivel,
                                    line_dash="dash",
                                    line_color=_color_ref,
                                    line_width=1.3,
                                    annotation_text=_etiqueta,
                                    annotation_position="right",
                                    annotation_font_size=10,
                                    annotation_font_color=_color_ref,
                                    row=num_fila, col=1,
                                )

                        # Agrandar solo los títulos de subplot (los 3 primeros annotations
                        # que añade make_subplots); los de add_hline vienen después y
                        # ya tienen su color propio — no los tocamos.
                        for ann in fig_sim.layout.annotations[:3]:
                            ann.font.size = 13
                            ann.font.color = "#1e293b"

                        fig_sim.update_layout(
                            height=950,
                            margin=dict(t=65, b=100, l=95, r=195),
                            paper_bgcolor="white",
                            plot_bgcolor="#f8fafc",
                            font=dict(family="sans-serif", size=12, color="#1e293b"),
                            # Leyenda debajo de los 3 gráficos para no tapar los titulos
                            legend=dict(
                                orientation="h",
                                x=0.5, xanchor="center",
                                y=-0.07, yanchor="top",
                                font=dict(size=12),
                                bgcolor="rgba(255,255,255,0.9)",
                                bordercolor="#cbd5e1",
                                borderwidth=1,
                            ),
                            hoverlabel=dict(
                                bgcolor="white",
                                font_size=12,
                                bordercolor="#94a3b8",
                            ),
                        )

                        # Eje X: etiqueta en fila 3, marcas en todas
                        fig_sim.update_xaxes(
                            title_text="Día de simulación",
                            title_font_size=12,
                            tickfont_size=11,
                            gridcolor="#e2e8f0",
                            row=3, col=1,
                        )
                        for _fila in [1, 2]:
                            fig_sim.update_xaxes(
                                tickfont_size=11,
                                gridcolor="#e2e8f0",
                                row=_fila, col=1,
                            )

                        # Eje Y: etiqueta y formato en las 3 filas
                        for _fila in [1, 2, 3]:
                            fig_sim.update_yaxes(
                                title_text="Unidades en bodega",
                                tickformat=",",
                                title_font_size=11,
                                tickfont_size=11,
                                gridcolor="#e2e8f0",
                                row=_fila, col=1,
                            )

                        st.plotly_chart(fig_sim, use_container_width=True)

                        # Guia de colores al pie del gráfico
                        st.markdown(
                            "<div style='background:#f1f5f9;border-radius:10px;padding:14px 20px;"
                            "font-size:13px;line-height:2.1;border:1px solid #e2e8f0;margin-top:4px;'>"
                            "<b>Guia de lineas de referencia</b><br>"
                            "<span style='color:#dc2626;font-weight:bold'>&#9135;&#9135; Roja</span>"
                            " — Umbral de pedido: cuando el stock (o la posición de inventario) cae "
                            "hasta este nivel, se genera una nueva orden de compra.<br>"
                            "<span style='color:#16a34a;font-weight:bold'>&#9135;&#9135; Verde</span>"
                            " — Nivel máximo (S): tope de inventario al que se repone en cada pedido. "
                            "El stock no deberia superar este valor habitualmente.<br>"
                            "<span style='color:#d97706;font-weight:bold'>&#9135;&#9135; Naranja</span>"
                            " — Reserva de seguridad: colchon mínimo para absorber variaciones "
                            "inesperadas en la demanda o retrasos en la entrega.<br>"
                            "<span style='color:#1e293b;font-size:12px'>"
                            "Linea solida = stock fisico en bodega &nbsp;|&nbsp; "
                            "Linea punteada = stock + pedidos en camino</span>"
                            "</div>",
                            unsafe_allow_html=True,
                        )

                # ── Tabla de abastecimiento — todos los medicamentos ──────────────
                st.divider()
                st.markdown("### Tabla de abastecimiento — todos los medicamentos")
                st.markdown(
                    "Esta tabla resume las recomendaciones de pedido calculadas automáticamente "
                    "para **cada medicamento** de la farmacia. Muestra cuándo pedir, cuánto pedir "
                    "y el nivel máximo recomendado de inventario, según el historial de consumo y "
                    "los parámetros configurados en el panel lateral.  \n"
                    "Los productos más urgentes aparecen primero: primero los que hay que **dar de baja** "
                    "(vencidos), luego los que hay que **pedir ahora** (bajo el punto de reorden), "
                    "después los que hay que **pedir pronto**, y finalmente los que tienen "
                    "**existencias suficientes**."
                )
                with st.expander("Ver tabla completa de abastecimiento", expanded=True):
                    t3a, t3b = st.columns([3, 2])
                    busq_t3 = t3a.text_input("Buscar:", placeholder="Nombre del producto...", key="busq_t3")
                    acciones_disp = []
                    for acción in ["Dar de baja", "Pedir ahora", "Pedir pronto", "Existencias suficientes"]:
                        if acción in df_politicas["Acción recomendada"].values:
                            acciones_disp.append(acción)
                    filtro_accion = t3b.multiselect("Filtrar por acción:", acciones_disp, default=acciones_disp, key="filtro_accion_t3")
                    df_vis = df_politicas[df_politicas["Acción recomendada"].isin(filtro_accion)].drop(columns="_media", errors="ignore")
                    if busq_t3.strip():
                        df_vis = df_vis[df_vis["Medicamento"].str.contains(busq_t3.strip(), case=False, na=False)]
                    st.caption(f"{len(df_vis)} producto(s)")
                    st.dataframe(_safe_df(df_vis), use_container_width=True, hide_index=True, height=400)
                    st.info(
                        "**Guía de columnas:**  \n"
                        "**Pedir cuando queden menos de X** = punto de reorden (s): nivel al que se debe emitir una orden para no quedarse sin stock durante el tiempo de entrega.  \n"
                        "**Cuánto pedir** = cantidad económica óptima (EOQ): minimiza la suma de costos de pedir y de mantener inventario.  \n"
                        "**Reserva de seguridad** = colchón extra para absorber variaciones inesperadas en la demanda o demoras del proveedor.  \n"
                        "**Nivel máximo** = tope de inventario recomendado para evitar exceso de existencias."
                    )
                    if len(df_vis) > 0:
                        _costo_vals_ab = (
                            pd.to_numeric(resumen["costo_unitario"], errors="coerce").fillna(0)
                            if "costo_unitario" in resumen.columns
                            else pd.Series(0.0, index=resumen.index)
                        )
                        _costo_map_ab = dict(zip(resumen[COL_CODIGO].astype(str), _costo_vals_ab))
                        _df_vis_dl = df_vis.copy()
                        _df_vis_dl["Costo unitario (CLP)"] = (
                            _df_vis_dl["Código"].astype(str).map(_costo_map_ab).fillna(0)
                        )
                        _df_vis_dl["Costo estimado pedido (CLP)"] = (
                            pd.to_numeric(_df_vis_dl["Cuánto pedir"], errors="coerce").fillna(0) *
                            _df_vis_dl["Costo unitario (CLP)"]
                        ).round(0).astype(int)
                        _buf_ped = io.BytesIO()
                        _df_vis_dl.to_excel(_buf_ped, index=False, engine="openpyxl")
                        st.download_button(
                            label=f"Descargar tabla ({len(df_vis)} producto(s))",
                            data=_buf_ped.getvalue(),
                            file_name=f"abastecimiento_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True,
                            key="dl_abastecimiento",
                        )

    # ══════════════════════════════════════════════════════════════════════
    # SUB-TAB: HORIZONTE RODANTE (Gurobi MIP + Bayesiano Gamma-Poisson)
    # ══════════════════════════════════════════════════════════════════════
    with _t3_rh:

        if not tiene_movimientos:
            st.warning("Se requiere el archivo de movimientos para calcular el pronóstico.")
        else:
            # ── Selector de medicamento ───────────────────────────────────
            _rh_meds = resumen[resumen["media_diaria"] > 0].sort_values(
                "media_diaria", ascending=False
            )[COL_NOMBRE].dropna().tolist()
            if not _rh_meds:
                st.warning("No hay medicamentos con historial de consumo.")
            else:
                _rh_med = st.selectbox("Medicamento:", _rh_meds, key="rh_med_sel")
                _rh_row = resumen[resumen[COL_NOMBRE] == _rh_med].iloc[0]

                # Detectar cambio de medicamento y limpiar recomendaciones anteriores
                if st.session_state.get("_rh_prev_med_sel") != _rh_med:
                    st.session_state.pop("rh_recommended_inv", None)
                    st.session_state.pop("rh_inv_ini_w",       None)
                    st.session_state["_rh_prev_med_sel"] = _rh_med

                # ── Construir consumo mensual desde movimientos ───────────
                _rh_mov = datos_movimientos[
                    datos_movimientos[COL_MOV_CODIGO] == str(_rh_row[COL_CODIGO])
                ].copy()
                _rh_mov[COL_MOV_FECHA]    = pd.to_datetime(_rh_mov[COL_MOV_FECHA], dayfirst=True, errors="coerce")
                _rh_mov[COL_MOV_CANTIDAD] = pd.to_numeric(_rh_mov[COL_MOV_CANTIDAD], errors="coerce").fillna(0)
                _rh_mov = _rh_mov.dropna(subset=[COL_MOV_FECHA])

                _rh_mensual = (
                    _rh_mov.set_index(COL_MOV_FECHA)
                    .resample("MS")[COL_MOV_CANTIDAD].sum()
                    .reset_index()
                )
                _rh_consumo_list = _rh_mensual[COL_MOV_CANTIDAD].astype(int).tolist()
                _rh_dias_list    = [
                    pd.Timestamp(d).days_in_month
                    for d in _rh_mensual[COL_MOV_FECHA]
                ]
                # Calcular días del mes siguiente (igual que en Paracetamol_RH.py)
                _ultimo_mes_ts   = pd.Timestamp(_rh_mensual[COL_MOV_FECHA].iloc[-1])
                _mes_sig_ts      = _ultimo_mes_ts + pd.DateOffset(months=1)
                _dias_mes_sig    = _mes_sig_ts.days_in_month
                # Reemplazar el último elemento de _rh_dias_list por el mes siguiente
                _rh_dias_sig     = _rh_dias_list + [_dias_mes_sig]

                if len(_rh_consumo_list) < 2:
                    st.info("Se necesitan al menos 2 meses de historial para el pronóstico Bayesiano.")
                else:
                    # ── λ para el formulario (sin mostrar gráfico) ────────
                    _bf_pre   = bayesian_forecast(_rh_consumo_list, _rh_dias_sig)
                    _lambda_d = _bf_pre["lambda_diario_hat"]

                    # ── Horizonte Rodante MIP (PuLP/CBC, sin licencia) ───
                    # SL solo desde sidebar (Programa de compras no tiene FVenvimiento)
                    _rh_sl_default = int(vida_util_dias) if vida_util_dias > 0 else 30

                    st.markdown("#### Parámetros del Horizonte Rodante")
                    st.caption("Selecciona el medicamento, ajusta los parámetros y presiona **Ejecutar** — la página no recarga hasta ese momento.")

                    # Valor por defecto de inventario inicial = tl × λ_d  (mínimo para evitar quiebre inicial)
                    # Tras cada ejecución se actualiza a (tl+R) × λ_d con el lambda del medicamento real.
                    _rh_tl_default  = int(lead_time)
                    _rh_inv_min_cur = max(int(round(_rh_tl_default * _lambda_d)), 1)
                    _rh_inv_default = st.session_state.get("rh_recommended_inv", _rh_inv_min_cur)

                    # Aplicar el valor recomendado al widget ANTES de renderizar el formulario.
                    # Si hay un reset pendiente (tras una ejecución) o si el widget aún no existe,
                    # se pre-carga con _rh_inv_default para que el campo muestre el valor correcto.
                    if st.session_state.pop("_rh_inv_pending_reset", False) or \
                            "rh_inv_ini_w" not in st.session_state:
                        st.session_state["rh_inv_ini_w"] = max(_rh_inv_default, 1)

                    with st.form("form_rh"):
                        _rh_med_form = st.selectbox(
                            "Medicamento a simular:",
                            _rh_meds,
                            index=_rh_meds.index(_rh_med) if _rh_med in _rh_meds else 0,
                            key="rh_med_form",
                        )
                        _rh_inv_ini = st.number_input(
                            "Inventario inicial (unidades)",
                            key="rh_inv_ini_w",
                            min_value=0, step=100,
                            help=(
                                "Stock con que parte la simulación el día 1. "
                                "Mínimo recomendado = lead_time × λ_diario (para no tener quiebres antes de la primera entrega). "
                                "Tras cada ejecución el campo se actualiza automáticamente al valor recomendado."
                            ),
                        )
                        _rh_c1, _rh_c2, _rh_c3 = st.columns(3)
                        with _rh_c1:
                            _rh_L    = st.number_input("Vida útil L (días, slots)",
                                                        value=max(_rh_sl_default, 2),
                                                        min_value=2, step=1,
                                                        help="Pre-llenado desde FVenvimiento. Unidades en slot L-1 se contabilizan como vencidas.")
                            _rh_tl   = st.number_input("Lead time tl (días)",
                                                        value=int(lead_time), min_value=1, step=1)
                        with _rh_c2:
                            _rh_R    = st.number_input("Intervalo mínimo entre pedidos R (días)",
                                                        value=3, min_value=1, step=1,
                                                        help="No se puede pedir dos veces dentro de este intervalo.")
                            _rh_Qmax = st.number_input("Cantidad máxima por pedido (Qmax)",
                                                        value=max(int(_lambda_d * 30 * 5), 1000),
                                                        min_value=1, step=100)
                            _rh_ss_d = st.number_input(
                                "Stock de seguridad (días)",
                                value=1, min_value=0, step=1,
                                help=(
                                    "Colchón mínimo que el modelo mantiene en todo momento "
                                    "(= días × λ_diario). Con ≥ 1 el stock nunca llega a 0 "
                                    "en régimen estacionario, protegiéndote ante variaciones "
                                    "de demanda o retrasos de entrega."
                                ),
                            )
                        with _rh_c3:
                            _rh_h    = st.number_input("Costo holding (h, $/u/día)",
                                                        value=int(costo_mantener), min_value=0, step=1)
                            _rh_k    = st.number_input("Costo orden (k, $)",
                                                        value=int(costo_orden), min_value=0, step=1000)
                            _rh_w    = st.number_input("Costo vencimiento (w, $/u)",
                                                        value=max(int(costo_desperdicio), 1), min_value=0, step=100,
                                                        help="Penalización por unidades vencidas. Típicamente el costo de compra por unidad.")
                            _rh_s    = st.number_input("Costo quiebre stock (s, $/u)",
                                                        value=10_000_000, min_value=1, step=1_000_000,
                                                        help="Penalización por demanda insatisfecha. Debe ser MUY superior al costo de orden (k) para que el modelo SIEMPRE prefiera pedir antes de quedar sin stock.")
                        _btn_rh = st.form_submit_button("Ejecutar Horizonte Rodante",
                                                         use_container_width=True, type="primary")

                    # ── Ejecutar Horizonte Rodante ────────────────────
                    if st.session_state.get("_rh_med") != _rh_med:
                        st.session_state.pop("_rh_cache", None)

                    if _btn_rh:
                        # Recalcular lambda con el medicamento elegido en el formulario
                        _rh_med = _rh_med_form
                        _rh_row = resumen[resumen[COL_NOMBRE] == _rh_med].iloc[0]
                        _rh_mov2 = datos_movimientos[
                            datos_movimientos[COL_MOV_CODIGO] == str(_rh_row[COL_CODIGO])
                        ].copy()
                        _rh_mov2[COL_MOV_FECHA]    = pd.to_datetime(_rh_mov2[COL_MOV_FECHA], dayfirst=True, errors="coerce")
                        _rh_mov2[COL_MOV_CANTIDAD] = pd.to_numeric(_rh_mov2[COL_MOV_CANTIDAD], errors="coerce").fillna(0)
                        _rh_mensual2 = (
                            _rh_mov2.dropna(subset=[COL_MOV_FECHA])
                            .set_index(COL_MOV_FECHA)
                            .resample("MS")[COL_MOV_CANTIDAD].sum()
                            .reset_index()
                        )
                        _cons2   = _rh_mensual2[COL_MOV_CANTIDAD].astype(int).tolist()
                        _dias2   = [pd.Timestamp(d).days_in_month for d in _rh_mensual2[COL_MOV_FECHA]]
                        _dias2s  = _dias2 + [( pd.Timestamp(_rh_mensual2[COL_MOV_FECHA].iloc[-1]) + pd.DateOffset(months=1)).days_in_month] if _dias2 else [30]
                        _bf2     = bayesian_forecast(_cons2, _dias2s)
                        _lambda_d = _bf2["lambda_diario_hat"]

                        # Actualizar el inventario recomendado en session_state para el próximo render
                        _rh_rec_inv = max(int(round((_rh_tl + _rh_R) * _lambda_d)), 1)
                        st.session_state["rh_recommended_inv"]  = _rh_rec_inv
                        # Marcar que el campo de inventario debe pre-cargarse con el nuevo valor
                        st.session_state["_rh_inv_pending_reset"] = True

                        # Advertir si el inventario inicial es insuficiente para cubrir el lead time
                        _inv_min_lt = int(_rh_tl * _lambda_d)
                        if _rh_inv_ini < _inv_min_lt:
                            _dias_cubiertos = int(_rh_inv_ini / max(_lambda_d, 1))
                            _dias_quiebre   = _rh_tl - _dias_cubiertos
                            st.warning(
                                f"⚠️ **Inventario inicial insuficiente.** "
                                f"Con {_rh_inv_ini:,} u y λ = {_lambda_d:.0f} u/día el stock se agota "
                                f"en ≈ {_dias_cubiertos} días, pero el primer pedido tarda {_rh_tl} días "
                                f"en llegar → **{_dias_quiebre} días sin stock** al inicio de la simulación. "
                                f"El campo ya fue actualizado a **{_rh_rec_inv:,} u** "
                                f"= ({_rh_tl}+{_rh_R}) × {_lambda_d:.0f} u/día. "
                                f"Vuelve a ejecutar para eliminar los quiebres."
                            )

                        # N_ITER = días del mes a pronosticar (mes siguiente al último dato)
                        # igual que Paracetamol_RH.py: DIAS_MES_SIGUIENTE = calendar.monthrange(MES_SIGUIENTE...)
                        _WINDOW        = 5
                        _N_ITER        = _dias2s[-1]

                        np.random.seed(42)
                        _demand_hist = [int(np.random.poisson(_lambda_d)) for _ in range(_WINDOW)]

                        _inv_st = {a: 0 for a in range(_rh_L)}
                        _inv_st[0] = int(_rh_inv_ini)

                        _results_rh = []
                        _pending_rh = []
                        _last_order = -_rh_R
                        _failed     = False

                        _bar = st.progress(0, text="Optimizando días...")
                        for _it in range(_N_ITER):
                            _day = _WINDOW + _it
                            _dh, _dlo, _dhi = _forecast_demand_rh(_demand_hist)

                            _arr_hoy = sum(q for (a, q) in _pending_rh if a == _day)
                            _inv_st[0] += _arr_hoy
                            _pending_rh = [(a, q) for (a, q) in _pending_rh if a != _day]

                            _cd     = max(0, _rh_R - (_day - _last_order))
                            _ss_u   = int(_rh_ss_d * _dh)   # SS en unidades = días × λ̂ del día
                            _sol = _solve_horizon_rh(
                                _inv_st, _dh, _day, _pending_rh, _cd,
                                _rh_L, _rh_tl, _rh_R, _rh_Qmax,
                                _rh_h, _rh_k, _rh_w, _rh_s,
                                ss_units=_ss_u,
                            )
                            if _sol is None:
                                st.error(f"Sin solución óptima en el día {_day}.")
                                _failed = True
                                break

                            _Qv, _Yv, _Wv, _Sv, _new_inv = _sol
                            if _Qv > 0:
                                _pending_rh.append((_day + _rh_tl, _Qv))
                                _last_order = _day

                            _inv_st  = _new_inv
                            _stk_tot = sum(_inv_st.values())
                            _demand_hist.append(_dh)

                            _results_rh.append({
                                "Día": _day, "d̂": _dh,
                                "IC lo": _dlo, "IC hi": _dhi,
                                "Pedido (Q)": _Qv, "¿Pide?": "Sí" if _Yv else "No",
                                "Vencidas (W)": _Wv, "Faltante (S)": _Sv,
                                "Stock total": _stk_tot,
                            })
                            _bar.progress((_it + 1) / _N_ITER,
                                          text=f"Día {_day}/{_WINDOW + _N_ITER - 1}")

                        _bar.empty()
                        if not _failed and _results_rh:
                            st.session_state["_rh_med"]   = _rh_med
                            st.session_state["_rh_cache"] = {
                                "results":  _results_rh,
                                "lambda_d": _lambda_d,
                                "inv_fin":  _inv_st,
                                "h_cost":   _rh_h,
                                "k_cost":   _rh_k,
                                "w_cost":   _rh_w,
                            }

                    # ── Mostrar resultados ────────────────────────────
                    if "_rh_cache" in st.session_state and st.session_state.get("_rh_med") == _rh_med:
                            _rh_c  = st.session_state["_rh_cache"]
                            _df_rh = pd.DataFrame(_rh_c["results"])

                            st.markdown("#### Resumen del mes simulado")
                            # ── Fila 1: métricas de servicio ──────────────
                            _sr1, _sr2, _sr3, _sr4, _sr5 = st.columns(5)
                            _sr1.metric("Días simulados", len(_df_rh))
                            _sr2.metric("Demanda total estimada",
                                        f"{_m(int(_df_rh['d̂'].sum()))} u")
                            _n_ord = int(_df_rh['¿Pide?'].eq('Sí').sum())
                            _sr3.metric("Total pedido",
                                        f"{_m(int(_df_rh['Pedido (Q)'].sum()))} u",
                                        delta=f"{_n_ord} órdenes emitidas",
                                        delta_color="off")
                            _sr4.metric("Unidades vencidas",
                                        f"{_m(int(_df_rh['Vencidas (W)'].sum()))} u")
                            _n_dias_q = int((_df_rh["Faltante (S)"] > 0).sum())
                            _sr5.metric("Demanda insatisfecha",
                                        f"{_m(int(_df_rh['Faltante (S)'].sum()))} u",
                                        delta=f"{_n_dias_q} día{'s' if _n_dias_q!=1 else ''} con quiebre real",
                                        delta_color="inverse" if _n_dias_q > 0 else "off")

                            # ── Fila 2: costos ─────────────────────────────
                            _h_c = _rh_c.get("h_cost", 0)
                            _k_c = _rh_c.get("k_cost", 0)
                            _w_c = _rh_c.get("w_cost", 0)
                            _costo_hold  = int(_df_rh["Stock total"].sum() * _h_c)
                            _costo_ord   = _n_ord * int(_k_c)
                            _costo_desp  = int(_df_rh["Vencidas (W)"].sum() * _w_c)
                            _costo_falt  = int(_df_rh["Faltante (S)"].sum() * _w_c)
                            _costo_total = _costo_hold + _costo_ord + _costo_desp + _costo_falt
                            st.markdown("<div style='margin-top:4px'></div>", unsafe_allow_html=True)
                            _sc1, _sc2, _sc3, _sc4, _sc5 = st.columns(5)
                            _sc1.metric("Costo total del mes",
                                        f"${_m(_costo_total)} CLP",
                                        help="Suma de todos los costos: holding + órdenes + desperdicio + faltante.")
                            _sc2.metric("Costo holding",
                                        f"${_m(_costo_hold)} CLP",
                                        help="Costo de mantener inventario (stock diario × h).")
                            _sc3.metric("Costo por órdenes",
                                        f"${_m(_costo_ord)} CLP",
                                        help=f"{_n_ord} órdenes × ${_m(int(_k_c))} CLP/orden.")
                            _sc4.metric("Costo desperdicio",
                                        f"${_m(_costo_desp)} CLP",
                                        help="Unidades vencidas × w.")
                            _sc5.metric("Costo faltante",
                                        f"${_m(_costo_falt)} CLP",
                                        help="Demanda insatisfecha × w.")

                            _fig_rh = go.Figure()
                            _fig_rh.add_trace(go.Scatter(
                                x=_df_rh["Día"], y=_df_rh["Stock total"],
                                mode="lines", name="Stock total",
                                line=dict(color="#2563eb", width=2),
                            ))
                            _fig_rh.add_trace(go.Bar(
                                x=_df_rh["Día"], y=_df_rh["Pedido (Q)"],
                                name="Pedido (Q)", marker_color="#9AE6B4", opacity=0.7,
                                yaxis="y2",
                            ))
                            for _dp in _df_rh[_df_rh["¿Pide?"] == "Sí"]["Día"].tolist():
                                _fig_rh.add_vline(x=_dp, line_dash="dot", line_color="#16a34a",
                                                  line_width=1.2, opacity=0.7)
                            # Zona roja: días con QUIEBRE REAL (S > 0) — distintos del stock
                            # llegando a 0 después de cubrir demanda (que es comportamiento normal)
                            _mask_s = _df_rh["Faltante (S)"] > 0
                            if _mask_s.any():
                                _fig_rh.add_trace(go.Bar(
                                    x=_df_rh.loc[_mask_s, "Día"],
                                    y=_df_rh.loc[_mask_s, "Faltante (S)"],
                                    name="Quiebre real (S>0)",
                                    marker_color="#ef4444", opacity=0.75,
                                    yaxis="y2",
                                ))
                            if _df_rh["Vencidas (W)"].sum() > 0:
                                _fig_rh.add_trace(go.Bar(
                                    x=_df_rh["Día"], y=_df_rh["Vencidas (W)"],
                                    name="Vencidas", marker_color="#fca5a5", opacity=0.7,
                                    yaxis="y2",
                                ))
                            _fig_rh.update_layout(
                                height=380, margin=dict(t=20, b=40, l=60, r=80),
                                xaxis_title="Día del mes simulado",
                                yaxis=dict(title="Stock total (u)", tickformat=","),
                                yaxis2=dict(title="Pedido / Quiebre / Vencidas (u)",
                                            overlaying="y", side="right", showgrid=False),
                                legend=dict(orientation="h", y=-0.18, x=0),
                                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#f8fafc",
                            )
                            st.plotly_chart(_fig_rh, use_container_width=True)
                            # Explicar el patrón diente de sierra
                            if _n_dias_q == 0:
                                st.success(
                                    "✅ **Sin quiebres de stock.** El stock llega a 0 al final de algunos días "
                                    "porque el inventario se agota justo antes de la próxima entrega — "
                                    "esto es el comportamiento **óptimo** del modelo (no sobra ni falta stock). "
                                    "La demanda de esos días fue cubierta en su totalidad."
                                )
                            else:
                                _dias_lista = _df_rh.loc[_mask_s, "Día"].tolist()
                                _rango = (f"días {_dias_lista[0]}–{_dias_lista[-1]}"
                                          if len(_dias_lista) > 1 else f"día {_dias_lista[0]}")
                                st.warning(
                                    f"⚠️ **Quiebres reales en {_rango}** ({_n_dias_q} días, "
                                    f"{_m(int(_df_rh['Faltante (S)'].sum()))} u en total). "
                                    f"Fuera de ese período el stock llega a 0 entre ciclos pero "
                                    f"**S = 0** — la demanda se cubrió, es agotamiento óptimo normal."
                                )
                            st.caption(
                                "Línea azul = stock total al final del día. "
                                "Barras verdes = cantidad pedida. "
                                "Barras rojas = quiebre real (demanda sin cubrir, S > 0). "
                                "Líneas punteadas = días en que se ordenó."
                            )
                            st.markdown("#### Detalle diario")
                            _df_rh_show = _df_rh.rename(columns={
                                "d̂": "Demanda estimada",
                                "IC lo": "IC 90% inf.",
                                "IC hi": "IC 90% sup.",
                            })
                            st.dataframe(_safe_df(_df_rh_show), use_container_width=True,
                                         hide_index=True, height=380)
                            _buf_rh = io.BytesIO()
                            _safe_df(_df_rh_show).to_excel(_buf_rh, index=False, engine="openpyxl")
                            st.download_button(
                                label="Descargar resultados del Horizonte Rodante",
                                data=_buf_rh.getvalue(),
                                file_name=f"horizonte_rodante_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx",
                                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                key="dl_rh",
                            )
                    else:
                        st.info("Configura los parámetros y haz clic en **Ejecutar Horizonte Rodante**.")

