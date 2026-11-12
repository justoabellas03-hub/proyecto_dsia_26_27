URL_API = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestres/"
)

# Precios de un día pasado: se añade la fecha en formato dd-mm-aaaa al final
URL_API_HIST = (
    "https://sedeaplicaciones.minetur.gob.es/ServiciosRESTCarburantes/"
    "PreciosCarburantes/EstacionesTerrestresHist/"
)

# --- Fuentes externas (mercados) ---
# Brent (USD/barril), serie DCOILBRENTEU de FRED: CSV con todo el histórico, sin clave
URL_BRENT = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU"
# Tipo de cambio de referencia del BCE: dólares por 1 euro, diario, sin clave
URL_EURUSD = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?format=csvdata"


 
# --- Columnas que usamos (nombres tal y como vienen en la API) ---
COLUMNAS = [
    "IDEESS", "Rótulo", "Tipo Venta",
    "Dirección", "C.P.", "Municipio", "Provincia",
    "IDMunicipio", "IDProvincia", "IDCCAA",
    "Latitud", "Longitud (WGS84)",
    "Precio Gasolina 95 E5", "Precio Gasolina 98 E5",
    "Precio Gasoleo A", "Precio Gasoleo Premium",
]
COORDENADAS = ("Latitud", "Longitud (WGS84)")
 
CAMPOS_PRECIOS = (
    "Precio Gasolina 95 E5",
    "Precio Gasolina 98 E5",
    "Precio Gasoleo A",
    "Precio Gasoleo Premium",
)
 

 
# --- Rangos plausibles ---
PRECIO_MIN, PRECIO_MAX = 0.5, 3.5          # Intervalo de precio €/litro de los que considero que es imposible que los combustibles no pertenezca
LATITUD_MIN, LATITUD_MAX = 27.0, 44.5      # Coordenadas que incluye Canarias
LONGITUD_MIN, LONGITUD_MAX = -18.5, 4.5
 