"""
Inspección de vehículos - RESPEL (SGA-HO-CO-FO-01)

Versión 2. Requiere haber ejecutado antes migracion_inspeccion_v2.sql
en Supabase. Guarda todo con la función registrar_inspeccion(), en una
sola transacción.

Secrets necesarios (.streamlit/secrets.toml o Secrets de Streamlit Cloud):
    [connections.supabase]
    SUPABASE_URL = "https://xxxx.supabase.co"
    SUPABASE_KEY = "clave ANON (public), nunca la service_role"
"""

import base64
import io
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
from PIL import Image
from streamlit_drawable_canvas import st_canvas
from supabase import Client, create_client

FORMATO_CODIGO = "SGA-HO-CO-FO-01"
FORMATO_VERSION = "1"
ZONA = ZoneInfo("America/Bogota")

st.set_page_config(page_title="SGA - Inspección RESPEL", layout="wide")
st.title("🚛 Inspección de Vehículos - RESPEL")
st.caption(f"Sistema de Gestión Ambiental | {FORMATO_CODIGO} · versión {FORMATO_VERSION}")


# ---------------------------------------------------------------------
# Conexión y catálogos
# ---------------------------------------------------------------------
@st.cache_resource
def init_connection() -> Client:
    cfg = st.secrets["connections"]["supabase"]
    return create_client(cfg["SUPABASE_URL"].strip(), cfg["SUPABASE_KEY"].strip())


supabase = init_connection()


@st.cache_data(ttl=600)
def cargar_items():
    r = supabase.table("catalog_items_chequeo").select("*").eq("activo", True).execute()
    return r.data


@st.cache_data(ttl=600)
def cargar_residuos():
    r = (
        supabase.table("catalog_tipos_residuo")
        .select("*")
        .eq("activo", True)
        .order("orden")
        .execute()
    )
    return r.data


# ---------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------
def hay_firma(canvas) -> bool:
    """True solo si el usuario realmente trazó algo en el lienzo."""
    return canvas.json_data is not None and len(canvas.json_data.get("objects", [])) > 0


def firma_a_base64(canvas) -> str:
    img = Image.fromarray(canvas.image_data.astype("uint8"), "RGBA").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def normalizar_placa(placa: str) -> str:
    return re.sub(r"[\s\-]", "", placa).upper()


# ---------------------------------------------------------------------
# Estado de la sesión
# ---------------------------------------------------------------------
# form_n cambia cada vez que se inicia una inspección nueva, para que
# todos los campos (y las firmas) arranquen limpios.
if "form_n" not in st.session_state:
    st.session_state.form_n = 0
if "resultado_guardado" not in st.session_state:
    st.session_state.resultado_guardado = None

n = st.session_state.form_n


def k(nombre: str) -> str:
    return f"{nombre}_{n}"


# ---------------------------------------------------------------------
# Pantalla de confirmación (evita guardar dos veces la misma inspección)
# ---------------------------------------------------------------------
if st.session_state.resultado_guardado:
    r = st.session_state.resultado_guardado
    if r["resultado"] == "APTO":
        st.success(f"✅ Inspección #{r['id']} guardada. Resultado: **APTO**.")
    else:
        st.error(f"🚫 Inspección #{r['id']} guardada. Resultado: **NO APTO**.")
        for motivo in r["motivos"]:
            st.write(f"- {motivo}")
        st.warning("El vehículo no debe cargar residuos hasta corregir lo anterior.")
    if st.button("➕ Registrar otra inspección", type="primary"):
        st.session_state.form_n += 1
        st.session_state.resultado_guardado = None
        st.rerun()
    st.stop()


# ---------------------------------------------------------------------
# Carga del catálogo
# ---------------------------------------------------------------------
try:
    items = cargar_items()
    residuos = cargar_residuos()
except Exception as e:
    st.error(f"❌ Error al consultar los catálogos en Supabase: {e}")
    st.stop()

if not items or not residuos:
    st.warning("⚠️ El catálogo de ítems o de residuos está vacío. Verifica la conexión y la migración SQL.")
    st.stop()

# Orden estable: las categorías salen en el orden en que se crearon sus
# ítems, y dentro de cada categoría se ordena por la columna "orden".
categorias = list(dict.fromkeys(i["categoria"] for i in sorted(items, key=lambda i: i["id"])))

