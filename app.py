import streamlit as st
from st_supabase_connection import SupabaseConnection

# Configuración visual de la página
st.set_page_config(page_title="SGA - Inspección RESPEL", layout="wide")

st.title("🚛 Inspección de Vehículos - RESPEL")
st.caption("Sistema de Gestión Ambiental | SGA-HO-CD-FO-01")

# 1. Conexión a Supabase (usa las llaves de tu proyecto en .streamlit/secrets.toml)
st_supabase = st.connection("supabase", type=SupabaseConnection)

# 2. Cargar el catálogo de preguntas guardado en Supabase
@st.cache_data(ttl=600)
def cargar_catalogo():
    res = st_supabase.query("*", table="catalog_items_chequeo").execute()
    return res.data

items_catalogo = cargar_catalogo()

# 3. Formulario principal
with st.form("form_inspeccion", clear_on_submit=True):
    
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
    
    # Registro de residuos básicos
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
    
    # Agrupar preguntas por categoría visualmente
    respuestas_checklist = {}
    
    if items_catalogo:
        # Agrupamos por categoría
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
    st.subheader("4. Firmas y Cierre")
    firma_insp = st.text_input("Firma Persona que Inspecciona (Nombre/Cédula)")
    firma_cond = st.text_input("Firma Conductor (Nombre/Cédula)")
    
    btn_guardar = st.form_submit_button("💾 Guardar Inspección Digital", use_container_width=True)

# 4. Proceso de Guardado en Supabase
if btn_guardar:
    if not placa or not nombre_conductor:
        st.error("Por favor completa los datos obligatorios (Placa y Conductor).")
    else:
        # A. Guardar Cabecera
        datos_cabecera = {
            "proveedor": proveedor,
            "placa": placa,
            "tipo_vehiculo": tipo_vehiculo,
            "nombre_conductor": nombre_conductor,
            "cedula_conductor": cedula,
            "arl_conductor": arl,
            "eps_conductor": eps,
            "certificado_transporte": certificado,
            "observaciones_certificado": obs_certificado,
            "firma_inspector": firma_insp,
            "firma_conductor": firma_cond
        }
        res_inspeccion = st_supabase.table("inspecciones_vehiculos").insert(datos_cabecera).execute()
        inspeccion_id = res_inspeccion.data[0]['id']
        
        # B. Guardar Checklist en detalle_checklist
        registros_checklist = []
        for item_id, resp in respuestas_checklist.items():
            registros_checklist.append({
                "inspeccion_id": inspeccion_id,
                "categoria": resp["categoria"],
                "item_nombre": resp["item_nombre"],
                "cumple": resp["cumple"],
                "observaciones": resp["observaciones"]
            })
        
        st_supabase.table("detalle_checklist").insert(registros_checklist).execute()
        
        st.success(f"✅ ¡Inspección #{inspeccion_id} guardada exitosamente en Supabase!")
