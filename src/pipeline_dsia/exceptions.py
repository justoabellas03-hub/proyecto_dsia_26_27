class GasolinerasError(Exception):
    """Error base del dominio."""
 
 
class DataLoadError(GasolinerasError):
    """No se han podido obtener los datos (red, fichero, formato...)."""
 
 
class ValidationError(GasolinerasError):
    """Los datos no superan la validación (p. ej. ninguna estación válida)."""
 