# ---------------------------------------------------------------------
# Formulario
# ---------------------------------------------------------------------
with st.form(f"form_inspeccion_{n}"):

    st.subheader("1. Datos generales")
    fecha = st.date_input("Fecha de la inspección", value=datetime.now(ZONA).date(), key=k("fecha"))

    c1, c2, c3 = st.columns(3)
    with c1:
        proveedor = st.text_input("Proveedor *", key=k("proveedor"))
        placa = st.text_input("Placa del vehículo *", key=k("placa"))
        tipo_vehiculo = st.text_input("Tipo de vehículo *", key=k("tipo_vehiculo"))
    with c2:
        nombre_conductor = st.text_input("Nombre del conductor *", key=k("nombre_conductor"))
        cedula_conductor = st.text_input("Cédula del conductor *", key=k("cedula_conductor"))
        arl = st.text_input("ARL del conductor", key=k("arl"))
    with c3:
        eps = st.text_input("EPS del conductor", key=k("eps"))
        certificado = st.radio(
            "¿El conductor cuenta con el certificado de aptitud para transportar residuos peligrosos? *",
            ["Sí", "No"],
            index=None,
            horizontal=True,
            key=k("certificado"),
        )
        obs_certificado = st.text_input("Observaciones del certificado", key=k("obs_certificado"))

    st.markdown("---")
    st.subheader("2. Residuos peligrosos a transportar")
    st.caption("Escribe el peso (kg) de cada residuo que se transporta. Deja en 0 los que no aplican.")

    pesos = {}
    cols_res = st.columns(2)
    for idx, t in enumerate(residuos):
        with cols_res[idx % 2]:
            pesos[t["id"]] = st.number_input(
                f"{t['nombre']} (kg)",
                min_value=0.0,
                step=0.1,
                key=k(f"peso_{t['id']}"),
                help=f"Corriente: {t['corriente']}" if t.get("corriente") else None,
            )

    st.markdown("---")
    st.subheader("3. Lista de chequeo")
    st.caption("⚠️ = ítem crítico: hay que responderlo. Si marcas «No», escribe la observación.")

    respuestas = {}
    for cat in categorias:
        st.write(f"**{cat}**")
        items_cat = sorted(
            (i for i in items if i["categoria"] == cat),
            key=lambda i: (i.get("orden") or 0, i["id"]),
        )
        for item in items_cat:
            critico = bool(item.get("critico"))
            col_a, col_b, col_c = st.columns([3, 1, 2])
            with col_a:
                st.write(("⚠️ " if critico else "") + item["item_nombre"])
            with col_b:
                cumple = st.radio(
                    "Cumple",
                    ["Sí", "No"],
                    index=None if critico else 0,
                    key=k(f"rad_{item['id']}"),
                    horizontal=True,
                    label_visibility="collapsed",
                )
            with col_c:
                obs = st.text_input(
                    "Obs",
                    key=k(f"obs_{item['id']}"),
                    label_visibility="collapsed",
                    placeholder="Observación",
                )
            respuestas[item["id"]] = {
                "item_id": item["id"],
                "categoria": item["categoria"],
                "item_nombre": item["item_nombre"],
                "critico": critico,
                "cumple_raw": cumple,
                "observaciones": obs.strip(),
            }

    st.markdown("---")
    st.subheader("4. Firmas")
    f1, f2 = st.columns(2)
    with f1:
        st.markdown("##### Persona que inspecciona")
        nombre_inspector = st.text_input("Nombre completo del inspector *", key=k("insp_nombre"))
        doc_inspector = st.text_input("Documento del inspector *", key=k("insp_doc"))
        st.caption("Firma aquí:")
        canvas_inspector = st_canvas(
            fill_color="rgba(255, 255, 255, 0)",
            stroke_width=2,
            stroke_color="#000000",
            background_color="#FFFFFF",
            height=150,
            width=350,
            drawing_mode="freedraw",
            return_image_data=True,
            key=k("canvas_inspector"),
        )
    with f2:
        st.markdown("##### Conductor del vehículo")
        st.caption("El conductor firma con los datos de la sección 1.")
        st.caption("Firma aquí:")
        canvas_conductor = st_canvas(
            fill_color="rgba(255, 255, 255, 0)",
            stroke_width=2,
            stroke_color="#000000",
            background_color="#FFFFFF",
            height=150,
            width=350,
            drawing_mode="freedraw",
            return_image_data=True,
            key=k("canvas_conductor"),
        )

    enviar = st.form_submit_button("💾 Guardar inspección", use_container_width=True, type="primary")


