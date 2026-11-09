import streamlit as st
from supabase import create_client, Client
from streamlit_drawable_canvas import st_canvas
import base64
from PIL import Image
import io

st.set_page_config(page_title="SGA - Inspección RESPEL", layout="wide")

st.title("🚛 Inspección de Vehículos - RESPEL")
st.caption("Sistema de Gestión Ambiental | SGA-HO-CD-FO-01")

# 1. Inicializar cliente de Supabase
@st.cache_resource
def init_connection():
    url = st.secrets["connections"]["supabase"]["SUPABASE_URL"].strip()
    key = st.secrets["connections"]["supabase"]["SUPABASE_KEY"].strip()
    return create_client(url, key)

supabase: Client = init_connection()

# 2. Cargar el catálogo de preguntas
@st.cache_data(ttl=600)
def cargar_catalogo():
    response = supabase.table("catalog_items_chequeo").select("*").execute()
    return response.data

try:
    items_catalogo = cargar_catalogo()
except Exception as e:
    st.error(f"❌ Error al consultar la tabla en Supabase: {e}")
    items_catalogo = []

if not items_catalogo:
    st.warning("⚠️ No se encontraron registros en el catálogo. Verifica la conexión.")
else:
    # 3. Formulario principal de inspección
    with st.form("form_inspeccion"):
        
        st.subheader("1. Datos Generales")
        col1, col2, col3 = st.columns(3)
        
        with col1:
            proveedor = st.text_input("Proveedor")
            placa = st.text_input("Placa Vehículo")
            tipo_vehiculo = st.text_input("Tipo de Vehículo")
        with col2:
            nombre_conductor = st.text_input("Nombre Conductor")
            cedula = st.text_input("Cédula Conductor")
            arl = st.text_input("ARL Conductor")
        with col3:
            eps = st.text_input("EPS Conductor")
            certificado = st.checkbox("¿Cuenta con Certificado RESPEL?", value=True)
            obs_certificado = st.text_input("Observaciones Certificado")

        st.markdown("---")
        st.subheader("2. Residuos Peligrosos a Transportar")
        
        col_r1, col_r2 = st.columns(2)
        with col_r1:
            peso_empaques = st.number_input("Empaques Contaminados (kg)", min_value=0.0, step=0.1)
            peso_raee = st.number_input("RAEE (kg)", min_value=0.0, step=0.1)
            peso_lodos = st.number_input("Lodos PTAR (kg)", min_value=0.0, step=0.1)
        with col_r2:
            peso_aceite = st.number_input("Aceite Usado (kg)", min_value=0.0, step=0.1)
            peso_baterias = st.number_input("Baterías y UPS (kg)", min_value=0.0, step=0.1)

        st.markdown("---")
        st.subheader("3. Lista de Chequeo (Verificación)")
        
        respuestas_checklist = {}
        categorias = list(set([item['categoria'] for item in items_catalogo]))
        
        for cat in categorias:
            st.write(f"**{cat}**")
            items_cat = [i for i in items_catalogo if i['categoria'] == cat]
            items_cat.sort(key=lambda x: x['orden'])
            
            for item in items_cat:
                c1, c2, c3 = st.columns([3, 1, 2])
                with c1:
                    st.write(item['item_nombre'])
                with c2:
                    cumple = st.radio("Cumple", ["Sí", "No"], key=f"rad_{item['id']}", horizontal=True, label_visibility="collapsed")
                with c3:
                    obs = st.text_input("Obs", key=f"obs_{item['id']}", label_visibility="collapsed", placeholder="Observación opcional")
                
                respuestas_checklist[item['id']] = {
                    "categoria": item['categoria'],
                    "item_nombre": item['item_nombre'],
                    "cumple": True if cumple == "Sí" else False,
                    "observaciones": obs
                }

        st.markdown("---")
        st.subheader("4. Firmas Digitales")
        
        col_f1, col_f2 = st.columns(2)
        
        with col_f1:
            st.text("Firma Persona que Inspecciona")
            nombre_inspector = st.text_input("Nombre y Cédula del Inspector")
            # Canvas para la firma del inspector
            canvas_inspector = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#FFFFFF",
                background_color="#1E1E1E",
                height=150,
                width=350,
                drawing_mode="freedraw",
                key="canvas_inspector",
            )
            
        with col_f2:
            st.text("Firma Conductor")
            # Canvas para la firma del conductor
            canvas_conductor = st_canvas(
                fill_color="rgba(255, 165, 0, 0.3)",
                stroke_width=2,
                stroke_color="#FFFFFF",
                background_color="#1E1E1E",
                height=150,
                width=350,
                drawing_mode="freedraw",
                key="canvas_conductor",
            )
        
        btn_guardar = st.form_submit_button("💾 Guardar Inspección Digital", use_container_width=True)

    # 4. Proceso de Guardado en Supabase
    if btn_guardar:
        if not placa or not nombre_conductor or not nombre_inspector:
            st.error("Por favor completa los datos obligatorios (Placa, Conductor y Nombre del Inspector).")
        else:
            # Procesar firma del inspector a base64 si existe trazo
            firma_inspector_b64 = ""
            if canvas_inspector.image_data is not None:
                img_insp = Image.fromarray(canvas_inspector.image_data.astype('uint8'), 'RGBA')
                buffered_insp = io.BytesIO()
                img_insp.save(buffered_insp, format="PNG")
                firma_inspector_b64 = base64.b64encode(buffered_insp.getvalue()).decode()

            # Procesar firma del conductor a base64 si existe trazo
            firma_conductor_b64 = ""
            if canvas_conductor.image_data is not None:
                img_cond = Image.fromarray(canvas_conductor.image_data.astype('uint8'), 'RGBA')
                buffered_cond = io.BytesIO()
                img_cond.save(buffered_cond, format="PNG")
                firma_conductor_b64 = base64.b64encode(buffered_cond.getvalue()).decode()

            # A. Guardar Cabecera
            datos_cabecera = {
                "proveedor": proveedor,
                "placa": placa.upper(),
                "tipo_vehiculo": tipo_vehiculo,
                "nombre_conductor": nombre_conductor,
                "cedula_conductor": cedula,
                "arl_conductor": arl,
                "eps_conductor": eps,
                "certificado_transporte": certificado,
                "observaciones_certificado": obs_certificado,
                "firma_inspector": f"{nombre_inspector} | B64_IMG", # Guardamos referencia o la imagen completa
                "firma_conductor": firma_conductor_b64
            }
            res_inspeccion = supabase.table("inspecciones_vehiculos").insert(datos_cabecera).execute()
            inspeccion_id = res_inspeccion.data[0]['id']
            
            # B. Guardar Checklist
            registros_checklist = []
            for item_id, resp in respuestas_checklist.items():
                registros_checklist.append({
                    "inspeccion_id": inspeccion_id,
                    "categoria": resp["categoria"],
                    "item_nombre": resp["item_nombre"],
                    "cumple": resp["cumple"],
                    "observaciones": resp["observaciones"]
                })
            
            supabase.table("detalle_checklist").insert(registros_checklist).execute()
            
            st.success(f"✅ ¡Inspección #{inspeccion_id} con firmas digitales guardada exitosamente en Supabase!")
