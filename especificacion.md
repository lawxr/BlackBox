# Especificación del servicio — Caja Negra

Este documento describe el comportamiento observable del servicio para permitir su reimplementación sin consultar al original.

Nivel de confianza:
- **confirmado**: probado y reproducible en experimentos propios.
- **probable**: observado una vez o inferido formalmente.
- **supuesto**: no probado; comportamiento por defecto adoptado por la réplica.

---

## 1. Entrada
Rutas, métodos, autenticación, forma del cuerpo y límites observados.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| ENT-01 | `GET /health` responde `200` y cuerpo `{"ok": true}` | 1 | confirmado |
| ENT-02 | `POST /__reset` reinicia el estado lógico completo y responde `200 {"ok": true}` | 2 | confirmado |
| ENT-03 | `POST /msg` recibe `{"m": "..."}` | 3 | confirmado |
| ENT-04 | Rutas inexistentes responden formato del original | TBD | supuesto |
| ENT-05 | Validación de cabecera `Authorization: Bearer <token>` | TBD | supuesto |

---

## 2. Integridad
Validación de formato de mensaje, checksum y delimitadores.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| INT-01 | Formato general `COMANDO;ARG1;...;CONTROL` delimitado por punto y coma | TBD | supuesto |
| INT-02 | Algoritmo de checksum / control | TBD | supuesto |

---

## 3. Comandos
Comandos soportados, argumentos, efecto y respuesta.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| CMD-01 | `PING;...` responde `{"pong": true}` | 3 | confirmado |
| CMD-02 | `ALTA;<NOMBRE>;<CTRL>` registra una nueva cuenta | TBD | supuesto |
| CMD-03 | `DEPOSITO;<CTA>;<MONTO>;<CTRL>` añade saldo a una cuenta | TBD | supuesto |
| CMD-04 | `TRANSFER;<ORIGEN>;<DESTINO>;<MONTO>;<CTRL>` transfiere saldo | TBD | supuesto |
| CMD-05 | `CONSULTA;<CTA>;<CTRL>` consulta balance y estado | TBD | supuesto |
| CMD-06 | `ANULA;<OP-ID>;<CTRL>` anula una transacción previa | TBD | supuesto |

---

## 4. Memoria entre requests
Estado persistido entre solicitudes, identificadores secuenciales y saldos.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| MEM-01 | Los identificadores de cuenta siguen patrón incremental `AC-XXXX` | TBD | supuesto |
| MEM-02 | Los identificadores de operación siguen patrón incremental `OP-XXXX` | TBD | supuesto |
| MEM-03 | El estado se aísla por token y se restablece tras `POST /__reset` | TBD | supuesto |

---

## 5. Errores
Códigos de error observados, cuerpo exacto y orden de evaluación.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| ERR-01 | Error E201: Formato de control inválido | TBD | supuesto |
| ERR-02 | Error E202: Checksum / control no coincide | TBD | supuesto |
| ERR-03 | Error E301 / E302: Formato o aridad de comando incorrecta | TBD | supuesto |
| ERR-04 | Error E401: Cuenta inexistente | TBD | supuesto |
| ERR-05 | Error E506: Límite por transferencia superado | TBD | supuesto |
| ERR-06 | Error E507: Saldo insuficiente | TBD | supuesto |

---

## 6. Cambios durante el día
Registro de divergencias detectadas en la versión activa del servicio durante la jornada.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| DRIFT-01 | Línea base inicial establecida por la mañana | TBD | supuesto |

---

## 7. Riesgos
Comportamientos anómalos o peligrosos del servicio original que no deberían heredarse en un cliente nuevo.

| ID | Comportamiento | Evidencia | Confianza |
|---|---|---|---|
| RSK-01 | Errores ortográficos en contratos (e.g., `"status":"recieved"`) | TBD | supuesto |
| RSK-02 | Falta de idempotencia en mutaciones sin control de replay | TBD | supuesto |