# ---------------------------------------------------------------------
# Validación y guardado
# ---------------------------------------------------------------------
if enviar:
    errores = []

    obligatorios = {
        "Proveedor": proveedor,
        "Placa": placa,
        "Tipo de vehículo": tipo_vehiculo,
        "Nombre del conductor": nombre_conductor,
        "Cédula del conductor": cedula_conductor,
        "Nombre del inspector": nombre_inspector,
        "Documento del inspector": doc_inspector,
    }
    faltan = [nombre for nombre, valor in obligatorios.items() if not valor.strip()]
    if faltan:
        errores.append("Faltan campos obligatorios: " + ", ".join(faltan) + ".")

    if certificado is None:
        errores.append("Responde si el conductor cuenta con el certificado de aptitud.")

    if not any(p > 0 for p in pesos.values()):
        errores.append("Registra el peso de al menos un tipo de residuo.")

    sin_responder = [r["item_nombre"] for r in respuestas.values() if r["cumple_raw"] is None]
    if sin_responder:
        errores.append("Faltan ítems críticos por responder: " + "; ".join(sin_responder) + ".")

    sin_obs = [
        r["item_nombre"]
        for r in respuestas.values()
        if r["cumple_raw"] == "No" and not r["observaciones"]
    ]
    if sin_obs:
        errores.append("Escribe la observación de los ítems marcados «No»: " + "; ".join(sin_obs) + ".")

    if not hay_firma(canvas_inspector):
        errores.append("Falta la firma del inspector.")
    if not hay_firma(canvas_conductor):
        errores.append("Falta la firma del conductor.")

    if errores:
        for e in errores:
            st.error(e)
        st.stop()

    checklist = [
        {
            "item_id": r["item_id"],
            "categoria": r["categoria"],
            "item_nombre": r["item_nombre"],
            "cumple": r["cumple_raw"] == "Sí",
            "observaciones": r["observaciones"],
        }
        for r in respuestas.values()
    ]
    residuos_payload = [
        {
            "tipo_residuo_id": t["id"],
            "nombre": t["nombre"],
            "corriente": t.get("corriente"),
            "peso_kg": round(float(pesos[t["id"]]), 2),
        }
        for t in residuos
        if pesos[t["id"]] > 0
    ]

    payload = {
        "fecha": fecha.isoformat(),
        "version_formato": FORMATO_VERSION,
        "proveedor": proveedor.strip().upper(),
        "placa": normalizar_placa(placa),
        "tipo_vehiculo": tipo_vehiculo.strip().upper(),
        "nombre_conductor": nombre_conductor.strip().upper(),
        "cedula_conductor": cedula_conductor.strip(),
        "arl_conductor": arl.strip().upper(),
        "eps_conductor": eps.strip().upper(),
        "certificado_transporte": certificado == "Sí",
        "observaciones_certificado": obs_certificado.strip(),
        "inspector_nombre": nombre_inspector.strip().upper(),
        "inspector_documento": doc_inspector.strip(),
        "firma_inspector": firma_a_base64(canvas_inspector),
        "firma_conductor": firma_a_base64(canvas_conductor),
        "checklist": checklist,
        "residuos": residuos_payload,
    }

    # Motivos que se mostrarán si el resultado es NO APTO
    motivos = []
    if certificado == "No":
        motivos.append("El conductor no cuenta con el certificado de aptitud.")
    for r in respuestas.values():
        if r["critico"] and r["cumple_raw"] == "No":
            motivos.append(f"Ítem crítico que no cumple: {r['item_nombre']} ({r['observaciones']})")

    try:
        res = supabase.rpc("registrar_inspeccion", {"payload": payload}).execute()
    except Exception as e:
        st.error("❌ No se pudo guardar la inspección. No se registró nada; intenta de nuevo.")
        with st.expander("Detalle técnico"):
            st.code(str(e))
        st.stop()

    datos = res.data
    st.session_state.resultado_guardado = {
        "id": datos["id"],
        "resultado": datos["resultado"],
        "motivos": motivos,
    }
    st.rerun()
