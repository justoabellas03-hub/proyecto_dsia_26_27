"""Pipeline de gasolineras: carga → selección de columnas → normalización → contrato.
 
Uso:
    python -m gasolineras_app.main                       # datos en vivo de la API
    python -m gasolineras_app.main Datos/precios.json    # JSON guardado
"""
 
import sys
 
from pipeline_dsia.constants import URL_API
from pipeline_dsia.exceptions import DataLoadError, ValidationError
from pipeline_dsia.loader import cargar_datos, cargar_fichero
from pipeline_dsia.validator import normalizar_numeros, validar_estaciones
 
# Columnas del DataFrame general que usamos en el proyecto
COLUMNAS = [
    "IDEESS", "Rótulo", "Tipo Venta",
    "Dirección", "C.P.", "Municipio", "Provincia",
    "IDMunicipio", "IDProvincia", "IDCCAA",
    "Latitud", "Longitud (WGS84)",
    "Precio Gasolina 95 E5", "Precio Gasolina 98 E5",
    "Precio Gasoleo A", "Precio Gasoleo Premium",
]
 
 
def main():
    # 1. Cargar: desde fichero si se indica, si no desde la API
    try:
        if len(sys.argv) > 1:
            df = cargar_fichero(sys.argv[1])
        else:
            df = cargar_datos(URL_API)
    except DataLoadError as exc:
        print(f"Error al cargar los datos: {exc}")
        return 2
    print(f"Estaciones cargadas: {len(df)}")
 
    # 2. Nuevo DataFrame solo con las columnas que nos interesan
    df_util = df[COLUMNAS].copy()
 
    # 3. Coma decimal → punto
    df_normalizado = normalizar_numeros(df_util)
 
    # 4. Contrato de datos → DataFrame de válidas y de errores
    try:
        df_validas, df_errores = validar_estaciones(df_normalizado)
    except ValidationError as exc:
        print(f"Validación fallida: {exc}")
        return 1
    print(f"Válidas: {len(df_validas)} · Errores: {len(df_errores)}")
 
    # 5. Aquí empiezan las métricas
    print(df_validas.head())
    return 0
 
 
if __name__ == "__main__":
    sys.exit(main())
