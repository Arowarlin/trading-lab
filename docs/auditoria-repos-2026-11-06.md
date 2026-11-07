# Auditoría de repos de referencia - 2026-11-06

Objetivo: decidir qué tomar de los repos propuestos sin contaminar el laboratorio
con código sin licencia, endpoints de exchange con escritura o dependencias
pesadas. Regla del proyecto: **nada se activa solo y nada envía órdenes reales**.

## Resumen

| Repo | Licencia | Actividad | Veredicto | Qué se tomó |
|---|---|---|---|---|
| [jaypolanco96/pixel-hedge-fund](https://github.com/jaypolanco96/pixel-hedge-fund) | **Sin licencia** | Creado 2026-09, último push 2026-10-08, 4★ | **No copiar código ni arte** | Solo inspiración conceptual: oficina pixel, HUD dentro de la escena, estados de personajes. |
| [ATK-zk/company-pixel-office](https://github.com/ATK-zk/company-pixel-office) | **MIT** (sprites de pixel-agents, MIT) | Creado 2026-10, push 2026-10-13, 4★ | **Inspiración; assets opcionales con atribución** | Idea de roster, personajes con rol/estado, burbujas y foco por personaje. No se copiaron assets. |
| [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot) | **Apache-2.0** | 8.4k★, activo, organización establecida | **Adoptar principios** | “Modelos razonan, el software calcula, los agentes orquestan, el sistema verifica”. En la UI: provenance determinista vs. narrativa LLM. |

## Detalle

### pixel-hedge-fund

- SvelteKit, oficina pixel muy elaborada, simulador de escritorio con datos de
  Bybit/BloFin.
- **Riesgo:** no tiene archivo de licencia; por defecto, todos los derechos
  reservados. Tampoco se debe reutilizar su arte.
- Contiene rutas de escritura a exchanges (`/api/bybit/order`, `/api/blofin/order`),
  gestión de claves y fallback a `.env.local`. No es un componente que queramos
  ejecutar en una máquina con claves reales.
- **Decisión:** no se clona, no se copia. Se toma la idea de “oficina vivida” y
  de estados visuales; la implementación de la Sala es propia (CSS/HTML/SVG).

### company-pixel-office

- Sitio estático (JS + PNGs) con seis personajes, roster, burbujas y escena
  nocturna. Licencia MIT; los sprites declaran MIT de pixel-agents.
- **Decisión:** se toma la estructura de interacción (personaje → rol → tarea →
  foco), pero se dibuja una oficina propia para no arrastrar 6.8 MB de assets ni
  depender de una estética/fuente concreta.
- Si en el futuro se usan sus sprites, hay que conservar `LICENSE-pixel-agents-MIT`
  y la atribución en el README.

### FinRobot

- Plataforma de equity research con agentes, cálculo determinista y auditoría.
  V2 usa PydanticAI + FastAPI + React/Tauri; V1 es una app web; V0 es AutoGen.
- **Lo valioso:** separación estricta entre números calculados por código y
  narración del LLM; provenance; pipelines de investigación; debate bull/bear y
  juez; validación determinista.
- **Lo que no encaja ahora:** V2 requiere Python 3.10/3.11, muchas dependencias,
  claves de proveedores (FMP, Finnhub, etc.) y un frontend React/Tauri. Nuestro
  LLM local de 27B y el alcance paper/FTMO no justifican ese peso.
- **Decisión:** se adopta el principio y se refleja en la UI (“Cifras: motor
  determinista · Tesis: LLM local”). Una integración futura sería un proveedor
  de research externo, no un reemplazo del núcleo.

## Qué se implementó

1. **Sala pixel propia** en `lab web` → pestaña **Sala**:
   - 10 roles de TradingAgents + estados (`en espera`, `trabajando`,
     `completado`, `error`).
   - Señales visuales: LED del monitor, burbujas, tablero MARKET WIRE, reloj.
   - Datos reales de `data/agent_runs/*.json`, `logs/deep_*.log` y la acción en
     curso; no hay datos inventados.
   - Clic en un personaje: rol, estado, última contribución y acceso al informe.
2. **Provenance visible** en el detalle del agente: los indicadores, límites y
   guard son deterministas; el LLM solo narra/decide sobre esa evidencia.
3. **Sin nuevas dependencias**: la Sala es HTML/CSS/JS servida por el mismo
   servidor estándar.

## Qué se rechazó

- Copiar código/arte de pixel-hedge-fund (sin licencia).
- Integrar endpoints de escritura a exchanges o gestión de claves de terceros.
- Instalar FinRobot completo o clonar FinGPT/FinRL en esta fase.
- Añadir un motor de juego o un framework frontend solo para la oficina.

## Referencias

- Licencia MIT: https://opensource.org/license/mit
- Apache-2.0: https://www.apache.org/licenses/LICENSE-2.0
- FinRobot: https://github.com/AI4Finance-Foundation/FinRobot
- company-pixel-office: https://github.com/ATK-zk/company-pixel-office
- pixel-hedge-fund: https://github.com/jaypolanco96/pixel-hedge-fund
