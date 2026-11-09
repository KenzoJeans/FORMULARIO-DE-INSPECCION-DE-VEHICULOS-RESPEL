import streamlit as st
from supabase import create_client, Client

st.set_page_config(page_title="SGA - Inspección RESPEL", layout="wide")

st.title("🚛 Inspección de Vehículos - RESPEL")
st.caption("Sistema de Gestión Ambiental | SGA-HO-CD-FO-01")

# Conexión a Supabase
@st.cache_resource
def init_connection():
    url = st.secrets["connections"]["supabase"]["SUPABASE_URL"]
    key = st.secrets["connections"]["supabase"]["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

# Cargar catálogo con captura de error detallada
@st.cache_data(ttl=600)
def cargar_catalogo():
    try:
        response = supabase.table("catalog_items_chequeo").select("*").execute()
        return response.data, None
    except Exception as e:
        return [], str(e)

items_catalogo, error_msg = cargar_catalogo()

if error_msg:
    st.error(f"❌ Error técnico conectando a Supabase: {error_msg}")
    st.info("💡 Revisa que en el Table Editor de Supabase exista la tabla 'catalog_items_chequeo' y que tus secretos en Streamlit Cloud tengan la URL y la Key correctas.")
else:
    st.success(f"¡Conexión exitosa! Se cargaron {len(items_catalogo)} ítems del checklist.")
