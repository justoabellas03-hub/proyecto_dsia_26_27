URL_API = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestres/"
)
 

 
# --- Columnas que usamos (nombres tal y como vienen en la API) ---
COORDENADAS = ("Latitud", "Longitud (WGS84)")
 
PRECIOS = (
    "Precio Gasolina 95 E5",
    "Precio Gasolina 98 E5",
    "Precio Gasoleo A",
    "Precio Gasoleo Premium",
)
 

 
# --- Rangos plausibles ---
PRECIO_MIN, PRECIO_MAX = 0.5, 3.5          # Intervalo de precio €/litro de los que considero que es imposible que los combustibles no pertenezca
LATITUD_MIN, LATITUD_MAX = 27.0, 44.5      # Coordenadas que incluye Canarias
LONGITUD_MIN, LONGITUD_MAX = -18.5, 4.5
 