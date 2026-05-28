
import streamlit as st
import pandas as pd
import numpy as np
import math
import io
import re
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import date, timedelta
import pytz
import gc
import streamlit.components.v1 as _components
from streamlit_autorefresh import st_autorefresh
import requests as _requests
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

def encontrar_columna(df, palabras_clave, ya_usadas):
    if df is None:
        return None
    for columna in df.columns:
        if columna in ya_usadas:
            continue
        nombre = str(columna).lower().replace("_", " ").replace("-", " ")
        for palabra in palabras_clave:
            if palabra in nombre:
                ya_usadas.add(columna)
                return columna
    return None

# ──────────────────────────────────────────────────────────────────────────────
def calcular_estado(dias):
    if pd.isna(dias): return "Sin fecha"
    if dias < 0:      return "VENCIDO"
    if dias <= 30:    return "CRITICO"
    if dias <= 90:    return "ADVERTENCIA"
    return "NORMAL"

# ──────────────────────────────────────────────────────────────────────────────
# FUNCIÓN: CALCULAR PARÁMETROS DE INVENTARIO
# Calcula s, Q, S, SS y U igual que en el notebook de políticas.
# ──────────────────────────────────────────────────────────────────────────────
def calcular_politicas(Media, V, OC, HC, LT, R, Z=1.645):
    # s cubre la demanda durante el lead time completo + un período de revisión
    U  = math.ceil((Media / (2 * V)) + ((V * R) / 2))
    s  = math.ceil((Media * (LT + R)) + Z * (V ** 0.5) * ((LT + R) ** 0.5))
    Q  = math.ceil(((2 * OC * Media) / HC) ** 0.5)
    S  = s + Q + U
    SS = max(0, math.ceil((Media * R) + (Z * (V ** 0.5) * ((LT + R) ** 0.5) - U)))

    return {"s": s, "Q": Q, "S": S, "SS": SS, "U": U}


# ──────────────────────────────────────────────────────────────────────────────
# FUNCIÓN: RECOMENDAR PERÍODO DE REVISIÓN
# Calcula cada cuántos días conviene revisar según el consumo.
# ──────────────────────────────────────────────────────────────────────────────
def recomendar_periodo(media_diaria, varianza_diaria, costo_orden, costo_mantener, lead_time):
    d = max(media_diaria, 0.001)
    Q = math.ceil(((2 * costo_orden * d) / costo_mantener) ** 0.5)
    R = Q / d

    if R < lead_time:
        R = lead_time

    if R <= 7:
        return 7, "Semanal (7 días)"
    if R <= 14:
        return 14, "Quincenal (14 días)"
    if R <= 21:
        return 21, "Cada 3 semanas (21 días)"
    if R <= 30:
        return 30, "Mensual (30 días)"

    r_redondeado = round(R / 7) * 7
    return int(r_redondeado), "Cada " + str(int(r_redondeado)) + " días"


# ──────────────────────────────────────────────────────────────────────────────
# SIMULACIONES POR EVENTOS (tiempo continuo) — réplica del notebook de referencia.
#
# La demanda sigue un proceso de Poisson con tasa Media (u/día):
#   tiempo entre llegadas ~ Exp(Media)  →  t = (-1/Media) * ln(U), U ~ Unif(0,1)
#
# Eventos posibles en cada paso:
#   1. Llegada de demanda (una unidad)
#   2. Revisión de inventario (cada R días)
#   3. Llegada de un pedido (LT días después de ser colocado)
#
# Se hacen NR réplicas y se promedian los costos.
# ──────────────────────────────────────────────────────────────────────────────
def _simular(Media, V, OC, HC, LT, R, s, Q, S_inicio, politica, NR=5, TiempoTotal=360):
    """
    Núcleo de simulación por eventos (tiempo continuo) para las tres políticas.
    S_inicio es el nivel máximo al que se repone en (R,S) y (R,s,S);
    en (R,s,Q) es solo el inventario inicial.

    La demanda diaria sigue una distribución Poisson con tasa Media:
      N_d ~ Poisson(Media)  →  entero aleatorio, algunos días más, otros menos
    Cada unidad del día d se ubica en un instante uniforme dentro de [d, d+1].
    Esto equivale exactamente al proceso de Poisson homogéneo del notebook de
    referencia (inter-llegadas ~ Exp(1/Media)), con la variabilidad visible
    día a día que muestra el gráfico.
    """
    CostoTotalReplicas   = 0.0
    CostoDiarioReplicas  = 0.0
    QuiebresTotalReplicas = 0   # unidades de demanda no atendidas (acumulado entre réplicas)
    Inventario_final     = []
    Tiempo_final         = []

    total_dias = int(TiempoTotal + LT + R) + 10

    for replica in range(NR):
        np.random.seed(replica)

        # Demanda diaria: N_d ~ Poisson(Media)
        # Variance = Media por día  →  consistente con calcular_politicas (V = Media)
        daily_counts = np.random.poisson(lam=Media, size=total_dias)
        # Cada unidad se coloca en un instante uniforme dentro de su día
        day_nums = np.repeat(np.arange(total_dias, dtype=float), daily_counts)
        if day_nums.size > 0:
            offsets      = np.random.uniform(0.0, 1.0, day_nums.size)
            demand_times = np.sort(day_nums + offsets)
        else:
            demand_times = np.array([float('inf')])
        d_idx = 0   # puntero al próximo evento de demanda

        TNow       = 0.0
        OH         = float(S_inicio)
        IT         = 0.0
        CostoTotal = 0.0
        Tiempo_Ant = 0.0
        Quiebres   = 0   # unidades sin atender en esta réplica

        Evento_Revisar = float(R)
        arrivals = []   # lista de (tiempo_llegada, cantidad)

        Inventario = [OH]
        Tiempo_sim = [TNow]
        IP_sim     = [OH]       # Posición de Inventario = OH + IT (IT=0 al inicio)

        while TNow <= TiempoTotal:
            next_demand  = demand_times[d_idx] if d_idx < demand_times.size else float('inf')
            next_arrival = arrivals[0][0]       if arrivals       else float('inf')

            # Prioridad: demanda (estricto <), luego revisión, luego llegada
            if next_demand < min(Evento_Revisar, next_arrival):
                TNow = next_demand
                CostoTotal += OH * (TNow - Tiempo_Ant) * HC
                Tiempo_Ant  = TNow
                if OH > 0:
                    OH -= 1
                else:
                    Quiebres += 1   # unidad demandada sin stock disponible

                d_idx += 1

            elif Evento_Revisar <= next_arrival:
                TNow = Evento_Revisar
                CostoTotal += OH * (TNow - Tiempo_Ant) * HC
                Tiempo_Ant  = TNow
                IP = OH + IT

                if politica == "rsq":
                    if IP <= s:
                        IT += Q
                        arrivals.append((TNow + LT, Q))
                        CostoTotal += OC

                elif politica == "rs":
                    # Reponer hasta el nivel máximo S_inicio en cada revisión
                    cant = float(max(0.0, S_inicio - IP))
                    if cant > 0:
                        IT += cant
                        arrivals.append((TNow + LT, cant))
                        CostoTotal += OC

                else:   # rss — reponer hasta S_inicio solo cuando IP ≤ s
                    if IP <= s:
                        cant = float(max(0.0, S_inicio - IP))
                        if cant > 0:
                            IT += cant
                            arrivals.append((TNow + LT, cant))
                            CostoTotal += OC

                Evento_Revisar = TNow + R

            else:
                t_arr, cant = arrivals.pop(0)
                TNow = t_arr
                CostoTotal += OH * (TNow - Tiempo_Ant) * HC
                Tiempo_Ant  = TNow
                OH += cant
                IT -= cant

            Inventario.append(OH)
            Tiempo_sim.append(TNow)
            IP_sim.append(OH + IT)   # IP = inventario físico + pedidos en tránsito

        CostoTotalReplicas    += CostoTotal
        CostoDiarioReplicas   += CostoTotal / TiempoTotal
        QuiebresTotalReplicas += Quiebres
        Inventario_final = Inventario
        Tiempo_final     = Tiempo_sim
        IP_final         = IP_sim    # Posición de Inventario de la última réplica

    costo_anual       = round(CostoTotalReplicas  / NR)
    costo_diario      = round(CostoDiarioReplicas / NR)
    quiebres_promedio = round(QuiebresTotalReplicas / NR)
    return costo_diario, costo_anual, Tiempo_final, Inventario_final, quiebres_promedio, IP_final


def simular_rsq(Media, V, OC, HC, LT, R, s, Q, S, NR=5, TiempoTotal=360):
    return _simular(Media, V, OC, HC, LT, R, s, Q, S,   "rsq", NR, TiempoTotal)

def simular_rs(Media, V, OC, HC, LT, R, s, Q, S, NR=5, TiempoTotal=360):
    return _simular(Media, V, OC, HC, LT, R, s, Q, S,   "rs",  NR, TiempoTotal)

def simular_rss(Media, V, OC, HC, LT, R, s, Q, S, NR=5, TiempoTotal=360):
    return _simular(Media, V, OC, HC, LT, R, s, Q, S,   "rss", NR, TiempoTotal)


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
    Lee una hoja de Excel detectando si los encabezados reales están en la fila 1 o en la fila 4.
    El formato del hospital a veces tiene un título fusionado en las primeras 3 filas,
    y los encabezados reales (CODIGO, NOMBRE, ...) empiezan en la fila 4.
    """
    # Leer solo la primera fila para ver qué hay en el encabezado
    df_prueba = pd.read_excel(io.BytesIO(archivo_bytes), sheet_name=nombre_hoja, header=0, nrows=1)
    primera_col = str(df_prueba.columns[0]).lower()
    # Si la primera columna ya dice "codigo" o "sku", los encabezados están en fila 1
    if "codigo" in primera_col or "sku" in primera_col:
        return pd.read_excel(io.BytesIO(archivo_bytes), sheet_name=nombre_hoja, header=0)
    else:
        # Si no, los encabezados están en la fila 4 (índice 3)
        return pd.read_excel(io.BytesIO(archivo_bytes), sheet_name=nombre_hoja, header=3)

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
        col_l = str(col).lower().strip()
        if ("codigo" in col_l or "código" in col_l) and col_codigo is None:
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
        if "stccritico" in nombre_c:
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
        codigo = row[col_codigo]
        nombre = row[col_nombre]
        if pd.isna(codigo) or pd.isna(nombre):
            continue
        cod = str(codigo).strip()
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
        "costo_orden": 40000, "costo_mantener": 10, "lead_time": 7, "periodo_revision": 7,
        "fecha_revision": date.today(), "hora_revision": None, "responsable": "",
        "archivos":       [],   # [{nombre, size, cargado_en, responsable, preview, n_productos, mov, inv_extra, inv_directo}]
        "historial":      [],   # [{Fecha, Responsable, Accion, Archivo, Productos}]
        "archivos_bytes": {},   # {nombre: bytes_originales} — para descargar el archivo original + filas nuevas
        "gd_file_ids":    {},   # {nombre_archivo: file_id_en_drive}
        "gd_mov_id":      None, # file_id del Excel de movimientos consolidado en Drive
    }


def _guardar_params(fecha, hora, resp, c_orden, c_mant, lt, pr):
    store = _store_global()
    store["fecha_revision"]   = fecha
    store["hora_revision"]    = hora
    store["responsable"]      = resp
    store["costo_orden"]      = c_orden
    store["costo_mantener"]   = c_mant
    store["lead_time"]        = lt
    store["periodo_revision"] = pr


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
            if any(k in str(c).lower() for k in keywords):
                return c
        return None

    _c_cod  = _find_col(_df_orig, ["matcod", "codigo", "cod_mat"])
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

    # Buscar el archivo de inventario (tiene columnas tipo Existencia, Codigo, Material, etc.)
    _archivo_inv_bytes = None
    _archivo_inv_nom   = None
    for _nom, _bts in _bytes_map.items():
        try:
            # El inventario tiene cabecera en fila 2 (índice 2)
            _df_test = pd.read_excel(io.BytesIO(_bts), header=2, nrows=1)
            _cols_l  = [str(c).lower() for c in _df_test.columns]
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
            if any(k in str(c).lower() for k in keywords):
                return c
        return None

    _c_cod  = _find_col(_df_inv, ["codigo", "cod"])
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

# ── Google Drive helpers ────────────────────────────────────────────────────────
@st.cache_resource
def _gd_service():
    """Crea y cachea el cliente de Google Drive via service account en st.secrets.
    Retorna None si las credenciales no están configuradas."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        _info  = dict(st.secrets["gcp_service_account"])
        _creds = service_account.Credentials.from_service_account_info(
            _info, scopes=["https://www.googleapis.com/auth/drive"]
        )
        return build("drive", "v3", credentials=_creds, cache_discovery=False)
    except Exception:
        return None


def _gd_folder_id():
    """Retorna el folder_id de Drive desde st.secrets, o None si no existe."""
    try:
        return str(st.secrets["google_drive"]["folder_id"])
    except Exception:
        return None


def _gd_find_file(svc, nombre, folder_id):
    """Busca un archivo por nombre en la carpeta. Retorna file_id o None."""
    try:
        _q   = f"name='{nombre}' and '{folder_id}' in parents and trashed=false"
        _res = svc.files().list(q=_q, fields="files(id,name)").execute()
        _fl  = _res.get("files", [])
        return _fl[0]["id"] if _fl else None
    except Exception:
        return None


def _gd_list_files(svc, folder_id):
    """Lista archivos xlsx/csv en la carpeta. Retorna [{id, name, modifiedTime}, ...]."""
    try:
        _q = (f"'{folder_id}' in parents and trashed=false and "
              "(mimeType='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' "
              "or mimeType='text/csv')")
        _res = svc.files().list(
            q=_q, fields="files(id,name,modifiedTime)", orderBy="modifiedTime desc"
        ).execute()
        return _res.get("files", [])
    except Exception:
        return []


def _gd_upload_file(svc, bytes_data, nombre, folder_id, file_id=None):
    """Sube o actualiza un archivo en Drive. Retorna el file_id resultante o None."""
    try:
        from googleapiclient.http import MediaIoBaseUpload
        _mime  = ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                  if nombre.lower().endswith(".xlsx") else "text/csv")
        _media = MediaIoBaseUpload(io.BytesIO(bytes_data), mimetype=_mime, resumable=False)
        if file_id:
            _f = svc.files().update(fileId=file_id, media_body=_media, fields="id").execute()
        else:
            _meta = {"name": nombre, "parents": [folder_id]}
            _f    = svc.files().create(body=_meta, media_body=_media, fields="id").execute()
        return _f.get("id")
    except Exception:
        return None


