---
name: opencode-task-generation
description: "Escribir una tarea para OpenCode con el formato de docs/futures/05_COLA_Y_ROADMAP.md §4, adaptada a DeepSeek V4.1 Flash: una sesión, ficheros cerrados, cifras exactas en los tests y punto de parada. Usar cada vez que se delegue implementación."
---

# opencode-task-generation

## Propósito
Que el modelo implementador (DeepSeek V4.1 Flash, OpenCode Go) no tenga que interpretar.

## Cuándo usarla
Al pasar una especificación a implementación.

## Entradas
Spec aprobada, ficheros permitidos, dependencias de la cola.

## Procedimiento
1. Una tarea = una sesión; si no cabe, dividirla.
2. Pegar siempre el BLOQUE COMÚN de `05 §4.1`.
3. Listar ficheros permitidos (nuevos o existentes) y prohibidos.
4. Firmas de funciones y estructuras explícitas.
5. Tests con valores exactos (no "debería funcionar").
6. Comando de cierre y fichero de informe `docs/futures/WORKER_REPORTS/<ID>.md`.
7. Decir el modelo: **DeepSeek V4.1 Flash**.

## Validación
Checklist: ficheros, firmas, cifras, parada, prohibiciones de AGENTS.md.

## Salidas
Prompt pegable en un bloque `text`.

## Falla si
La tarea toca motores compartidos sin lock o mezcla dos tareas.

## Restricciones
Nunca pedir campañas, descargas de pago, push ni borrados.
