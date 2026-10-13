URL_API = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestres/"
)
 
# --- Estructura de la respuesta de la API ---
CLAVE_LISTA = "ListaEESSPrecio"
CLAVE_FECHA = "Fecha"
 
# --- Columnas que usamos (nombres tal y como vienen en la API) ---
COORDENADAS = ("Latitud", "Longitud (WGS84)")
 
PRECIOS = (
    "Precio Gasolina 95 E5",
    "Precio Gasolina 98 E5",
    "Precio Gasoleo A",
    "Precio Gasoleo Premium",
)
 
COLUMNAS_UTILES = (
    "IDEESS", "Rótulo", "Tipo Venta",
    "Dirección", "C.P.", "Municipio", "Provincia",
    "IDMunicipio", "IDProvincia", "IDCCAA",
    *COORDENADAS,
    *PRECIOS,
)
 
# --- Rangos plausibles ---
PRECIO_MIN, PRECIO_MAX = 0.5, 3.5          # €/litro
LATITUD_MIN, LATITUD_MAX = 27.0, 44.5      # incluye Canarias
LONGITUD_MIN, LONGITUD_MAX = -18.5, 4.5
 