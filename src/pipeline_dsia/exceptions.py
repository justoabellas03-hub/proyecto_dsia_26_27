class GasolinerasError(Exception):
    """Error base del dominio."""
 
 
class DataLoadError(GasolinerasError):
    """No se han podido obtener los datos (red, fichero, formato...)."""
 
 
class ValidationError(GasolinerasError):
    """Los datos no superan la validación (p. ej. ninguna estación válida)."""


class ModelError(GasolinerasError):
    """Problema con el modelo: no existe, no se puede cargar o no hay datos para entrenarlo."""


class IAError(GasolinerasError):
    """Ha fallado la llamada al proveedor de IA (Hugging Face)."""
