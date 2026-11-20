"""TradingLab Discovery Lab (TradingLab 2.0).

Motor de descubrimiento de estrategias CFD/futuros. Esta capa es **aislada**:

* no importa ni llama funciones de órdenes (``submit_market``, ``close_position``,
  ``modify_position``);
* no escribe en tablas del carril protegido ni en sus archivos;
* trabaja con barras cerradas y ejecuta en el open siguiente.

La Fase 0 solo crea el paquete, la configuración y los tests de aislamiento.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