def _gd_download_file(svc, file_id):
    """Descarga un archivo de Drive. Retorna bytes o None."""
    try:
        from googleapiclient.http import MediaIoBaseDownload
        _req  = svc.files().get_media(fileId=file_id)
        _buf  = io.BytesIO()
        _dl   = MediaIoBaseDownload(_buf, _req)
        _done = False
        while not _done:
            _, _done = _dl.next_chunk()
        return _buf.getvalue()
    except Exception:
        return None


def _gd_guardar_original(nombre, bytes_data):
    """Guarda los bytes originales de un archivo en Drive. Retorna (ok, msg)."""
    _svc = _gd_service()
    _fid = _gd_folder_id()
    if not _svc or not _fid:
        return False, "Drive no configurado"
    try:
        _store  = _store_global()
        _ids    = _store.setdefault("gd_file_ids", {})
        _old_id = _ids.get(nombre) or _gd_find_file(_svc, nombre, _fid)
        _new_id = _gd_upload_file(_svc, bytes_data, nombre, _fid, _old_id)
        if _new_id:
            _ids[nombre] = _new_id
            return True, f"'{nombre}' guardado en Drive"
        return False, f"Error al subir '{nombre}'"
    except Exception as _e:
        return False, str(_e)


def _gd_guardar_movimientos():
    """Guarda el Excel de movimientos consolidados en Drive. Retorna (ok, msg)."""
    _svc = _gd_service()
    _fid = _gd_folder_id()
    if not _svc or not _fid:
        return False, "Drive no configurado"
    try:
        _store       = _store_global()
        _mov_b, _    = _excel_mov_actualizado(_store.get("movimientos", []))
        _drive_nom   = "SAVIA_movimientos.xlsx"
        _old_id      = _store.get("gd_mov_id") or _gd_find_file(_svc, _drive_nom, _fid)
        _new_id      = _gd_upload_file(_svc, _mov_b, _drive_nom, _fid, _old_id)
        if _new_id:
            _store["gd_mov_id"] = _new_id
            return True, "Movimientos guardados en Drive"
        return False, "Error al guardar movimientos en Drive"
    except Exception as _e:
        return False, str(_e)


def _gd_cargar_desde_drive():
    """Descarga y procesa todos los archivos de la carpeta Drive.
    Retorna (n_cargados, mensaje)."""
    _svc = _gd_service()
    _fid = _gd_folder_id()
    if not _svc or not _fid:
        return 0, "Drive no configurado"
    _files = _gd_list_files(_svc, _fid)
    if not _files:
        return 0, "No hay archivos en la carpeta de Drive"
    _s_gd    = _store_global()
    _ya_gd   = {a["nombre"] for a in _s_gd["archivos"]}
    _cargados = 0
    _tz_gd   = pytz.timezone("America/Santiago")
    _ahora_gd = pd.Timestamp.now(tz=_tz_gd).strftime("%Y-%m-%d %H:%M")
    _resp_gd  = _s_gd.get("responsable", "") or "Google Drive"
    for _gdf in _files:
        _nom_gd = _gdf["name"]
        if _nom_gd == "SAVIA_movimientos.xlsx":   # archivo interno — no reprocesar
            continue
        if _nom_gd in _ya_gd:                     # ya cargado
            continue
        _bytes_gd = _gd_download_file(_svc, _gdf["id"])
        if _bytes_gd is None:
            continue
        _rec_gd = _parsear_archivo(_nom_gd, _bytes_gd)
        if _rec_gd is None:
            continue
        if len(_bytes_gd) <= 5 * 1024 * 1024:
            _s_gd.setdefault("archivos_bytes", {})[_nom_gd] = _bytes_gd
        _s_gd.setdefault("gd_file_ids", {})[_nom_gd] = _gdf["id"]
        _s_gd["archivos"].append({
            "nombre":      _nom_gd,
            "size":        len(_bytes_gd),
            "mov":         _rec_gd["mov"],
            "inv_extra":   _rec_gd["inv_extra"],
            "inv_directo": _rec_gd["inv_directo"],
            "cargado_en":  _ahora_gd,
            "responsable": _resp_gd,
            "preview":     _rec_gd["preview"],
            "n_productos": _rec_gd["n_productos"],
        })
        _s_gd["historial"].append({
            "Fecha":       _ahora_gd,
            "Responsable": _resp_gd,
            "Accion":      "Carga desde Drive",
            "Archivo":     _nom_gd,
            "Productos":   _rec_gd["n_productos"],
        })
        _ya_gd.add(_nom_gd)
        _cargados += 1
    if _cargados:
        _recompute()
    return _cargados, (f"{_cargados} archivo(s) cargado(s) correctamente desde Drive."
                       if _cargados else "No hay archivos nuevos para cargar.")


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
        productos.columns = [str(c) for c in productos.columns]
        store["inv"] = productos;  store["mov"] = mov_comb;  store["formato_hospital"] = True
        # Guardar archivos de inventario estándar (lotes + vencimientos) aunque haya formato hospital
        if inv_dirs:
            _il = pd.concat(inv_dirs, ignore_index=True)
            _il.columns = [str(c) for c in _il.columns]
            store["inv_lotes"] = _il
        else:
            store["inv_lotes"] = None
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
    st.caption("Para seleccionar varios archivos a la vez: Cmd+clic (Mac) o Ctrl+clic (Windows).")
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
                    "Accion":      "Carga",
                    "Archivo":     _nom,
                    "Productos":   _rec["n_productos"],
                })
                _n_ok += 1
        gc.collect()
        _recompute()
        if _n_ok:
            st.success(f"{_n_ok} archivo(s) procesado(s) correctamente.")
            # Auto-guardar en Google Drive si está configurado
            if _gd_service() and _gd_folder_id():
                for _nom_ag, _bytes_ag in _s.get("archivos_bytes", {}).items():
                    _gd_guardar_original(_nom_ag, _bytes_ag)
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
                                "Accion":      "Eliminacion",
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
    lead_time        = st.number_input("Tiempo de entrega CENABAST (días)", value=_s["lead_time"],        step=1)
    periodo_revision = st.number_input("Período de revisión (días)",        value=_s["periodo_revision"], step=1)
    Z = 1.881  # nivel de servicio 97%

_guardar_params(fecha_revision, hora_revision, responsable,
                costo_orden, costo_mantener, lead_time, periodo_revision)

# ── Webhook Make.com (alertas automáticas) ────────────────────────────────────
with st.sidebar.expander("Alertas automáticas (Make.com)", expanded=False):
    st.caption("Pega aquí la URL del webhook de Make para recibir alertas cuando el stock baje del punto de reorden o cuando haya lotes rechazados.")
    _wh_stored = _store_global().get("webhook_url", "")
    _wh_input  = st.text_input("URL del webhook:", value=_wh_stored,
                               placeholder="https://hook.eu2.make.com/...",
                               key="wh_url_input", label_visibility="collapsed")
    if _wh_input != _wh_stored:
        _store_global()["webhook_url"] = _wh_input.strip()

# ── Google Drive (persistencia de datos entre sesiones) ───────────────────────
with st.sidebar.expander("Google Drive (persistencia)", expanded=False):
    _gd_svc_sb  = _gd_service()
    _gd_fid_sb  = _gd_folder_id()
    _gd_conn_sb = (_gd_svc_sb is not None) and (_gd_fid_sb is not None)

    if not _gd_conn_sb:
        st.caption(
            "Sin credenciales configuradas. "
            "Agrega `gcp_service_account` y `google_drive.folder_id` "
            "en `.streamlit/secrets.toml` para activar la persistencia automática."
        )
    else:
        st.success("✅ Conectado a Google Drive")
        _gd_files_sb = _gd_list_files(_gd_svc_sb, _gd_fid_sb)

        # Mostrar archivos en Drive
        if _gd_files_sb:
            _nombres_gd = [f for f in _gd_files_sb if f["name"] != "SAVIA_movimientos.xlsx"]
            if _nombres_gd:
                st.caption(f"Archivos en Drive ({len(_nombres_gd)}):")
                for _gdf_sb in _nombres_gd[:6]:
                    _ts_sb = _gdf_sb.get("modifiedTime", "")[:10]
                    st.caption(f"  📄 {_gdf_sb['name']}  ·  {_ts_sb}")
                if len(_nombres_gd) > 6:
                    st.caption(f"  … y {len(_nombres_gd) - 6} más")
            else:
                st.caption("No hay archivos de datos en Drive aún.")
        else:
            st.caption("La carpeta de Drive está vacía.")

        # Botón: cargar desde Drive
        if st.button("⬇ Cargar desde Drive", key="gd_load_btn", use_container_width=True):
            with st.spinner("Descargando desde Drive…"):
                _n_gd, _msg_gd = _gd_cargar_desde_drive()
            if _n_gd:
                st.success(_msg_gd)
                st.rerun()
            else:
                st.info(_msg_gd)

        # Botón: guardar manualmente en Drive
        if st.button("⬆ Guardar en Drive ahora", key="gd_save_btn", use_container_width=True):
            _s_gd_sb = _store_global()
            _saved_gd = 0
            with st.spinner("Subiendo archivos a Drive…"):
                for _n_gd_sb, _b_gd_sb in _s_gd_sb.get("archivos_bytes", {}).items():
                    _ok_gd_sb, _ = _gd_guardar_original(_n_gd_sb, _b_gd_sb)
                    if _ok_gd_sb:
                        _saved_gd += 1
            if _saved_gd:
                st.success(f"✓ {_saved_gd} archivo(s) guardado(s) en Drive.")
            else:
                st.info("No hay archivos para guardar (carga datos primero).")

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
    # ── Opción de cargar desde Google Drive antes de pedir subida manual ──
    _gd_svc_main = _gd_service()
    _gd_fid_main = _gd_folder_id()
    if _gd_svc_main and _gd_fid_main:
        _gd_fl_main = _gd_list_files(_gd_svc_main, _gd_fid_main)
        _gd_fl_data = [f for f in _gd_fl_main if f["name"] != "SAVIA_movimientos.xlsx"]
        if _gd_fl_data:
            st.info(
                f"Se encontraron **{len(_gd_fl_data)} archivo(s)** guardados en Google Drive. "
                "¿Deseas cargarlos automáticamente?"
            )
            _col_gd1, _col_gd2 = st.columns(2)
            with _col_gd1:
                if st.button("Cargar desde Drive", type="primary", use_container_width=True, key="gd_autoload"):
                    with st.spinner("Descargando desde Drive…"):
                        _n_gd_main, _msg_gd_main = _gd_cargar_desde_drive()
                    if _n_gd_main:
                        st.success(_msg_gd_main)
                        st.rerun()
                    else:
                        st.warning(_msg_gd_main)
            with _col_gd2:
                if st.button("Subir archivo nuevo", use_container_width=True, key="gd_skip"):
                    st.info("Usa el panel izquierdo para subir tus archivos.")
            st.stop()
    st.info("Sube un archivo en el panel izquierdo")
    st.stop()

# Aviso cuando se cargó un archivo de consumos del hospital (sin stock ni vencimiento)
if _g.get("formato_hospital", False):
    st.info(
        "Archivo de consumos del hospital cargado correctamente.  \n"
        "Los datos de **existencias actuales** y **fecha de vencimiento** no están en este tipo de archivo, "
        "por lo que las alertas de vencimiento no estarán disponibles.  \n"
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
    IL_COD  = encontrar_columna(datos_inv_lotes, ["codigo", "sku", "clave"],                        _il_usadas)
    IL_NOM  = encontrar_columna(datos_inv_lotes, ["material", "nombre", "medicamento", "descripcion"], _il_usadas)
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
COL_CODIGO      = encontrar_columna(datos_inventario, ["codigo", "sku", "clave", "articulo", "referencia"],             usadas_inv)
COL_NOMBRE      = encontrar_columna(datos_inventario, ["nombre", "medicamento", "farmaco", "descripcion"],              usadas_inv)
COL_LOTE        = encontrar_columna(datos_inventario, ["lote", "batch", "partida"],                                     usadas_inv)
COL_VENCIMIENTO = encontrar_columna(datos_inventario, ["vencimiento", "vence", "caducidad", "expiry", "fec venc", "vto"], usadas_inv)
COL_STOCK       = encontrar_columna(datos_inventario, ["stock", "existencia", "disponible", "inventario", "saldo"],     usadas_inv)
COL_COSTO       = encontrar_columna(datos_inventario, ["costo", "cost", "precio compra", "valor compra", "precio"],     usadas_inv)
COL_MARCA       = encontrar_columna(datos_inventario, ["marca", "laboratorio", "fabricante"],                           usadas_inv)
COL_UNIDAD      = encontrar_columna(datos_inventario, ["unidad", "medida", "presentacion"],                             usadas_inv)


# Si no se detectó alguna columna esencial, el usuario la elige manualmente
cols_disponibles = list(datos_inventario.columns)
if not COL_CODIGO:      COL_CODIGO      = st.selectbox("Columna de CÓDIGO:",      cols_disponibles)
if not COL_NOMBRE:      COL_NOMBRE      = st.selectbox("Columna de NOMBRE:",      cols_disponibles)
if not COL_VENCIMIENTO: COL_VENCIMIENTO = st.selectbox("Columna de VENCIMIENTO:", cols_disponibles)
if not COL_STOCK:       COL_STOCK       = st.selectbox("Columna de STOCK:",       cols_disponibles)

# Detectar columnas de movimientos (con su propio set para no mezclar con inventario)
if datos_movimientos is not None:
    usadas_mov       = set()
    COL_MOV_CODIGO   = encontrar_columna(datos_movimientos, ["codigo", "sku", "nombre", "medicamento"], usadas_mov)
    COL_MOV_FECHA    = encontrar_columna(datos_movimientos, ["fecha", "date", "periodo", "mes"],         usadas_mov)
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
    n_lotes         = (COL_STOCK,    "count"),  # cuenta cuántas filas (lotes) hay
    costo_unitario  = (COL_COSTO,    "mean"),
).reset_index()

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
#   4. Media = ceil(lambda_estable)   [tasa diaria de la dist. Poisson]
#   5. V = min(Media, var(tamaños_de_lote))  [varianza de los lotes, no /30]
# ──────────────────────────────────────────────────────────────────────────────
if tiene_movimientos:
    mov = datos_movimientos.copy()
    mov[COL_MOV_CANTIDAD] = pd.to_numeric(mov[COL_MOV_CANTIDAD], errors="coerce").fillna(0)
    mov[COL_MOV_FECHA]    = pd.to_datetime(mov[COL_MOV_FECHA], dayfirst=True, errors="coerce")

    def _parametros_llegada(df_prod):
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

        # lambda_i = demanda_i / días_desde_pedido_anterior  (igual que el notebook)
        k       = min(len(dias_entre), n - 1)
        lambdas = batch_vals[1: k + 1] / dias_entre[:k]

        lambda_estable = lambdas.mean()
        if lambda_estable <= 0 or np.isnan(lambda_estable):
            return pd.Series({"media_diaria": 0.0, "var_diaria": 0.0})

        media     = math.ceil(lambda_estable)
        var_batch = float(pd.Series(batch_vals).var())
        if np.isnan(var_batch) or var_batch <= 0:
            var_batch = float(media)
        V = min(float(media), var_batch)

        return pd.Series({"media_diaria": float(media), "var_diaria": V})

    # Calcular parámetros para cada producto sin deprecaciones de pandas 2.x
    filas_params = []
    for codigo_p, df_grupo in mov.groupby(COL_MOV_CODIGO):
        params = _parametros_llegada(df_grupo)
        filas_params.append({
            COL_CODIGO:      codigo_p,
            "media_diaria":  params["media_diaria"],
            "var_diaria":    params["var_diaria"],
        })
    tabla_parametros = pd.DataFrame(filas_params)

    resumen = resumen.merge(tabla_parametros, on=COL_CODIGO, how="left")
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
tab1, tab2, tab3, tab4 = st.tabs([
    "Panel Principal",
    "Seguimiento",
    "Movimientos",
    "Abastecimiento",
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
    PALETA = {"sin_stock": "#E53E3E", "critico": "#DD6B20", "bajo": "#D69E2E",
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

    _fi5.metric("Total productos",  f"{len(resumen):,}",
                help="Cantidad de medicamentos distintos actualmente en el inventario.")
    _fi6.metric("Pérdida estimada", f"{_pct_perdida:.1f}%",
                help="Porcentaje del valor total en existencias que corresponde a medicamentos vencidos. Un valor alto indica pérdida económica por caducidad.")

    st.markdown("<div style='margin:12px 0'></div>", unsafe_allow_html=True)

    # ── 3. Semáforo — un círculo por estado ──────────────────────────────────
    st.markdown(_ayuda(
        "<b>Semáforo de cobertura</b> — Cada círculo muestra cuántos medicamentos se encuentran en ese estado. "
        "<b>Rojo</b> = sin existencias o vencidos (acción inmediata). "
        "<b>Naranja</b> = cobertura crítica, menos de 1 mes de existencias. "
        "<b>Amarillo</b> = cobertura baja, entre 1 y 3 meses. "
        "<b>Verde</b> = cobertura adecuada, más de 3 meses."
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
            _col_d = [PALETA["sin_stock"], PALETA["critico"], PALETA["bajo"], PALETA["adecuado"]]
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
            _col_map_e = {"VENCIDO": PALETA["sin_stock"], "CRITICO": PALETA["critico"],
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
        st.caption("Haz clic en una categoría del grafico para filtrar la tabla de productos por ese estado.")

        # Tabla filtrada por estado seleccionado
        if _sel != "Todos":
            if formato_hospital and _cat_map and "_estado_cob" in resumen.columns:
                _cob_val  = _cat_map.get(_sel, _sel)
                _tbl_filt = resumen[resumen["_estado_cob"] == _cob_val].copy()
            else:
                _tbl_filt = resumen[resumen["estado"] == _sel].copy()

            _c_show = [COL_CODIGO, COL_NOMBRE, "stock_total"]
            if not formato_hospital:
                for _c in ["min_dias_vencer", "estado"]:
                    if _c in _tbl_filt.columns: _c_show.append(_c)
            else:
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
                if "min_dias_vencer" in _urg.columns and not formato_hospital: _uc.append("min_dias_vencer")
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
            _lb   = [f"{int(v):,}" for v in _top10["consumo_mensual"]]
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
                _vc_fmt   = [f"{int(v):,}" for v in _vc_df["Valor"]]
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
            _rk1.metric("Productos en estado seleccionado", f"{_n_prod:,}")
            _rk2.metric("Requieren pedido",                 f"{_n_pedir:,}")
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
                    f'<td style="padding:8px 12px;text-align:right;font-weight:600">{int(_drow["Productos"]):,}</td>'
                    f'<td style="padding:8px 12px;text-align:right">{int(_drow["Unidades_totales"]):,}</td>'
                    f'</tr>'
                )
            _tbl_html += '</tbody></table>'
            st.markdown(_tbl_html, unsafe_allow_html=True)
        else:
            st.info("Selecciona al menos un estado para ver los KPIs.")

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
                "Usa el filtro para ver la distribucion de un medicamento especifico."
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
                f'<div style="font-size:1.15rem;font-weight:800;color:#0f172a">{int(_bd_total):,} u</div>'
                f'<div style="font-size:0.75rem;color:#64748b">{len(_bod_cols)} bodegas · {len(resumen):,} medicamentos</div>'
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
                f"Existencias: <b>{int(_bd_stk[k]):,}</b> u<br>"
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
            st.caption("Pasa el cursor sobre cada nodo para ver el nombre de la bodega, las unidades en existencia y su participacion porcentual sobre el total.")

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
                    "ALCANCE": "Cobertura (m)",
                }).reset_index(drop=True)

                st.markdown(
                    f'<div style="font-size:0.80rem;color:#64748b;margin-bottom:6px">'
                    f'<b>{len(_bd_show):,}</b> productos con existencias en <b>{_bd_det_sel}</b></div>',
                    unsafe_allow_html=True,
                )
                st.dataframe(_safe_df(_bd_show), use_container_width=True, hide_index=True, height=320)

    # ══════════════════════════════════════════════════════════════════════════
    # SUB-TAB 1 — INVENTARIO
    # ══════════════════════════════════════════════════════════════════════════
    with _t2_inv:
        st.markdown(_ayuda(
            "<b>Tabla de inventario</b> — Lista completa de medicamentos con sus existencias actuales, cobertura estimada y prioridad de reposicion. "
            "La tabla esta ordenada por <b>urgencia</b>: primero aparecen los productos sin existencias, luego los criticos, y al final los que estan bien abastecidos. "
            "<b>Cobertura (meses)</b>: tiempo estimado que duran las existencias actuales al ritmo de consumo historico. "
            "<b>Cant. sugerida</b>: unidades recomendadas a pedir segun el modelo de inventario configurado. "
            "Usa el buscador y el filtro de estado para enfocarte en productos especificos."
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
        for _cx, _lx, _vx, _sx, _cxc in [
            (_t2c1, "Productos en vista",   f"{_t2n:,}",    "según filtros activos",  "#3182CE"),
            (_t2c2, "Sin existencias",      f"{_t2_sin:,}", _t2_pct,                  "#E53E3E"),
            (_t2c3, "Requieren pedido",     f"{_t2_ped:,}", "cant. sugerida > 0",     "#DD6B20"),
            (_t2c4, "Valor en existencias", _t2_val_s,      "CLP — selección actual", "#38A169"),
        ]:
            _cx.markdown(
                f'<div style="background:white;border-radius:10px;padding:12px 16px;margin:4px 0 10px 0;'
                f'box-shadow:0 1px 3px rgba(0,0,0,0.07);border-top:3px solid {_cxc};">'
                f'<div style="font-size:0.60rem;color:#64748b;font-weight:600;text-transform:uppercase;'
                f'letter-spacing:0.05em;margin-bottom:4px">{_lx}</div>'
                f'<div style="font-size:1.25rem;font-weight:800;color:#0f172a">{_vx}</div>'
                f'<div style="font-size:0.62rem;color:#94a3b8;margin-top:2px">{_sx}</div>'
                f'</div>', unsafe_allow_html=True,
            )

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
                lambda v: f"${int(v):,}" if pd.notna(v) and v > 0 else "—"
            )
        if "valor_inventario" in tabla.columns:
            tabla["valor_inventario"] = tabla["valor_inventario"].apply(
                lambda v: f"${int(v):,}" if pd.notna(v) and v > 0 else "—"
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
                help="Meses estimados que duran las existencias actuales al ritmo de consumo promedio. Menos de 1 mes = critico; 1-3 meses = bajo; más de 3 meses = adecuado.",
            )
        if "Cant. sugerida" in tabla.columns:
            _ccfg["Cant. sugerida"] = st.column_config.NumberColumn("Cant. sugerida", format="%d u",
                           help="Cantidad recomendada a pedir en la proxima orden, calculada por el modelo de inventario.")
        if "Costo unit." in tabla.columns:
            _ccfg["Costo unit."] = st.column_config.TextColumn("Costo unit.",
                           help="Precio unitario del medicamento en CLP, según el Programa de compras.")
        if "Valor en exist." in tabla.columns:
            _ccfg["Valor en exist."] = st.column_config.TextColumn("Valor en exist.",
                           help="Valor económico total: existencias × costo unitario (CLP).")
        if "Días p/Vencer" in tabla.columns:
            _ccfg["Días p/Vencer"] = st.column_config.NumberColumn("Días p/Vencer", format="%d d",
                           help="Días que faltan para que venza el lote más próximo a caducar. Negativo = ya vencido.")

        st.caption(f"{_t2n:,} producto(s) — ordenados por urgencia")
        st.dataframe(_safe_df(tabla), use_container_width=True, hide_index=True,
                     height=520, column_config=_ccfg)

    # ══════════════════════════════════════════════════════════════════════════
    # SUB-TAB 2 — VENCIMIENTOS
    # ══════════════════════════════════════════════════════════════════════════
    with _t2_venc:
        st.markdown(_ayuda(
            "<b>Control de vencimientos por lote</b> — Muestra cada lote de medicamento con su fecha de caducidad real. "
            "Un mismo medicamento puede aparecer varias veces si tiene multiples lotes con fechas distintas. "
            "La logica recomendada es <b>FEFO</b> (First Expired, First Out): el lote que vence primero debe dispensarse primero para evitar perdidas. "
            "<b>Dias restantes</b>: dias entre hoy y la fecha de vencimiento del lote. Un valor negativo significa que el lote ya esta vencido. "
            "La tabla inferior lista solo los lotes que vencen en menos de 30 dias, con una accion sugerida para cada uno."
        ), unsafe_allow_html=True)
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
            # ── KPI strip ─────────────────────────────────────────────────────
            _nv_venc = int((_venc_df["dias_vencer"] < 0).sum())
            _nv_crit = int(((_venc_df["dias_vencer"] >= 0) & (_venc_df["dias_vencer"] < 30)).sum())
            _nv_adv  = int(((_venc_df["dias_vencer"] >= 30) & (_venc_df["dias_vencer"] < 90)).sum())
            _nv_ok   = int((_venc_df["dias_vencer"] >= 90).sum())
            _vkc1, _vkc2, _vkc3, _vkc4 = st.columns(4)
            for _vc, _vl_lbl, _vv, _vcolor, _vhelp in [
                (_vkc1, "Lotes vencidos",       f"{_nv_venc:,}", "#E53E3E",
                 "Lotes cuya fecha de vencimiento ya pasó. Deben darse de baja del inventario."),
                (_vkc2, "Vencen en <30 días",   f"{_nv_crit:,}", "#DD6B20",
                 "Lotes con menos de 30 días antes de caducar. Requieren acción inmediata."),
                (_vkc3, "Vencen en 30–90 días", f"{_nv_adv:,}",  "#D69E2E",
                 "Lotes con entre 1 y 3 meses de vida útil restante. Monitorear y planificar."),
                (_vkc4, "Vencen en >90 días",   f"{_nv_ok:,}",   "#38A169",
                 "Lotes con más de 3 meses hasta su vencimiento. Estado adecuado."),
            ]:
                _vc.markdown(
                    f'<div style="background:white;border-radius:10px;padding:12px 16px;margin:4px 0 10px 0;'
                    f'box-shadow:0 1px 3px rgba(0,0,0,0.07);border-top:3px solid {_vcolor};" '
                    f'title="{_vhelp}">'
                    f'<div style="font-size:0.60rem;color:#64748b;font-weight:600;text-transform:uppercase;'
                    f'letter-spacing:0.05em;margin-bottom:4px">{_vl_lbl}</div>'
                    f'<div style="font-size:1.25rem;font-weight:800;color:#0f172a">{_vv}</div>'
                    f'</div>', unsafe_allow_html=True,
                )

            # ── Filtro de urgencia ─────────────────────────────────────────────
            _vf_col1, _vf_col2 = st.columns([2, 3])
            _vf_vista = _vf_col1.radio(
                "Mostrar en el gráfico:",
                ["Todos con fecha", "Solo vencidos y críticos (<30 d)", "Solo próximos (30–90 d)"],
                horizontal=False, key="venc_vista",
            )
            _vf_busq = _vf_col2.text_input(
                "Buscar medicamento:", placeholder="Filtra por nombre...", key="venc_busq"
            )

            # Aplicar filtro de vista
            if _vf_vista == "Solo vencidos y críticos (<30 d)":
                _venc_vis = _venc_df[_venc_df["dias_vencer"] < 30].copy()
            elif _vf_vista == "Solo próximos (30–90 d)":
                _venc_vis = _venc_df[(_venc_df["dias_vencer"] >= 30) & (_venc_df["dias_vencer"] < 90)].copy()
            else:
                _venc_vis = _venc_df.copy()

            if _vf_busq.strip():
                _mask_b = _venc_vis[_venc_nom].astype(str).str.contains(_vf_busq.strip(), case=False, na=False)
                _venc_vis = _venc_vis[_mask_b]

            # ── Timeline ──────────────────────────────────────────────────────
            _venc_prod = (
                _venc_vis.groupby(_venc_nom)
                .agg(dias_min=("dias_vencer", "min"))
                .reset_index()
                .sort_values("dias_min")
                .head(20)
            )
            if len(_venc_prod) == 0:
                st.info("No hay medicamentos que coincidan con los filtros aplicados.")
            else:
                _venc_prod["color"] = _venc_prod["dias_min"].apply(
                    lambda d: "#E53E3E" if d < 0 else "#DD6B20" if d < 30
                    else "#D69E2E" if d < 90 else "#38A169"
                )
                _noms_v = [
                    n[:45] + "…" if len(str(n)) > 45 else str(n)
                    for n in _venc_prod[_venc_nom]
                ]
                _fig_tl = go.Figure(go.Bar(
                    x=_venc_prod["dias_min"].clip(lower=-365),
                    y=_noms_v,
                    orientation="h",
                    marker_color=_venc_prod["color"].tolist(),
                    text=[f"{int(d)} d" for d in _venc_prod["dias_min"]],
                    textposition="outside", cliponaxis=False,
                    hovertemplate="<b>%{y}</b><br>%{x} días hasta vencer<extra></extra>",
                ))
                _fig_tl.add_vline(x=0,  line_color="#E53E3E", line_width=2, line_dash="dash",
                                  annotation_text="Hoy", annotation_position="top left")
                _fig_tl.add_vline(x=30, line_color="#DD6B20", line_width=1, line_dash="dot",
                                  annotation_text="30 d", annotation_position="top right")
                _fig_tl.add_vline(x=90, line_color="#D69E2E", line_width=1, line_dash="dot",
                                  annotation_text="90 d", annotation_position="top right")
                _fig_tl.update_layout(
                    title=dict(text=f"Días hasta vencimiento — top {len(_venc_prod)} más urgentes",
                               font=dict(size=13, color="#0f172a")),
                    height=max(300, len(_venc_prod) * 28 + 80),
                    margin=dict(t=36, b=8, l=8, r=80),
                    xaxis=dict(title="Días restantes (negativo = ya vencido)",
                               zeroline=True, zerolinecolor="#E53E3E", zerolinewidth=2),
                    yaxis=dict(autorange="reversed"),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(_fig_tl, use_container_width=True)
                st.caption("Cada barra = un medicamento, posicionado según el lote que vence primero. Izquierda de la línea 'Hoy' = ya vencido. Entre 'Hoy' y '30 d' = acción urgente.")

            # ── Tabla detalle: lotes con acción requerida (<90 días) ──────────
            _crit_v = _venc_vis[_venc_vis["dias_vencer"] < 90].copy().sort_values("dias_vencer")
            if len(_crit_v) > 0:
                # Construir columnas base
                _cv_cols = [_venc_nom]
                if _venc_lote and _venc_lote in _crit_v.columns:
                    _cv_cols.append(_venc_lote)
                if _venc_stk and _venc_stk in _crit_v.columns:
                    _cv_cols.append(_venc_stk)
                if IL_VENC and IL_VENC in _crit_v.columns and IL_VENC not in _cv_cols:
                    _cv_cols.append(IL_VENC)
                _cv_cols.append("dias_vencer")
                _crit_show = _crit_v[[c for c in _cv_cols if c in _crit_v.columns]].copy()

                # Fecha legible dd/mm/yyyy
                if IL_VENC and IL_VENC in _crit_show.columns:
                    _crit_show[IL_VENC] = pd.to_datetime(
                        _crit_show[IL_VENC], errors="coerce"
                    ).dt.strftime("%d/%m/%Y").fillna("—")

                # Situación en texto natural (reemplaza número crudo)
                def _dias_legible(d):
                    d = int(d)
                    if d < 0:   return f"Vencido hace {abs(d):,} días"
                    if d == 0:  return "Vence hoy"
                    if d == 1:  return "Vence mañana"
                    return f"Vence en {d:,} días"

                _crit_show["Situación"]  = _crit_show["dias_vencer"].apply(_dias_legible)
                _crit_show["_estado"]    = _crit_show["dias_vencer"].apply(
                    lambda d: "vencido" if d < 0 else "critico" if d < 15
                    else "proximo" if d < 30 else "monitorear"
                )

                # Renombrar columnas
                _ren_v = {_venc_nom: "Medicamento", "dias_vencer": "_dias_raw"}
                if _venc_lote:  _ren_v[_venc_lote] = "Nro. de lote"
                if _venc_stk:   _ren_v[_venc_stk]  = "Unidades"
                if IL_VENC:     _ren_v[IL_VENC]     = "Fecha vencimiento"
                _crit_show = _crit_show.rename(
                    columns={k: v for k, v in _ren_v.items() if k}
                ).reset_index(drop=True)

                # Orden de columnas: Medicamento | Situación | Nro lote | Unidades | Fecha
                _col_ord = ["Medicamento", "Situación"]
                if "Nro. de lote"      in _crit_show.columns: _col_ord.append("Nro. de lote")
                if "Unidades"          in _crit_show.columns: _col_ord.append("Unidades")
                if "Fecha vencimiento" in _crit_show.columns: _col_ord.append("Fecha vencimiento")
                _col_ord += ["_estado"]
                _crit_show = _crit_show[[c for c in _col_ord if c in _crit_show.columns]]

                # ── 4 secciones por nivel de urgencia ─────────────────────────
                st.markdown(
                    '<div style="font-size:0.85rem;font-weight:700;color:#1a202c;margin:18px 0 4px 0">'
                    'Detalle por lote — ordenado por urgencia</div>',
                    unsafe_allow_html=True,
                )
                _secciones_v = [
                    ("vencido",    "Vencidos — retirar del inventario",
                     "#C53030", "#FFF5F5",
                     "Estos lotes ya superaron su fecha de vencimiento. "
                     "Deben retirarse del inventario y darse de baja de inmediato para evitar riesgos."),
                    ("critico",   "Críticos — vencen en menos de 15 días",
                     "#C05621", "#FFFAF0",
                     "Menos de 15 días de vida útil restante. "
                     "Dispensar estos lotes <b>antes que cualquier otro</b> (principio FEFO: primero en vencer, primero en salir)."),
                    ("proximo",   "Próximos — entre 15 y 30 días",
                     "#975A16", "#FEFCBF",
                     "Entre 15 y 30 días hasta el vencimiento. "
                     "Planificar devolución al proveedor si corresponde, o asegurar su consumo antes de que lleguen a estado crítico."),
                    ("monitorear","Monitorear — entre 30 y 90 días",
                     "#276749", "#F0FFF4",
                     "Entre 1 y 3 meses hasta el vencimiento. "
                     "No requieren acción urgente, pero deben estar bajo seguimiento para evitar que lleguen a estado crítico sin ser detectados."),
                ]
                for _est_k, _sec_tit, _sec_col, _sec_bg, _sec_desc in _secciones_v:
                    _df_sec = _crit_show[_crit_show["_estado"] == _est_k].drop(
                        columns=["_estado", "_dias_raw"], errors="ignore"
                    ).reset_index(drop=True)
                    if len(_df_sec) == 0:
                        continue
                    st.markdown(
                        f'<div style="background:{_sec_bg};border-left:4px solid {_sec_col};'
                        f'border-radius:6px;padding:10px 14px;margin:14px 0 6px 0">'
                        f'<div style="font-size:0.80rem;font-weight:700;color:{_sec_col};'
                        f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px">'
                        f'{_sec_tit} — {len(_df_sec)} lote{"s" if len(_df_sec) != 1 else ""}</div>'
                        f'<div style="font-size:0.78rem;color:#4A5568;line-height:1.5">'
                        f'{_sec_desc}</div></div>',
                        unsafe_allow_html=True,
                    )
                    _ccfg_v = {}
                    if "Medicamento"      in _df_sec.columns:
                        _ccfg_v["Medicamento"]      = st.column_config.TextColumn("Medicamento", help="Nombre del medicamento o insumo.")
                    if "Situación"        in _df_sec.columns:
                        _ccfg_v["Situación"]        = st.column_config.TextColumn("Situación", help="Tiempo transcurrido o restante hasta la fecha de vencimiento.")
                    if "Nro. de lote"     in _df_sec.columns:
                        _ccfg_v["Nro. de lote"]     = st.column_config.TextColumn("Nro. de lote", help="Identificador único del lote físico registrado en el inventario.")
                    if "Unidades"         in _df_sec.columns:
                        _ccfg_v["Unidades"]         = st.column_config.NumberColumn("Unidades en lote", format="%d u", help="Cantidad de unidades físicas disponibles en este lote específico.")
                    if "Fecha vencimiento" in _df_sec.columns:
                        _ccfg_v["Fecha vencimiento"] = st.column_config.TextColumn("Fecha vencimiento", help="Fecha en que expira la vida útil del lote según el fabricante.")
                    st.dataframe(
                        _safe_df(_df_sec), use_container_width=True, hide_index=True,
                        column_config=_ccfg_v,
                        height=min(420, max(80, len(_df_sec) * 35 + 40)),
                    )

    # ══════════════════════════════════════════════════════════════════════════
    # SUB-TAB 3 — DETALLE POR MEDICAMENTO
    # ══════════════════════════════════════════════════════════════════════════
    with _t2_det:
        st.markdown(_ayuda(
            "<b>Ficha completa de medicamento</b> — Selecciona cualquier producto para ver todos sus indicadores en detalle. "
            "El <b>termometro (gauge)</b> muestra visualmente si las existencias están en zona critica (rojo), de alerta (naranja) o adecuada (verde) respecto a las existencias minimas y maximas definidas. "
            "La <b>tabla de informacion</b> resume parametros operativos como existencias minimas, maximas y criticas. "
            "El <b>historial mensual</b> permite identificar estacionalidad o tendencias de consumo. "
            "El buscador filtra el listado en tiempo real; el dropdown muestra primero los medicamentos de mayor consumo."
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
            _d_stk   = float(_row_d.get("stock_total",    0) or 0)
            _d_alc   = float(pd.to_numeric(_row_d.get("ALCANCE",    None), errors="coerce") or 0)
            _d_smin  = float(pd.to_numeric(_row_d.get("STC_MIN",    None), errors="coerce") or 0)
            _d_smax  = float(pd.to_numeric(_row_d.get("STC_MAX",    None), errors="coerce") or 0)
            _d_scrit = float(pd.to_numeric(_row_d.get("STC_CRITICO",None), errors="coerce") or 0)
            _d_med   = float(_row_d.get("media_diaria",   0) or 0)
            _d_sug   = float(pd.to_numeric(_row_d.get("SUGERIDO",   0), errors="coerce") or 0)
            _d_costo = float(pd.to_numeric(_row_d.get("costo_unitario", 0), errors="coerce") or 0)
            _d_dcob  = float(_row_d.get("dias_cobertura", 0) or 0)
            _d_est   = str(_row_d.get("_estado_cob", _row_d.get("estado", "—")))

            # ── KPI strip ─────────────────────────────────────────────────────
            _dk1, _dk2, _dk3, _dk4 = st.columns(4)
            _dk1.metric("Existencias actuales", f"{math.floor(_d_stk):,} u",
                        help="Total de unidades fisicas disponibles en todas las bodegas para este medicamento.")
            _dk2.metric("Consumo prom. mensual", f"{_d_med*30:,.0f} u/mes" if _d_med > 0 else "—",
                        help="Promedio de unidades dispensadas por mes, calculado a partir del historial de movimientos.")
            if _d_alc > 0:
                _dk3.metric("Cobertura", f"{round(_d_alc, 1)} meses",
                            help="Meses que duran las existencias actuales al ritmo de consumo promedio. Menos de 1 mes = critico.")
            elif _d_dcob > 0:
                _dk3.metric("Días de cobertura", f"{_d_dcob:.0f} días",
                            help="Dias que duran las existencias actuales al ritmo de consumo promedio.")
            else:
                _dk3.metric("Cobertura", "—",
                            help="No hay datos suficientes para estimar la cobertura (sin historial de consumo).")
            _dk4.metric("Sugerido pedir", f"{math.ceil(_d_sug):,} u" if _d_sug > 0 else "No requerido",
                        help="Cantidad recomendada para la proxima orden de compra, segun el modelo de inventario y los parametros configurados.")

            st.divider()

            # ── Gauge (izq) + Tabla info / Lotes (der) ────────────────────────
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
                    paper_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(_fig_g, use_container_width=True)
                if _d_smax > 0 and _d_smin > 0:
                    st.caption(f"Zona roja: existencias ≤ {int(_d_scrit)} u (critico). Zona naranja: entre {int(_d_scrit)} y {int(_d_smin)} u (por debajo del minimo). Zona verde: sobre {int(_d_smin)} u (adecuado). La marca naranja indica las existencias minimas requeridas.")
                else:
                    st.caption("Zona roja: cobertura ≤ 1 mes. Zona naranja: 1-3 meses. Zona verde: >3 meses. La marca naranja indica el umbral de 3 meses recomendado.")

            with _tcol:
                if formato_hospital:
                    st.markdown("**Información del producto**")
                    _info_rows = [
                        {"Campo": "Código",       "Valor": str(_cod_d)},
                        {"Campo": "Existencias actuales", "Valor": f"{math.floor(_d_stk):,} u"},
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
                    _info_rows.append({"Campo": "Estado", "Valor": _d_est})
                    for _campo, _col_r in [
                        ("Cobertura (meses)",   "ALCANCE"),
                        ("Existencias mínimas", "STC_MIN"),
                        ("Existencias máximas", "STC_MAX"),
                        ("Existencias críticas","STC_CRITICO"),
                        ("Consumo promedio",    "CONS_PROM"),
                    ]:
                        if _col_r in _row_d.index and not pd.isna(_row_d.get(_col_r)):
                            _info_rows.append({"Campo": _campo, "Valor": f"{float(_row_d[_col_r]):,.1f}"})
                    if _d_costo > 0:
                        _info_rows.append({"Campo": "Precio unitario",    "Valor": f"${_d_costo:,.0f} CLP"})
                        _info_rows.append({"Campo": "Valor en existencias","Valor": f"${_d_stk * _d_costo:,.0f} CLP"})
                    st.dataframe(
                        _safe_df(pd.DataFrame(_info_rows)),
                        use_container_width=True, hide_index=True,
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
                        st.caption("Barras azules = unidades dispensadas cada mes. Linea roja punteada = promedio mensual historico. Meses por encima del promedio pueden indicar estacionalidad o picos de demanda que deben considerarse al planificar el siguiente pedido.")
                    else:
                        st.info("Sin fechas válidas para construir el historial.")
                else:
                    st.info("Sin movimientos registrados para este medicamento.")
            else:
                st.info("Sube el archivo de movimientos para ver el historial de consumo.")

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 3 — MOVIMIENTOS
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    _smv = _store_global()
    # Inicializar listas en el store si aún no existen
    if "movimientos" not in _smv: _smv["movimientos"] = []
    if "lotes_oc"    not in _smv: _smv["lotes_oc"]    = []

    # ── Helper: disparar webhook ───────────────────────────────────────────
    def _disparar_webhook(payload: dict):
        _wh = _store_global().get("webhook_url", "").strip()
        if not _wh:
            return False, "Sin URL configurada"
        try:
            r = _requests.post(_wh, json=payload, timeout=6)
            return r.status_code < 300, f"HTTP {r.status_code}"
        except Exception as _e:
            return False, str(_e)

    # ── DataFrames de trabajo ──────────────────────────────────────────────
    _MOV_COLS  = ["Fecha","Medicamento","Código","Tipo","Cantidad","Bodega","Observaciones","Responsable"]
    _LOT_COLS  = ["Fecha llegada","OC referencia","Medicamento","Código","Nro. lote",
                  "Cant. pedida","Cant. llegada","Cant. aprobada","Cant. rechazada",
                  "Motivo rechazo","Fecha vencimiento","Responsable"]
    _df_movs  = pd.DataFrame(_smv["movimientos"])  if _smv["movimientos"]  else pd.DataFrame(columns=_MOV_COLS)
    _df_lotes = pd.DataFrame(_smv["lotes_oc"])     if _smv["lotes_oc"]     else pd.DataFrame(columns=_LOT_COLS)

    # ── BOD_* disponibles (para selector de bodega) ────────────────────────
    _bods_disponibles = sorted([
        c.replace("BOD_", "").replace("_", " ").title()
        for c in resumen.columns if c.startswith("BOD_")
    ])
    if not _bods_disponibles:
        _bods_disponibles = ["Bodega Central"]

    # Lista de medicamentos ordenada por consumo
    if "media_diaria" in resumen.columns:
        _meds_lista = resumen.sort_values("media_diaria", ascending=False)[COL_NOMBRE].dropna().tolist()
    else:
        _meds_lista = resumen[COL_NOMBRE].dropna().sort_values().tolist()

    # ── Descargas siempre visibles (arriba del módulo) ────────────────────
    st.markdown(_ayuda(
        "Los archivos de abajo son <b>exactamente tus archivos originales</b> con lo nuevo añadido al final "
        "(movimientos) o con las existencias actualizadas (inventario). El formato y estructura es el mismo que cargaste.",
        color="#F0FFF4", borde="#38A169",
    ), unsafe_allow_html=True)
    _dlh1, _dlh2 = st.columns(2)

    # ── Inventario: archivo original con existencias actualizadas ─────────
    _inv_bytes, _inv_nom = _excel_inv_actualizado()
    _dlh1.download_button(
        label="Inventario actualizado (.xlsx)",
        data=_inv_bytes,
        file_name=_inv_nom,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        help="Tu archivo de inventario original con las existencias actualizadas según los movimientos registrados.",
        key="dl_inv_top",
    )

    # ── Movimientos: archivo original + filas nuevas al final ─────────────
    _n_nuevos_top = len(_smv["movimientos"])
    _mov_bytes, _mov_nom = _excel_mov_actualizado(_smv["movimientos"])
    _dlh2.download_button(
        label=f"Movimientos (.xlsx){f'  (+{_n_nuevos_top} filas nuevas)' if _n_nuevos_top else ''}",
        data=_mov_bytes,
        file_name=_mov_nom,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
        help="Tu archivo de movimientos original con las filas nuevas añadidas al final en el mismo formato. Las columnas '_SAVIA' marcan lo nuevo.",
        key="dl_mov_top",
    )

    st.markdown("---")

    _t3_reg, _t3_lot, _t3_his, _t3_gest = st.tabs([
        "Registrar movimiento",
        "Control de Lotes",
        "Historial",
        "Gestión de datos",
    ])

    # ══════════════════════════════════════════════════════════════════════
    # SUB-TAB: REGISTRAR MOVIMIENTO
    # ══════════════════════════════════════════════════════════════════════
    with _t3_reg:
        st.markdown(_ayuda(
            "<b>Registro de movimientos</b> — Ingresa aquí cada entrada, salida, pérdida o ajuste de inventario. "
            "Cada registro queda guardado en el historial de la sesión y actualiza las existencias de forma inmediata. "
            "Si las existencias caen bajo el punto de reorden, se dispara automáticamente una alerta al webhook de Make.com configurado en el panel lateral."
        ), unsafe_allow_html=True)

        # ── Controles FUERA del form (sin límite WebSocket) ──────────────
        _mv_busq = st.text_input(
            "Buscar medicamento:",
            placeholder="Escribe parte del nombre para filtrar...",
            key="mv_med_busq",
        )
        _mv_lista_f = (
            [m for m in _meds_lista if _mv_busq.strip().lower() in m.lower()][:50]
            if _mv_busq.strip() else _meds_lista[:50]
        ) or _meds_lista[:50]
        st.caption(f"Mostrando {len(_mv_lista_f)} de {len(_meds_lista):,} medicamentos.")

        # Modo de registro (fuera del form para controlar campos dinámicos)
        _mv_modo = st.radio(
            "Modo de registro:",
            ["Por unidad", "Por lote / pack"],
            horizontal=True,
            key="mv_modo_sel",
            help="'Por unidad': ingresas el total directo. 'Por lote/pack': ingresas la cantidad del pack y cuántos packs recibes (más unidades sueltas si aplica).",
        )

        with st.form("form_movimiento", clear_on_submit=True):
            _fc1, _fc2 = st.columns([3, 2])
            _mv_med = _fc1.selectbox(
                "Medicamento *",
                _mv_lista_f,
                help="Lista filtrada según el buscador de arriba.",
                key="mv_med_sel",
            )
            _mv_tipo = _fc2.selectbox(
                "Tipo de movimiento *",
                ["Entrada", "Salida", "Pérdida", "Ajuste de inventario"],
                help="Entrada: recepción de pedido. Salida: dispensación/consumo. Pérdida: merma, rotura, vencimiento. Ajuste: corrección de inventario.",
            )

            # ── Campos de cantidad según modo ──────────────────────────────
            if _mv_modo == "Por lote / pack":
                st.markdown(_ayuda(
                    "Ingresa el <b>tamaño del pack</b> (unidades que trae cada pack) y cuántos "
                    "<b>packs completos</b> recibes. Si sobran unidades sueltas (un pack incompleto), "
                    "agrégalas en el último campo. El total se calcula automáticamente.",
                    color="#EBF8FF", borde="#3182CE",
                ), unsafe_allow_html=True)
                _fpa, _fpb, _fpc = st.columns(3)
                _mv_pack_u = _fpa.number_input(
                    "Unidades por pack", min_value=1, value=10, step=1,
                    help="¿Cuántas unidades trae cada pack o lote? Ej: si el pack trae 100 ampollas, escribe 100.",
                )
                _mv_packs  = _fpb.number_input(
                    "Packs completos", min_value=0, value=0, step=1,
                    help="Número de packs completos que entran o salen.",
                )
                _mv_suelts = _fpc.number_input(
                    "Unidades sueltas adicionales", min_value=0, value=0, step=1,
                    help="Unidades de un pack incompleto. Ej: si recibiste 2 packs completos y 15 unidades sueltas, escribe 15 aquí.",
                )
                _mv_cant_calc = int(_mv_pack_u) * int(_mv_packs) + int(_mv_suelts)
                st.info(f"Total a registrar: **{_mv_cant_calc:,} unidades** ({int(_mv_packs)} × {int(_mv_pack_u)} + {int(_mv_suelts)} sueltas)")
            else:
                _mv_cant_calc = 0  # placeholder; se lee del input abajo
                _mv_cant_u = st.number_input(
                    "Cantidad *", min_value=1, value=1, step=1,
                    help="Número total de unidades del movimiento.",
                )
                _mv_cant_calc = int(_mv_cant_u)

            _fc4, _fc5 = st.columns(2)
            _mv_bod = _fc4.selectbox(
                "Bodega *", _bods_disponibles,
                help="Bodega desde/hacia donde se realiza el movimiento.",
            )
            _mv_fecha = _fc5.date_input(
                "Fecha *", value=date.today(),
                help="Fecha efectiva del movimiento (puede ser retroactiva).",
            )
            _mv_obs = st.text_area(
                "Observaciones (opcional)",
                placeholder="Ej: Recepción OC 2026-045, lote 30322578 — llegó con 2 unidades dañadas",
                height=68,
            )
            _mv_submit = st.form_submit_button("Registrar movimiento", type="primary", use_container_width=True)

        if _mv_submit:
            _mv_row_cod = resumen.loc[resumen[COL_NOMBRE] == _mv_med, COL_CODIGO]
            _mv_cod     = str(_mv_row_cod.iloc[0]) if len(_mv_row_cod) > 0 else "—"
            _mv_obs_txt = _mv_obs.strip() if _mv_obs else "—"
            if _mv_modo == "Por lote / pack" and _mv_packs > 0:
                _mv_obs_txt += f" | Pack: {int(_mv_packs)}×{int(_mv_pack_u)} u + {int(_mv_suelts)} sueltas"

            _smv["movimientos"].append({
                "Fecha":        _mv_fecha.strftime("%d/%m/%Y"),
                "Medicamento":  _mv_med,
                "Código":       _mv_cod,
                "Tipo":         _mv_tipo,
                "Cantidad":     _mv_cant_calc,
                "Bodega":       _mv_bod,
                "Observaciones": _mv_obs_txt,
                "Responsable":  _smv.get("responsable", "sin especificar"),
                "_ts":          pd.Timestamp.now().isoformat(),
            })

            # ── Añadir al DataFrame del archivo de movimientos cargado ─────
            if tiene_movimientos and _store_global()["mov"] is not None:
                _mov_new = {col: None for col in _store_global()["mov"].columns}
                if COL_MOV_CODIGO:   _mov_new[COL_MOV_CODIGO]   = _mv_cod
                if COL_MOV_FECHA:    _mov_new[COL_MOV_FECHA]     = pd.Timestamp(_mv_fecha)
                if COL_MOV_CANTIDAD: _mov_new[COL_MOV_CANTIDAD]  = float(_mv_cant_calc)
                # Columnas extra marcadas con _SAVIA para que sea fácil identificar lo nuevo
                _mov_new["Tipo_SAVIA"]         = _mv_tipo
                _mov_new["Bodega_SAVIA"]        = _mv_bod
                _mov_new["Observaciones_SAVIA"] = _mv_obs_txt
                _mov_new["Responsable_SAVIA"]   = _smv.get("responsable", "")
                _store_global()["mov"] = pd.concat(
                    [_store_global()["mov"], pd.DataFrame([_mov_new])],
                    ignore_index=True,
                )

            # ── Actualizar stock en el archivo de inventario ───────────────
            _delta_inv = _mv_cant_calc if _mv_tipo == "Entrada" else -_mv_cant_calc
            _inv_store = _store_global()["inv"]
            if COL_STOCK and COL_CODIGO and _inv_store is not None:
                _mask_inv = _inv_store[COL_CODIGO].astype(str) == str(_mv_cod)
                if _mask_inv.any():
                    _cur = pd.to_numeric(_inv_store.loc[_mask_inv, COL_STOCK], errors="coerce").fillna(0)
                    _inv_store.loc[_mask_inv, COL_STOCK] = (_cur + _delta_inv).clip(lower=0)
            # También actualizar la columna BOD_* de la bodega seleccionada si existe
            _bod_col_k = "BOD_" + _mv_bod.upper().replace(" ", "_")
            if _bod_col_k in (_inv_store.columns if _inv_store is not None else []):
                _mask_inv2 = _inv_store[COL_CODIGO].astype(str) == str(_mv_cod)
                if _mask_inv2.any():
                    _cur2 = pd.to_numeric(_inv_store.loc[_mask_inv2, _bod_col_k], errors="coerce").fillna(0)
                    _inv_store.loc[_mask_inv2, _bod_col_k] = (_cur2 + _delta_inv).clip(lower=0)

            _inv_delta_txt = f"+{_mv_cant_calc:,}" if _mv_tipo == "Entrada" else f"−{_mv_cant_calc:,}"
            st.success(
                f"Movimiento registrado: **{_mv_tipo}** de **{_mv_cant_calc:,} u** de {_mv_med}  \n"
                f"Stock en inventario actualizado ({_inv_delta_txt} u). Descarga los archivos actualizados arriba."
            )
            # Auto-guardar movimientos en Google Drive si está configurado
            if _gd_service() and _gd_folder_id():
                _gd_guardar_movimientos()

            # ── Verificar si el stock ajustado cae bajo el punto de reorden ──
            _mv_row = resumen[resumen[COL_NOMBRE] == _mv_med]
            if len(_mv_row) > 0:
                _base_stk = float(_mv_row.iloc[0].get("stock_total", 0) or 0)
                # Calcular delta acumulado en sesión para este medicamento
                _delta = sum(
                    m["Cantidad"] if m["Tipo"] == "Entrada" else -m["Cantidad"]
                    for m in _smv["movimientos"] if m["Medicamento"] == _mv_med
                )
                _adj_stk = max(0, _base_stk + _delta)
                _stc_min = float(_mv_row.iloc[0].get("STC_MIN", 0) or 0)
                if _adj_stk < _stc_min and _stc_min > 0:
                    st.warning(
                        f"Alerta: las existencias ajustadas de **{_mv_med}** ({int(_adj_stk):,} u) "
                        f"caen bajo el punto de reorden ({int(_stc_min):,} u). Se recomienda hacer un pedido."
                    )
                    _ok, _msg = _disparar_webhook({
                        "tipo_alerta": "existencias_bajo_reorden",
                        "medicamento": _mv_med,
                        "codigo":      _mv_cod,
                        "existencias_ajustadas": int(_adj_stk),
                        "punto_reorden": int(_stc_min),
                        "ultimo_movimiento": _mv_tipo,
                        "fecha": _mv_fecha.strftime("%d/%m/%Y"),
                    })
                    if _ok:
                        st.info("Alerta enviada al webhook de Make.com.")
                    elif _store_global().get("webhook_url", ""):
                        st.warning(f"No se pudo enviar la alerta al webhook: {_msg}")

        # ── Resumen de últimos 5 movimientos ──────────────────────────────
        if _smv["movimientos"]:
            st.markdown("**Últimos movimientos registrados en esta sesión**")
            _last5 = pd.DataFrame(_smv["movimientos"][-10:]).drop(columns=["_ts"], errors="ignore")
            _last5 = _last5[_MOV_COLS].iloc[::-1].reset_index(drop=True)
            st.dataframe(
                _safe_df(_last5), use_container_width=True, hide_index=True,
                height=min(380, len(_last5) * 35 + 40),
            )
        else:
            st.info("Aún no se han registrado movimientos en esta sesión.")

    # ══════════════════════════════════════════════════════════════════════
    # SUB-TAB: CONTROL DE LOTES
    # ══════════════════════════════════════════════════════════════════════
    with _t3_lot:
        st.markdown(_ayuda(
            "<b>Control de lotes</b> — Registra la recepción de cada lote, el resultado del control de calidad "
            "y las cantidades aprobadas y rechazadas. "
            "Si los rechazos superan el 30% del pedido, se envía automáticamente una alerta de calidad al webhook. "
            "El gráfico y las tablas se actualizan en tiempo real con cada registro."
        ), unsafe_allow_html=True)

        # ── Diagrama de flujo del ciclo del lote ─────────────────────────
        _NODES = [
            (0.5, 2.0, "Pedido OC",           "#3182CE", "white"),
            (2.0, 2.0, "Llegada",              "#3182CE", "white"),
            (3.5, 2.0, "Control de\nCalidad",  "#3182CE", "white"),
            (5.0, 2.8, "Aprobado",             "#38A169", "white"),
            (6.5, 2.8, "Bodega",               "#38A169", "white"),
            (8.0, 2.8, "Dispensación",         "#276749", "white"),
            (5.0, 1.2, "Rechazado",            "#C53030", "white"),
            (6.5, 1.2, "Reg. Pérdida",         "#C53030", "white"),
            (8.0, 1.2, "Desecho",              "#742A2A", "white"),
        ]
        _EDGES = [
            (0, 1), (1, 2), (2, 3), (3, 4), (4, 5),
            (2, 6), (6, 7), (7, 8),
        ]
        _fig_flow = go.Figure()
        for (_x1, _y1, _, _, _), (_x2, _y2, _, _, _) in [(_NODES[a], _NODES[b]) for a, b in _EDGES]:
            _fig_flow.add_trace(go.Scatter(
                x=[_x1 + 0.5, _x2 - 0.5], y=[_y1, _y2],
                mode="lines",
                line=dict(color="#A0AEC0", width=2),
                showlegend=False, hoverinfo="skip",
            ))
        for _nx, _ny, _nlbl, _nc, _ntc in _NODES:
            _fig_flow.add_shape(type="rect",
                x0=_nx-0.48, y0=_ny-0.32, x1=_nx+0.48, y1=_ny+0.32,
                fillcolor=_nc, line_color=_nc, line_width=0, layer="above",
            )
            _fig_flow.add_annotation(x=_nx, y=_ny, text=_nlbl.replace("\n", "<br>"),
                showarrow=False, font=dict(size=10, color=_ntc), align="center",
            )
        _fig_flow.update_layout(
            height=220, margin=dict(t=10, b=10, l=10, r=10),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-0.1, 8.6]),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[0.7, 3.3]),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        )
        st.plotly_chart(_fig_flow, use_container_width=True)
        st.caption("Flujo estándar del ciclo de vida de un lote: desde la orden de compra hasta la dispensación o el desecho si es rechazado en control de calidad.")

        # ── Formulario de registro de lote ────────────────────────────────
        st.markdown("#### Registrar recepción de lote")
        # Buscador FUERA del form para evitar límite WebSocket
        _lot_busq = st.text_input(
            "Buscar medicamento:",
            placeholder="Escribe parte del nombre para filtrar...",
            key="lot_med_busq",
        )
        _lot_lista_f = (
            [m for m in _meds_lista if _lot_busq.strip().lower() in m.lower()][:50]
            if _lot_busq.strip() else _meds_lista[:50]
        ) or _meds_lista[:50]
        st.caption(f"Mostrando {len(_lot_lista_f)} de {len(_meds_lista):,} medicamentos.")

        with st.form("form_lote", clear_on_submit=True):
            _lc1, _lc2 = st.columns([2, 2])
            _lot_med   = _lc1.selectbox("Medicamento *", _lot_lista_f,
                                        help="Lista filtrada según el buscador de arriba.")
            _lot_oc    = _lc2.text_input("OC de referencia", placeholder="Ej: OC-2026-045",
                                         help="Número de orden de compra asociada a este lote.")

            _lc3, _lc4 = st.columns([2, 2])
            _lot_num   = _lc3.text_input("Número de lote *", placeholder="Ej: 30322578",
                                          help="Código de lote del fabricante.")
            _lot_flleg = _lc4.date_input("Fecha de llegada *", value=date.today(),
                                          help="Fecha en que el lote llegó al establecimiento.")

            _lc5, _lc6, _lc7, _lc8 = st.columns(4)
            _lot_ped  = _lc5.number_input("Cant. pedida",   min_value=0, value=0, step=1,
                                           help="Unidades solicitadas en la OC.")
            _lot_lleg = _lc6.number_input("Cant. llegada",  min_value=0, value=0, step=1,
                                           help="Unidades físicamente recibidas.")
            _lot_apr  = _lc7.number_input("Cant. aprobada", min_value=0, value=0, step=1,
                                           help="Unidades que pasaron el control de calidad.")
            _lot_rech = _lc8.number_input("Cant. rechazada",min_value=0, value=0, step=1,
                                           help="Unidades que NO pasaron el control de calidad.")

            _lc9, _lc10 = st.columns([2, 2])
            _lot_motivo = _lc9.selectbox(
                "Motivo de rechazo (si aplica)",
                ["—", "Falla de calidad", "Daño físico", "Cadena de frío rota",
                 "Fecha de vencimiento incorrecta", "Otro"],
                help="Completar solo si hay unidades rechazadas.",
            )
            _lot_fvenc = _lc10.date_input("Fecha de vencimiento del lote",
                                           value=date.today() + timedelta(days=365),
                                           help="Fecha de vencimiento indicada en el envase del lote.")

            _lot_submit = st.form_submit_button("Registrar lote", type="primary", use_container_width=True)

        if _lot_submit:
            if not _lot_num.strip():
                st.error("El número de lote es obligatorio.")
            else:
                _lot_cod = ""
                _lot_row = resumen[resumen[COL_NOMBRE] == _lot_med]
                if len(_lot_row) > 0:
                    _lot_cod = str(_lot_row.iloc[0][COL_CODIGO])

                _smv["lotes_oc"].append({
                    "Fecha llegada":     _lot_flleg.strftime("%d/%m/%Y"),
                    "OC referencia":     _lot_oc.strip() or "—",
                    "Medicamento":       _lot_med,
                    "Código":            _lot_cod,
                    "Nro. lote":         _lot_num.strip(),
                    "Cant. pedida":      int(_lot_ped),
                    "Cant. llegada":     int(_lot_lleg),
                    "Cant. aprobada":    int(_lot_apr),
                    "Cant. rechazada":   int(_lot_rech),
                    "Motivo rechazo":    _lot_motivo if _lot_rech > 0 else "—",
                    "Fecha vencimiento": _lot_fvenc.strftime("%d/%m/%Y"),
                    "Responsable":       _smv.get("responsable", "sin especificar"),
                    "_ts":               pd.Timestamp.now().isoformat(),
                })

                # Si hay unidades aprobadas, registrar entrada en movimientos
                if _lot_apr > 0:
                    _lot_obs_txt = f"Entrada desde lote {_lot_num.strip()} (OC: {_lot_oc or '—'})"
                    _smv["movimientos"].append({
                        "Fecha":         _lot_flleg.strftime("%d/%m/%Y"),
                        "Medicamento":   _lot_med,
                        "Código":        _lot_cod,
                        "Tipo":          "Entrada",
                        "Cantidad":      int(_lot_apr),
                        "Bodega":        _bods_disponibles[0] if _bods_disponibles else "Bodega Central",
                        "Observaciones": _lot_obs_txt,
                        "Responsable":   _smv.get("responsable", "sin especificar"),
                        "_ts":           pd.Timestamp.now().isoformat(),
                    })
                    # Añadir también al archivo de movimientos cargado
                    if tiene_movimientos and _store_global()["mov"] is not None:
                        _lot_mov_new = {col: None for col in _store_global()["mov"].columns}
                        if COL_MOV_CODIGO:   _lot_mov_new[COL_MOV_CODIGO]   = _lot_cod
                        if COL_MOV_FECHA:    _lot_mov_new[COL_MOV_FECHA]     = pd.Timestamp(_lot_flleg)
                        if COL_MOV_CANTIDAD: _lot_mov_new[COL_MOV_CANTIDAD]  = float(_lot_apr)
                        _lot_mov_new["Tipo_SAVIA"]         = "Entrada"
                        _lot_mov_new["Bodega_SAVIA"]        = _bods_disponibles[0] if _bods_disponibles else "Bodega Central"
                        _lot_mov_new["Observaciones_SAVIA"] = _lot_obs_txt
                        _lot_mov_new["Responsable_SAVIA"]   = _smv.get("responsable", "")
                        _store_global()["mov"] = pd.concat(
                            [_store_global()["mov"], pd.DataFrame([_lot_mov_new])],
                            ignore_index=True,
                        )
                    # Actualizar stock en inventario
                    _inv_s2 = _store_global()["inv"]
                    if COL_STOCK and COL_CODIGO and _inv_s2 is not None:
                        _mask_l = _inv_s2[COL_CODIGO].astype(str) == str(_lot_cod)
                        if _mask_l.any():
                            _cur_l = pd.to_numeric(_inv_s2.loc[_mask_l, COL_STOCK], errors="coerce").fillna(0)
                            _inv_s2.loc[_mask_l, COL_STOCK] = (_cur_l + float(_lot_apr)).clip(lower=0)
                    st.success(
                        f"Lote {_lot_num} registrado. **{int(_lot_apr):,} u** aprobadas añadidas al inventario y al archivo de movimientos.  \n"
                        "Descarga los archivos actualizados en la parte superior de esta pestaña."
                    )

                # Alerta si rechazados > 30% del pedido
                if _lot_ped > 0 and _lot_rech / _lot_ped > 0.30:
                    st.error(
                        f"Los rechazos ({int(_lot_rech):,} u) superan el **30%** del pedido ({int(_lot_ped):,} u). "
                        "Se está disparando una alerta de calidad."
                    )
                    _ok, _msg = _disparar_webhook({
                        "tipo_alerta":    "calidad_lotes_rechazados",
                        "medicamento":    _lot_med,
                        "codigo":         _lot_cod,
                        "nro_lote":       _lot_num.strip(),
                        "oc_referencia":  _lot_oc or "—",
                        "cant_pedida":    int(_lot_ped),
                        "cant_rechazada": int(_lot_rech),
                        "pct_rechazo":    round(_lot_rech / _lot_ped * 100, 1),
                        "motivo":         _lot_motivo,
                        "fecha":          _lot_flleg.strftime("%d/%m/%Y"),
                    })
                    if _ok:
                        st.info("Alerta de calidad enviada al webhook de Make.com.")
                    elif _store_global().get("webhook_url", ""):
                        st.warning(f"No se pudo enviar la alerta: {_msg}")
                elif _lot_ped > 0:
                    st.success(f"Tasa de rechazo: {_lot_rech/_lot_ped*100:.1f}% — dentro del umbral aceptable.")

        # ── Gráficos de lotes (solo si hay datos) ─────────────────────────
        if _smv["lotes_oc"]:
            _df_lot_g = pd.DataFrame(_smv["lotes_oc"])
            _lc_g1, _lc_g2 = st.columns(2)

            # Torta: aprobados vs rechazados totales
            with _lc_g1:
                _tot_apr  = pd.to_numeric(_df_lot_g["Cant. aprobada"],  errors="coerce").fillna(0).sum()
                _tot_rech = pd.to_numeric(_df_lot_g["Cant. rechazada"], errors="coerce").fillna(0).sum()
                if _tot_apr + _tot_rech > 0:
                    _fig_pie_lot = go.Figure(go.Pie(
                        labels=["Aprobado", "Rechazado"],
                        values=[_tot_apr, _tot_rech],
                        marker_colors=["#38A169", "#E53E3E"],
                        hole=0.4,
                        textinfo="label+percent",
                    ))
                    _fig_pie_lot.update_layout(
                        title=dict(text="Lotes: aprobados vs rechazados", font=dict(size=12)),
                        height=280, margin=dict(t=36, b=8, l=8, r=8),
                        paper_bgcolor="rgba(0,0,0,0)",
                    )
                    st.plotly_chart(_fig_pie_lot, use_container_width=True)

            # Barras apiladas: rechazos por motivo
            with _lc_g2:
                _df_mot = _df_lot_g[_df_lot_g["Cant. rechazada"].apply(
                    lambda v: pd.to_numeric(v, errors="coerce") > 0
                )].copy()
                if len(_df_mot) > 0:
                    _df_mot["Cant. rechazada"] = pd.to_numeric(_df_mot["Cant. rechazada"], errors="coerce").fillna(0)
                    _df_mot_g = _df_mot.groupby("Motivo rechazo")["Cant. rechazada"].sum().reset_index()
                    _df_mot_g = _df_mot_g[_df_mot_g["Motivo rechazo"] != "—"]
                    if len(_df_mot_g) > 0:
                        _fig_bar_mot = go.Figure(go.Bar(
                            x=_df_mot_g["Motivo rechazo"],
                            y=_df_mot_g["Cant. rechazada"],
                            marker_color="#E53E3E",
                            text=_df_mot_g["Cant. rechazada"].astype(int).astype(str) + " u",
                            textposition="outside",
                        ))
                        _fig_bar_mot.update_layout(
                            title=dict(text="Unidades rechazadas por motivo", font=dict(size=12)),
                            height=280, margin=dict(t=36, b=8, l=8, r=60),
                            xaxis=dict(tickangle=-20),
                            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        )
                        st.plotly_chart(_fig_bar_mot, use_container_width=True)

            # Tabla de lotes registrados
            st.markdown("**Lotes registrados en esta sesión**")
            _df_lot_show = _df_lot_g.drop(columns=["_ts", "Código"], errors="ignore").reset_index(drop=True)
            st.dataframe(_safe_df(_df_lot_show), use_container_width=True, hide_index=True, height=320)
        else:
            st.info("Aún no se han registrado lotes en esta sesión. Usa el formulario de arriba para empezar.")

    # ══════════════════════════════════════════════════════════════════════
    # SUB-TAB: HISTORIAL
    # ══════════════════════════════════════════════════════════════════════
    with _t3_his:
        st.markdown(_ayuda(
            "<b>Historial de movimientos</b> — Visualiza y filtra todos los movimientos registrados en la sesión. "
            "Usa los filtros para enfocarte en un medicamento, bodega, tipo de movimiento o rango de fechas específico. "
            "Descarga la tabla filtrada como Excel para llevar un registro externo o cargarla en el sistema."
        ), unsafe_allow_html=True)

        if not _smv["movimientos"]:
            st.info("Aún no hay movimientos registrados. Ve a la sub-pestaña 'Registrar movimiento' para comenzar.")
        else:
            _df_his = pd.DataFrame(_smv["movimientos"]).drop(columns=["_ts"], errors="ignore")
            _df_his["Fecha"] = pd.to_datetime(_df_his["Fecha"], format="%d/%m/%Y", errors="coerce")

            # ── Filtros ───────────────────────────────────────────────────
            _hf1, _hf2, _hf3 = st.columns(3)
            _hf_med  = _hf1.multiselect("Medicamento:", sorted(_df_his["Medicamento"].unique()),
                                         key="his_med_filt", placeholder="Todos")
            _hf_tipo = _hf2.multiselect("Tipo:", ["Entrada","Salida","Pérdida","Ajuste de inventario"],
                                          key="his_tipo_filt", placeholder="Todos")
            _hf_bod  = _hf3.multiselect("Bodega:", sorted(_df_his["Bodega"].unique()),
                                          key="his_bod_filt", placeholder="Todas")

            _hd1, _hd2 = st.columns(2)
            _h_fecha_min = _df_his["Fecha"].min().date() if _df_his["Fecha"].notna().any() else date.today()
            _h_fecha_max = _df_his["Fecha"].max().date() if _df_his["Fecha"].notna().any() else date.today()
            _hf_desde = _hd1.date_input("Desde:", value=_h_fecha_min, key="his_desde")
            _hf_hasta = _hd2.date_input("Hasta:", value=_h_fecha_max, key="his_hasta")

            # Aplicar filtros
            _df_fil = _df_his.copy()
            if _hf_med:  _df_fil = _df_fil[_df_fil["Medicamento"].isin(_hf_med)]
            if _hf_tipo: _df_fil = _df_fil[_df_fil["Tipo"].isin(_hf_tipo)]
            if _hf_bod:  _df_fil = _df_fil[_df_fil["Bodega"].isin(_hf_bod)]
            _df_fil = _df_fil[
                (_df_fil["Fecha"] >= pd.Timestamp(_hf_desde)) &
                (_df_fil["Fecha"] <= pd.Timestamp(_hf_hasta))
            ]
            _df_fil["Fecha"] = _df_fil["Fecha"].dt.strftime("%d/%m/%Y")

            st.caption(f"Mostrando {len(_df_fil):,} de {len(_df_his):,} movimientos.")

            # ── Serie de tiempo semanal ───────────────────────────────────
            _df_ts = _df_his.copy()
            _df_ts["Semana"] = _df_ts["Fecha"].dt.to_period("W").dt.start_time
            _df_ent = _df_ts[_df_ts["Tipo"] == "Entrada"].groupby("Semana")["Cantidad"].sum().reset_index().rename(columns={"Cantidad": "Entradas"})
            _df_sal = _df_ts[_df_ts["Tipo"].isin(["Salida","Pérdida"])].groupby("Semana")["Cantidad"].sum().reset_index().rename(columns={"Cantidad": "Salidas"})
            _df_sem = _df_ent.merge(_df_sal, on="Semana", how="outer").fillna(0).sort_values("Semana")

            if len(_df_sem) > 0:
                _fig_ts = go.Figure()
                _fig_ts.add_trace(go.Bar(x=_df_sem["Semana"], y=_df_sem["Entradas"],
                                         name="Entradas", marker_color="#38A169"))
                _fig_ts.add_trace(go.Bar(x=_df_sem["Semana"], y=_df_sem["Salidas"],
                                         name="Salidas / Pérdidas", marker_color="#E53E3E"))
                _fig_ts.update_layout(
                    barmode="group",
                    title=dict(text="Entradas y salidas por semana", font=dict(size=13)),
                    height=280, margin=dict(t=36, b=8, l=8, r=8),
                    xaxis=dict(title="Semana"),
                    yaxis=dict(title="Unidades"),
                    legend=dict(orientation="h", y=1.1),
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                )
                st.plotly_chart(_fig_ts, use_container_width=True)

            # ── Tabla filtrada + exportar ────────────────────────────────
            st.dataframe(
                _safe_df(_df_fil[_MOV_COLS].reset_index(drop=True)),
                use_container_width=True, hide_index=True,
                height=min(500, max(120, len(_df_fil) * 35 + 40)),
            )

            # Botón exportar — usa el archivo cargado + nuevas filas (filtrado)
            _buf_xls = io.BytesIO()
            _mov_full = _store_global().get("mov")
            if _mov_full is not None and len(_mov_full) > 0:
                # Exportar el archivo completo actualizado (no solo el filtro de sesión)
                _mov_full.to_excel(_buf_xls, index=False, engine="openpyxl")
                _xls_label = f"Descargar archivo de movimientos completo (.xlsx) — {len(_mov_full):,} filas"
            else:
                _df_fil[_MOV_COLS].to_excel(_buf_xls, index=False, engine="openpyxl")
                _xls_label = "Descargar movimientos de la sesión (.xlsx)"
            st.download_button(
                label=_xls_label,
                data=_buf_xls.getvalue(),
                file_name=f"movimientos_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Archivo de movimientos original con todas las filas nuevas añadidas al final.",
            )

    # ══════════════════════════════════════════════════════════════════════
    # SUB-TAB: GESTIÓN DE DATOS
    # ══════════════════════════════════════════════════════════════════════
    with _t3_gest:
        st.markdown(_ayuda(
            "<b>Gestión de datos del inventario</b> — Edita o elimina registros directamente desde la tabla. "
            "Filtra por nombre para encontrar el medicamento, modifica las celdas que necesites y haz clic en "
            "<b>Aplicar cambios</b> para que se reflejen en toda la aplicación. "
            "También puedes descargar el inventario actualizado, el registro de movimientos o los lotes como archivos Excel."
        ), unsafe_allow_html=True)

        # ── Selector de columnas a mostrar ────────────────────────────────
        _prio_cols = [c for c in [
            COL_CODIGO, COL_NOMBRE,
            "stock_total", "STC_MIN", "STC_MAX", "STC_CRITICO",
            "ALCANCE", "SUGERIDO", "CONS_PROM", "costo_unitario",
        ] if c in datos_inventario.columns]
        _bod_cols_g = [c for c in datos_inventario.columns if c.startswith("BOD_")]
        _cols_editor = _prio_cols + _bod_cols_g

        _gest_busq = st.text_input(
            "Buscar medicamento:",
            placeholder="Filtra por nombre o código...",
            key="gest_busq_inv",
        )
        _inv_edit_df = datos_inventario[_cols_editor].copy() if _cols_editor else datos_inventario.copy()
        if _gest_busq.strip():
            _m1 = _inv_edit_df[COL_NOMBRE].astype(str).str.contains(_gest_busq.strip(), case=False, na=False)
            _m2 = _inv_edit_df[COL_CODIGO].astype(str).str.contains(_gest_busq.strip(), case=False, na=False)
            _inv_edit_df = _inv_edit_df[_m1 | _m2]
        _inv_edit_df = _inv_edit_df.head(100).reset_index(drop=True)

        st.caption(
            f"Mostrando {len(_inv_edit_df):,} filas. "
            "Para **eliminar** una fila: marca la casilla de la izquierda y bórrala con la tecla ←. "
            "Para **editar** una celda: haz doble clic sobre ella."
        )

        # ── Editor de datos ────────────────────────────────────────────────
        _ccfg_gest = {}
        if COL_NOMBRE in _inv_edit_df.columns:
            _ccfg_gest[COL_NOMBRE] = st.column_config.TextColumn("Nombre", width="large")
        if COL_CODIGO in _inv_edit_df.columns:
            _ccfg_gest[COL_CODIGO] = st.column_config.TextColumn("Código", width="small")
        if "stock_total" in _inv_edit_df.columns:
            _ccfg_gest["stock_total"] = st.column_config.NumberColumn("Existencias", format="%d u")
        for _bc in _bod_cols_g:
            _ccfg_gest[_bc] = st.column_config.NumberColumn(_bc.replace("BOD_","").replace("_"," "), format="%d u")

        _edited_inv = st.data_editor(
            _inv_edit_df,
            use_container_width=True,
            hide_index=False,
            num_rows="dynamic",
            column_config=_ccfg_gest,
            key="data_editor_inv",
        )

        _gc1, _gc2 = st.columns(2)
        if _gc1.button("Aplicar cambios al inventario", type="primary", use_container_width=True,
                        help="Guarda las ediciones y eliminaciones en el inventario activo. Los cambios se reflejan en toda la app."):
            _g_store = _store_global()
            _inv_base = _g_store["inv"].copy()
            # Obtener los índices originales del filtro aplicado
            if _gest_busq.strip():
                _m1b = _inv_base[COL_NOMBRE].astype(str).str.contains(_gest_busq.strip(), case=False, na=False)
                _m2b = _inv_base[COL_CODIGO].astype(str).str.contains(_gest_busq.strip(), case=False, na=False)
                _idx_orig = _inv_base[_m1b | _m2b].head(100).index
            else:
                _idx_orig = _inv_base.head(100).index

            # Calcular filas eliminadas (las que estaban antes y ya no están en _edited_inv)
            _orig_codes = set(_inv_base.loc[_idx_orig, COL_CODIGO].astype(str))
            _edit_codes = set(_edited_inv[COL_CODIGO].astype(str)) if COL_CODIGO in _edited_inv.columns else _orig_codes
            _deleted    = _orig_codes - _edit_codes
            if _deleted:
                _inv_base = _inv_base[~_inv_base[COL_CODIGO].astype(str).isin(_deleted)]

            # Aplicar ediciones a las filas que siguen existiendo
            for _, _erow in _edited_inv.iterrows():
                _ecod = str(_erow.get(COL_CODIGO, ""))
                _mask = _inv_base[COL_CODIGO].astype(str) == _ecod
                if _mask.any():
                    for _col in _edited_inv.columns:
                        if _col in _inv_base.columns:
                            _inv_base.loc[_mask, _col] = _erow[_col]

            _g_store["inv"] = _inv_base
            if _deleted:
                st.success(f"Cambios aplicados. Se eliminaron {len(_deleted)} fila(s): {', '.join(list(_deleted)[:5])}. Recargando...")
            else:
                st.success("Cambios aplicados correctamente. Recargando...")
            st.rerun()

        # ── Descargas (mismos archivos originales + cambios) ──────────────
        st.markdown("---")
        st.markdown("#### Exportar datos")
        st.caption("Los archivos descargados son exactamente los que cargaste, con tus cambios aplicados.")
        _dl1, _dl2, _dl3 = st.columns(3)

        # 1. Inventario original actualizado
        _inv_bytes_g, _inv_nom_g = _excel_inv_actualizado()
        _dl1.download_button(
            label="Inventario actualizado (.xlsx)",
            data=_inv_bytes_g,
            file_name=_inv_nom_g,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            help="Tu archivo de inventario original con existencias actualizadas por los movimientos.",
            key="dl_inv_gest",
        )

        # 2. Movimientos original + filas nuevas
        _n_nuevos_g = len(_smv["movimientos"])
        _mov_bytes_g, _mov_nom_g = _excel_mov_actualizado(_smv["movimientos"])
        _dl2.download_button(
            label=f"Movimientos (.xlsx){f' +{_n_nuevos_g}' if _n_nuevos_g else ''}",
            data=_mov_bytes_g,
            file_name=_mov_nom_g,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            help="Tu archivo de movimientos original con las filas nuevas al final.",
            key="dl_mov_gest",
        )

        # 3. Lotes registrados en sesión
        if _smv["lotes_oc"]:
            _buf_lot_dl = io.BytesIO()
            pd.DataFrame(_smv["lotes_oc"]).drop(columns=["_ts","Código"], errors="ignore").to_excel(
                _buf_lot_dl, index=False, engine="openpyxl"
            )
            _dl3.download_button(
                label=f"Lotes registrados (.xlsx)",
                data=_buf_lot_dl.getvalue(),
                file_name=f"lotes_SAVIA_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                help="Registro de control de calidad de todos los lotes ingresados en esta sesión.",
            )
        else:
            _dl3.info("Sin lotes aún")

# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO 4 — ABASTECIMIENTO Y SIMULACIÓN
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown(_ayuda(
        "<b>Modulo de Abastecimiento</b> — Calcula automaticamente las politicas optimas de reposicion para cada medicamento, basandose en el historial de consumo y los parametros configurados en el panel lateral. "
        "<b>Punto de reorden (s)</b>: nivel de existencias al que se debe emitir un nuevo pedido para no quedarse sin existencias durante el tiempo de entrega. "
        "<b>Cantidad a pedir (EOQ)</b>: cantidad economicamente optima que minimiza la suma de costos de ordenar y de mantener inventario. "
        "<b>Reserva de seguridad (SS)</b>: existencias extra para absorber variaciones inesperadas en la demanda o en el tiempo de entrega. "
        "<b>Nivel maximo (S)</b>: techo de inventario para evitar exceso de existencias. "
        "La tabla esta ordenada por urgencia: primero los productos que requieren accion inmediata."
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
                accion = "DAR DE BAJA — reponer"
            elif fila["stock_total"] < p["s"]:
                accion = "Pedir ahora"
            elif dias_cob is not None and not pd.isna(dias_cob) and dias_cob < (lead_time + periodo_revision) * 1.5:
                accion = "Pedir pronto"
            else:
                accion = "Existencias suficientes"
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
                "Acción recomendada":           accion,
                "_media":                       fila["media_diaria"],
            })

        if len(filas_politicas) == 0:
            st.warning("No hay medicamentos con datos de demanda suficientes.")
        else:
            df_politicas = pd.DataFrame(filas_politicas)
            orden_accion = {"DAR DE BAJA — reponer": 0, "Pedir ahora": 1, "Pedir pronto": 2, "Existencias suficientes": 3}
            df_politicas["_orden"] = df_politicas["Acción recomendada"].map(orden_accion).fillna(4)
            df_politicas = df_politicas.sort_values("_orden").drop(columns="_orden")

            NOMBRES = {"(R,s,Q)": "Cantidad fija", "(R,S)": "Reponer hasta el máximo", "(R,s,S)": "Variable hasta el máximo"}
            DESCRIPCION = {
                "(R,s,Q)": "Si las existencias están bajas, pide siempre la misma cantidad fija.",
                "(R,S)":   "Pide lo necesario para llegar al nivel máximo de existencias.",
                "(R,s,S)": "Si las existencias están bajas, pide lo necesario para llegar al máximo.",
            }

            # ── SECCIÓN 1: tabla de políticas ──────────────────────────────────
            with st.expander("Detalle de abastecimiento", expanded=True):
                t3a, t3b = st.columns([3, 2])
                busq_t3 = t3a.text_input("Buscar:", placeholder="Nombre del producto...", key="busq_t3")
                # Filtrar solo las acciones que aparecen en los datos actuales
                acciones_disp = []
                for accion in ["DAR DE BAJA — reponer", "Pedir ahora", "Pedir pronto", "Existencias suficientes"]:
                    if accion in df_politicas["Acción recomendada"].values:
                        acciones_disp.append(accion)
                filtro_accion = t3b.multiselect("Filtrar por acción:", acciones_disp, default=acciones_disp, key="filtro_accion_t3")
                df_vis = df_politicas[df_politicas["Acción recomendada"].isin(filtro_accion)].drop(columns="_media", errors="ignore")
                if busq_t3.strip():
                    df_vis = df_vis[df_vis["Medicamento"].str.contains(busq_t3.strip(), case=False, na=False)]
                st.caption(f"{len(df_vis)} producto(s)")
                st.dataframe(_safe_df(df_vis), use_container_width=True, hide_index=True, height=400)
                st.info("**Guía:** *Pedir cuando queden menos de X* = punto de reorden. *Cuánto pedir* = cantidad más económica (EOQ). *Reserva de seguridad* = colchón para imprevistos.")

            # ── SECCIÓN 2: frecuencia de revisión ──────────────────────────────

            # ── SECCIÓN 3: simulación de estrategias ───────────────────────────
            with st.expander("Comparación de estrategias de pedido"):
                st.caption("Simula el costo anual de tres estrategias distintas para un medicamento.")
                # Ordenar los medicamentos de mayor a menor consumo para que el default sea relevante
                meds_sim_ord = df_politicas.sort_values("_media", ascending=False)["Medicamento"].tolist()
                med_sim = st.selectbox("Medicamento a simular:", meds_sim_ord, key="sim_med")
                # Obtener los datos del medicamento seleccionado
                fila_simulacion = resumen[resumen[COL_NOMBRE] == med_sim].iloc[0]
                media_sim = max(fila_simulacion["media_diaria"], 0.001)
                # var_diaria ya contiene min(Media, var_batch) del proceso de estimación
                var_diaria_raw = fila_simulacion["var_diaria"]
                var_sim = max(float(var_diaria_raw) if not pd.isna(var_diaria_raw) else media_sim, 0.001)
                params_sim = calcular_politicas(media_sim, var_sim, costo_orden, costo_mantener, lead_time, periodo_revision, Z)
                R_opt_sim, _ = recomendar_periodo(media_sim, var_sim, costo_orden, costo_mantener, lead_time)

                # Nivel máximo (S_inicio) según la política — igual que el notebook de referencia:
                #   (R,s,Q) → inventario inicial = s+Q+U; pide Q fija cuando IP ≤ s
                #   (R,S)   → S_inicio = s;     repone hasta s en CADA revisión
                #   (R,s,S) → S_inicio = s+Q;   repone hasta s+Q solo cuando IP ≤ s
                s_sim  = params_sim["s"]
                Q_sim  = params_sim["Q"]
                S_rsq  = params_sim["S"]   # = s + Q + U  (inventario inicial (R,s,Q))
                S_rs   = s_sim             # (R,S)  ordena hasta el propio punto de reorden
                S_rss  = s_sim + Q_sim     # (R,s,S) ordena hasta s + Q

                # ── Resumen de parámetros de simulación ───────────────────────
                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    st.markdown("**Demanda**")
                    st.markdown(f"""
| Parámetro | Valor |
|---|---|
| Tasa de demanda (λ) | **{round(media_sim, 2)} u/día** |
| Varianza diaria (V) | **{round(var_sim, 2)} u²/día** |
| Horizonte simulado | **360 días** |
| Réplicas | **5** |
""")
                with pc2:
                    st.markdown("**Operación y costos**")
                    st.markdown(f"""
| Parámetro | Valor |
|---|---|
| Tiempo de entrega (LT) | **{int(lead_time)} días** |
| Período de revisión (R) | **{int(periodo_revision)} días** |
| Nivel de servicio (Z) | **{Z} (~97 %)** |
| Costo por orden (OC) | **${costo_orden:,} CLP** |
| Costo mantener (HC) | **${costo_mantener:,} CLP/u/día** |
""")
                with pc3:
                    st.markdown("**Parámetros de política**")
                    st.markdown(f"""
| Parámetro | Valor |
|---|---|
| Punto de reorden (s) | **{s_sim} u** |
| Lote fijo (Q) | **{Q_sim} u** |
| Undershoot prom. (U) | **{params_sim['U']} u** |
| Reserva de seguridad (SS) | **{params_sim['SS']} u** |
| S — inicio (R,s,Q) | **{S_rsq} u** |
| S — máximo (R,S) | **{S_rs} u** |
| S — máximo (R,s,S) | **{S_rss} u** |
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
                    with st.spinner("Ejecutando simulaciones..."):
                        r_rsq = simular_rsq(media_sim, var_sim, costo_orden, costo_mantener, lead_time, periodo_revision, s_sim, Q_sim, S_rsq)
                        r_rs  = simular_rs( media_sim, var_sim, costo_orden, costo_mantener, lead_time, periodo_revision, s_sim, Q_sim, S_rs)
                        r_rss = simular_rss(media_sim, var_sim, costo_orden, costo_mantener, lead_time, periodo_revision, s_sim, Q_sim, S_rss)
                    st.session_state["_sim_med"]   = med_sim
                    st.session_state["_sim_cache"] = {
                        "rsq": (_recortar_sim(r_rsq, _n_dias), r_rsq[0], r_rsq[1], r_rsq[4]),
                        "rs":  (_recortar_sim(r_rs,  _n_dias), r_rs[0],  r_rs[1],  r_rs[4]),
                        "rss": (_recortar_sim(r_rss, _n_dias), r_rss[0], r_rss[1], r_rss[4]),
                    }

                if "_sim_cache" not in st.session_state:
                    st.info("Selecciona un medicamento y haz clic en **Ejecutar simulación**.")
                else:
                    _sc = st.session_state["_sim_cache"]
                    costos_anuales  = {"(R,s,Q)": _sc["rsq"][2], "(R,S)": _sc["rs"][2], "(R,s,S)": _sc["rss"][2]}
                    quiebres_pol    = {"(R,s,Q)": _sc["rsq"][3], "(R,S)": _sc["rs"][3], "(R,s,S)": _sc["rss"][3]}
                    costos_diarios  = {"(R,s,Q)": _sc["rsq"][1], "(R,S)": _sc["rs"][1], "(R,s,S)": _sc["rss"][1]}

                    min_quiebres = min(quiebres_pol.values())
                    candidatas   = [p for p, q in quiebres_pol.items() if q == min_quiebres]
                    mejor        = min(candidatas, key=lambda p: costos_anuales[p])

                    filas_comparacion = []
                    for pol in ["(R,s,Q)", "(R,S)", "(R,s,S)"]:
                        q = quiebres_pol[pol]
                        disponibilidad = "Sin quiebres" if q == 0 else f"{q} u. sin atender"
                        if pol == mejor:
                            etiqueta = "RECOMENDADA"
                        elif q > min_quiebres:
                            etiqueta = "Quiebres de stock"
                        else:
                            dif = round((costos_anuales[pol] - costos_anuales[mejor]) / max(costos_anuales[mejor], 1) * 100, 1)
                            etiqueta = f"Más cara (+{dif} %)"
                        filas_comparacion.append({
                            "Estrategia":        NOMBRES[pol],
                            "Cómo funciona":     DESCRIPCION[pol],
                            "Quiebres de stock": disponibilidad,
                            "Costo diario ($)":  f"{costos_diarios[pol]:,}",
                            "Costo anual ($)":   f"{costos_anuales[pol]:,}",
                            "Evaluación":        etiqueta,
                        })
                    st.dataframe(_safe_df(pd.DataFrame(filas_comparacion)), use_container_width=True, hide_index=True)

                    razon_mejor = []
                    if min_quiebres == 0:
                        razon_mejor.append("sin quiebres de stock")
                    else:
                        razon_mejor.append(f"menor cantidad de quiebres ({min_quiebres} u.)")
                    razon_mejor.append("menor costo entre las de igual disponibilidad")
                    st.success(
                        f"Estrategia recomendada: **{NOMBRES[mejor]}** ({mejor}) — {DESCRIPCION[mejor]}  \n"
                        f"Criterio: {' y '.join(razon_mejor)}.  \n"
                        f"Costo anual estimado: **${costos_anuales[mejor]:,.0f} CLP** · "
                        f"Quiebres promedio: **{quiebres_pol[mejor]} u.**"
                    )

                    st.divider()
                    st.markdown("**Evolución de existencias en bodega — últimos 90 días de simulación:**")

                    refs_por_politica = {
                        "(R,s,Q)": [(s_sim, "#dc2626", "s = punto reorden"), (params_sim["SS"], "#d97706", "SS = seg.")],
                        "(R,S)":   [(S_rs,  "#16a34a", "S = s (nivel máx.)"), (params_sim["SS"], "#d97706", "SS = seg.")],
                        "(R,s,S)": [(s_sim, "#dc2626", "s = punto reorden"), (S_rss, "#16a34a", "S = s+Q (nivel máx.)"), (params_sim["SS"], "#d97706", "SS = seg.")],
                    }
                    titulos_estrategias = [
                        f"Política (R,s,Q) — {NOMBRES['(R,s,Q)']}",
                        f"Política (R,S) — {NOMBRES['(R,S)']}",
                        f"Política (R,s,S) — {NOMBRES['(R,s,S)']}",
                    ]
                    fig_sim = make_subplots(rows=3, cols=1, shared_xaxes=True,
                                            subplot_titles=titulos_estrategias, vertical_spacing=0.12)

                    for num_fila, (pol, color_linea) in enumerate([("(R,s,Q)", "#1a3a5c"), ("(R,S)", "#2563eb"), ("(R,s,S)", "#16a34a")], start=1):
                        x_datos, y_oh, y_ip = _sc[pol.lower().replace(",", "").replace("(", "").replace(")", "")][0]
                        fig_sim.add_trace(go.Scatter(x=x_datos, y=y_oh, mode="lines",
                            name=f"OH {NOMBRES[pol]}", legendgroup=pol,
                            line=dict(color=color_linea, width=1.8), showlegend=True), row=num_fila, col=1)
                        fig_sim.add_trace(go.Scatter(x=x_datos, y=y_ip, mode="lines",
                            name=f"IP {NOMBRES[pol]}", legendgroup=pol,
                            line=dict(color=color_linea, width=1, dash="dot"),
                            opacity=0.55, showlegend=True), row=num_fila, col=1)
                        for nivel, color_ref, etiqueta in refs_por_politica[pol]:
                            fig_sim.add_hline(y=nivel, line_dash="dash", line_color=color_ref, line_width=1,
                                annotation_text=etiqueta, annotation_position="right",
                                annotation_font_size=10, row=num_fila, col=1)

                    fig_sim.update_layout(height=780, margin=dict(t=50, b=30, l=80, r=130),
                                          paper_bgcolor="white", plot_bgcolor="#f8fafc")
                    fig_sim.update_xaxes(title_text="Día de simulación", row=3, col=1)
                    for num_fila in [1, 2, 3]:
                        fig_sim.update_yaxes(title_text="Unidades en bodega", tickformat=",",
                                             title_font_size=11, row=num_fila, col=1)
                    st.plotly_chart(fig_sim, use_container_width=True)
                    st.caption(
                        "**Línea sólida (OH)** = inventario físico en bodega  |  "
                        "**Línea punteada (IP)** = posición de inventario (OH + pedidos en tránsito) — "
                        "la orden se activa cuando **IP** cruza el umbral **s**, no cuando lo hace OH  \n"
                        "**Rojo** = punto de reorden (s)  |  "
                        "**Verde** = nivel máximo (S)  |  "
                        "**Naranja** = reserva de seguridad (SS)"
                    )

            # ── SECCIÓN 4: comparación actual vs óptimo ────────────────────────
            with st.expander("Que tan cerca estas del ideal"):
                # Ordenar medicamentos por consumo para que el default sea relevante
                meds_comp_ord = df_politicas.sort_values("_media", ascending=False)["Medicamento"].tolist()
                med_comp  = st.selectbox("Medicamento a evaluar:", meds_comp_ord, key="comp")
                fila_comparacion = resumen[resumen[COL_NOMBRE] == med_comp].iloc[0]
                consumo_c = max(fila_comparacion["media_diaria"], 0.001)
                var_c     = max(fila_comparacion["var_diaria"], 0.001)
                # Calcular los parámetros óptimos usando el MISMO período de revisión del sidebar
                # (para que la comparación sea justa: mismo R, solo difieren Q y s)
                revision_actual = int(periodo_revision)
                p_opt = calcular_politicas(consumo_c, var_c, costo_orden, costo_mantener, lead_time, revision_actual, Z)

                # El usuario ingresa los valores que usa actualmente en la práctica
                ci2, ci3 = st.columns(2)
                cantidad_actual = ci2.number_input("Unidades que se piden habitualmente", min_value=1, value=int(p_opt["Q"]), step=1, key="real_Q")
                reorden_actual  = ci3.number_input("Existencias con las que se decide pedir (u)", min_value=0, value=int(p_opt["s"]), step=1, key="real_s")

                # Función para calcular cuánto se aleja el valor actual del ideal (en %)
                def desviacion(actual, ideal):
                    if ideal == 0: return 0
                    return round((actual - ideal) / ideal * 100, 1)
                # Función para clasificar la desviación en texto
                def evaluacion(pct):
                    if abs(pct) <= 10:  return "Adecuado (" + str(pct) + "%)"
                    if abs(pct) <= 30:  return "Alejado (" + str(pct) + "%)"
                    return "Muy alejado (" + str(pct) + "%)"

                # Construir tabla de evaluación comparando actual vs recomendado
                df_eval = pd.DataFrame([
                    {"Parámetro": "Cantidad que se pide",
                     "Actual": str(cantidad_actual) + " u",
                     "Recomendado": str(p_opt["Q"]) + " u",
                     "Evaluación": evaluacion(desviacion(cantidad_actual, p_opt["Q"]))},
                    {"Parámetro": "Existencias mínimas para activar el pedido",
                     "Actual": str(reorden_actual) + " u",
                     "Recomendado": str(p_opt["s"]) + " u",
                     "Evaluación": evaluacion(desviacion(reorden_actual, p_opt["s"]))},
                ])
                st.dataframe(_safe_df(df_eval), use_container_width=True, hide_index=True)

                # Simular ambas políticas con el MISMO período de revisión (revision_actual)
                # Diferencia: parámetros Q y s del usuario vs los calculados como óptimos
                with st.spinner("Calculando impacto en costos..."):
                    _, costo_actual, _, _, _, _ = simular_rsq(consumo_c, var_c, costo_orden, costo_mantener, lead_time, revision_actual, reorden_actual, cantidad_actual, reorden_actual + cantidad_actual)
                    _, costo_optimo, _, _, _, _ = simular_rsq(consumo_c, var_c, costo_orden, costo_mantener, lead_time, revision_actual, p_opt["s"], p_opt["Q"], p_opt["S"])

                diferencia = costo_actual - costo_optimo
                cc1, cc2, cc3 = st.columns(3)
                cc1.metric("Costo actual (CLP/año)", f"${costo_actual:,.0f}")
                cc2.metric("Costo recomendado (CLP/año)", f"${costo_optimo:,.0f}")
                cc3.metric("Diferencia", f"${abs(diferencia):,.0f}", delta=f"{'más caro' if diferencia > 0 else 'más barato'}", delta_color="inverse")
                if diferencia > 0:
                    st.warning(f"Tu política actual cuesta **${diferencia:,.0f} CLP/año más** que la recomendada.")
                elif diferencia < 0:
                    st.success(f"Tu política actual es **${abs(diferencia):,.0f} CLP/año más barata** que la recomendada.")
                else:
                    st.info("El costo actual es equivalente al recomendado.")

