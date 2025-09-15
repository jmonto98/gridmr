# README.md

## GridMR — Mini MapReduce con FastAPI + Docker

Sistema distribuido **Maestro–Workers** para procesar textos en paralelo (estilo MapReduce). El **maestro** coordina tareas y agrega resultados; los **workers** ejecutan cómputo sobre *chunks* de archivos de texto. Ideal para practicar conceptos de partición, asignación, tolerancia a fallos y agregación de resultados.

---

## Tabla de contenidos
- [Arquitectura](#arquitectura)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Requisitos](#requisitos)
- [Configuración](#configuración)
- [Inicio rápido](#inicio-rápido)
- [Flujo de datos](#flujo-de-datos)
- [Catálogo de operaciones](#catálogo-de-operaciones)
- [Ejemplos (curl)](#ejemplos-curl)
- [Desarrollo local](#desarrollo-local)
- [Observabilidad y salud](#observabilidad-y-salud)
- [Resolución de problemas](#resolución-de-problemas)
- [Hoja de ruta](#hoja-de-ruta)
- [Licencia](#licencia)

---

## Arquitectura
```
Cliente ─► Maestro (FastAPI) ─► Workers (FastAPI)
               │                   │
               │                   ├─ Acceso local a /data (chunks)
               │
               └─ Agregación de resultados + respuesta al cliente
```
- **Maestro**: recibe un *job* (archivo objetivo + operación/categoría), consulta a los workers, agrega y devuelve el resultado.
- **Workers**: procesan *chunks* locales montados en `/data` según un **manifest** que asigna *chunks* a cada worker.
- **Partición previa**: `split_pile.py` divide libros y genera `*.manifest.json`.

> **Nota**: Se puede justificar *reduce central* (en el Maestro) o extender con **servicio de reducers** y *shuffle*.

---

## Estructura del repositorio
```
gridmr-main/
├─ .env.example
├─ .gitignore
├─ books/                 # Datos de ejemplo (*.txt)
├─ docker-compose.yml
├─ master/
│  ├─ Dockerfile
│  ├─ app.py              # API del Maestro
│  ├─ gridfs/
│  │  └─ manifests/       # Manifests generados por split_pile.py
│  └─ requirements.txt
├─ requirements.txt       # opcional (tools/script)
├─ split_pile.py          # Splitter de libros y generador de manifests
└─ worker/
   ├─ Dockerfile
   ├─ app.py              # API del Worker
   └─ requirements.txt
```

---

## Requisitos
- **Docker** y **Docker Compose**.
- (Opcional) **Python ≥ 3.11** si vas a usar `split_pile.py` fuera de Docker.

---

## Configuración
1. Copia variables base:
   ```bash
   cp .env.example .env
   ```
   Define capacidades por worker, p. ej.:
   ```env
   WORKER1_CAPACITY=4
   WORKER2_CAPACITY=4
   WORKER3_CAPACITY=4
   WORKER4_CAPACITY=4
   ```

2. Coloca tus archivos `.txt` en `books/` (ej.: `Quijote.txt`, `Odisea.txt`).

3. **Genera los chunks y manifests** (particionado previo):
   ```bash
   # Requiere Python local (o usa un contenedor temporal de python:3.11)
   python split_pile.py --input books/Quijote.txt --file-key Quijote
   python split_pile.py --input books/Odisea.txt  --file-key Odisea
   ```
   Esto creará `master/gridfs/manifests/<file>.manifest.json` y poblará `./chunks/workerX/`.

> Si encuentras líneas con `...` en `docker-compose.yml` o en algún `*.manifest.json`, **elimínalas**/regenera los archivos. Son *placeholders* y rompen el YAML/JSON.

4. (Opcional) Ajusta `docker-compose.yml` si despliegas en varios hosts (puertos, URLs públicas, CORS/HTTPS).

---

## Inicio rápido
```bash
# Compila y levanta Maestro + 4 Workers
docker compose up --build

# Maestro en http://localhost:8000 (Swagger UI en /docs)
# Workers en http://localhost:8001..8004
```
Verifica:
```bash
curl http://localhost:8000/workers
curl http://localhost:8000/files
```
Ejecuta un job:
```bash
curl -X POST http://localhost:8000/job \
  -H "Content-Type: application/json" \
  -d '{
        "file_key":"Quijote",
        "operation":"cont",
        "category":"palabras"
      }'
```

---

## Flujo de datos
1. `split_pile.py` divide el texto y genera *manifests* con asignación de *chunks* a workers.
2. El Maestro recibe un `JobRequest` y decide qué workers participan.
3. Cada Worker lee sus *chunks* desde `/data` y ejecuta la operación solicitada.
4. El Maestro agrega las respuestas y responde al cliente.

---

## Catálogo de operaciones
- `operation`: `cont` (conteo) | `prom` (promedios simples)
- `category`: `palabras` | `vocales` | `letras`
- `target` (opcional): objetivo específico (p. ej., vocal **"a"**, letra **"b"** o palabra **"molino"**).

**Ejemplos de semántica** (orientativo):
- `cont/palabras`: total de palabras (o de `target` si se provee).
- `cont/vocales`: total de vocales (o de la vocal `target`).
- `prom/palabras`: promedio de palabras por línea.
- `prom/letras`: promedio de letras por línea.

> La semántica exacta depende de tu implementación en `worker/app.py`. Ajusta la documentación si difiere.

---

## Ejemplos (curl)
Listar workers y archivos conocidos:
```bash
curl http://localhost:8000/workers
curl http://localhost:8000/files
```
Conteo total de palabras:
```bash
curl -X POST http://localhost:8000/job \
  -H "Content-Type: application/json" \
  -d '{"file_key":"Quijote","operation":"cont","category":"palabras"}'
```
Conteo de la vocal "a":
```bash
curl -X POST http://localhost:8000/job \
  -H "Content-Type: application/json" \
  -d '{"file_key":"Odisea","operation":"cont","category":"vocales","target":"a"}'
```
Promedio de palabras por línea:
```bash
curl -X POST http://localhost:8000/job \
  -H "Content-Type: application/json" \
  -d '{"file_key":"Quijote","operation":"prom","category":"palabras"}'
```

---

## Desarrollo local
- Maestro:
  ```bash
  cd master
  uvicorn app:app --reload --host 0.0.0.0 --port 8000
  ```
- Worker (puerto ejemplo 8001):
  ```bash
  cd worker
  WORKER_ID=worker1 WORKER_CAPACITY=4 WORKER_PORT=8001 \
  uvicorn app:app --reload --host 0.0.0.0 --port 8001
  ```

**Variables de entorno (resumen)**
- Maestro: `WORKERS` (lista de URLs de workers separados por coma).
- Worker: `WORKER_ID`, `WORKER_CAPACITY`, `WORKER_PORT`.

---

## Observabilidad y salud
Añade *healthchecks* en `docker-compose.yml` (recomendado):
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8000/workers"]
  interval: 10s
  timeout: 3s
  retries: 5
restart: unless-stopped
```
Para workers, usa `GET /info` en el `test`.

> Implementa logs estructurados (JSON) y maneja timeouts/reintentos por chunk para resiliencia.

---

## Resolución de problemas
- **404 file_key**: asegúrate de haber corrido `split_pile.py` y de que existan `./chunks/workerX/`.
- **YAML/JSON inválido**: elimina cualquier `...` residual y valida con `yq`/`jq`.
- **CORS**: si expones el Maestro públicamente, habilita `CORSMiddleware` en FastAPI.

---

## Hoja de ruta
- Planificador dinámico (asignación por disponibilidad/latencia).
- Reintentos y *straggler mitigation*.
- Reducers dedicados + *shuffle*.
- Métricas y `/metrics` (Prometheus) o logs enriquecidos.
- Pruebas con `pytest`.

---

## Licencia
MIT (o la que definas).

---

# Documentación de APIs

> Esta sección incluye **especificación funcional** y **OpenAPI 3.1** de referencia para Maestro y Workers. Ajusta campos si tu implementación devuelve estructuras distintas.

## Maestro — API de coordinación

### GET /workers
Devuelve información resumida de los workers configurados.

**200**
```json
{
  "workers_expected": 4,
  "workers": [
    {"id": "worker1", "url": "http://worker1:8001", "capacity": 4, "status": "ok"},
    {"id": "worker2", "url": "http://worker2:8002", "capacity": 4, "status": "ok"}
  ]
}
```

### GET /files
Lista los `file_key` disponibles a partir de los manifests.

**200**
```json
{
  "files": [
    {
      "file_key": "Quijote",
      "manifest": "master/gridfs/manifests/Quijote.manifest.json",
      "chunks": 16
    },
    { "file_key": "Odisea", "manifest": "...", "chunks": 12 }
  ]
}
```

### POST /job
Ejecuta un trabajo sobre un `file_key`.

**Body** `JobRequest`
```json
{
  "file_key": "Quijote",
  "operation": "cont",
  "category": "palabras",
  "target": null
}
```
- `operation`: `cont` | `prom`
- `category`: `palabras` | `vocales` | `letras`
- `target` (opcional): restringe el conteo/promedio a una vocal/letra/palabra específica.

**200** `JobResponse` (ejemplo conteo de palabras)
```json
{
  "file_key": "Quijote",
  "operation": "cont",
  "category": "palabras",
  "target": null,
  "status": {
    "workers_expected": 4,
    "workers_responded": 4,
    "missing_workers": []
  },
  "result": {
    "count_total": 123456,
    "counts_per_chunk": {
      "chunk_000.txt": 7890,
      "chunk_001.txt": 8011
    }
  },
  "warnings": []
}
```

**Posibles errores**
- `400` solicitud inválida.
- `404` `file_key` no encontrado en manifests.
- `502` fallo al invocar un worker.

---

## Worker — API de ejecución

### GET /info
Devuelve metadatos del worker y estado mínimo.

**200**
```json
{
  "id": "worker1",
  "capacity": 4,
  "port": 8001,
  "data_path": "/data",
  "n_chunks": 4
}
```

### POST /run
Ejecuta el cómputo local para un `file_key`.

**Body** `RunRequest`
```json
{
  "file_key": "Quijote",
  "operation": "cont",
  "category": "palabras",
  "target": null,
  "chunk_ids": ["chunk_000.txt", "chunk_001.txt"]
}
```
- `chunk_ids` (opcional): si se omite, el worker procesa los *chunks* que le correspondan según el manifest.

**200** `RunResult`
```json
{
  "worker_id": "worker1",
  "file_key": "Quijote",
  "result": {
    "count_total": 15901,
    "counts_per_chunk": {
      "chunk_000.txt": 7890,
      "chunk_001.txt": 8011
    }
  },
  "processed_chunks": ["chunk_000.txt", "chunk_001.txt"],
  "duration_ms": 212
}
```

**Posibles errores**
- `404` `file_key` sin *chunks* en `/data`.
- `400` parámetros inválidos.

---

## OpenAPI 3.1 — Maestro (referencia)
```yaml
openapi: 3.1.0
info:
  title: GridMR Maestro API
  version: 0.1.0
servers:
  - url: http://localhost:8000
paths:
  /workers:
    get:
      summary: Lista el estado de workers
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/WorkersResponse'
  /files:
    get:
      summary: Lista file_keys disponibles
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/FilesResponse'
  /job:
    post:
      summary: Ejecuta un trabajo Map-like y agrega resultados
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/JobRequest'
      responses:
        '200':
          description: Resultado agregado
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/JobResponse'
        '400': { description: Solicitud inválida }
        '404': { description: file_key no encontrado }
        '502': { description: Error al invocar worker }
components:
  schemas:
    JobRequest:
      type: object
      properties:
        file_key: { type: string }
        operation:
          type: string
          enum: [cont, prom]
        category:
          type: string
          enum: [palabras, vocales, letras]
        target:
          type: [string, 'null']
      required: [file_key, operation, category]
    JobResponse:
      type: object
      properties:
        file_key: { type: string }
        operation: { type: string }
        category: { type: string }
        target: { type: [string, 'null'] }
        status:
          type: object
          properties:
            workers_expected: { type: integer }
            workers_responded: { type: integer }
            missing_workers:
              type: array
              items: { type: string }
        result:
          type: object
          description: Estructura dependiente de operation/category
        warnings:
          type: array
          items: { type: string }
      required: [file_key, operation, category, status, result]
    WorkersResponse:
      type: object
      properties:
        workers_expected: { type: integer }
        workers:
          type: array
          items:
            $ref: '#/components/schemas/WorkerInfo'
    WorkerInfo:
      type: object
      properties:
        id: { type: string }
        url: { type: string }
        capacity: { type: integer }
        status: { type: string }
    FilesResponse:
      type: object
      properties:
        files:
          type: array
          items:
            $ref: '#/components/schemas/FileInfo'
    FileInfo:
      type: object
      properties:
        file_key: { type: string }
        manifest: { type: string }
        chunks: { type: integer }
```

---

## OpenAPI 3.1 — Worker (referencia)
```yaml
openapi: 3.1.0
info:
  title: GridMR Worker API
  version: 0.1.0
servers:
  - url: http://localhost:8001
paths:
  /info:
    get:
      summary: Información básica del worker
      responses:
        '200':
          description: OK
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/WorkerInfo'
  /run:
    post:
      summary: Ejecuta cómputo sobre chunks locales
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/RunRequest'
      responses:
        '200':
          description: Resultado del worker
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/RunResult'
        '400': { description: Solicitud inválida }
        '404': { description: file_key sin chunks }
components:
  schemas:
    WorkerInfo:
      type: object
      properties:
        id: { type: string }
        capacity: { type: integer }
        port: { type: integer }
        data_path: { type: string }
        n_chunks: { type: integer }
    RunRequest:
      type: object
      properties:
        file_key: { type: string }
        operation: { type: string, enum: [cont, prom] }
        category: { type: string, enum: [palabras, vocales, letras] }
        target: { type: [string, 'null'] }
        chunk_ids:
          type: array
          items: { type: string }
      required: [file_key, operation, category]
    RunResult:
      type: object
      properties:
        worker_id: { type: string }
        file_key: { type: string }
        result: { type: object }
        processed_chunks:
          type: array
          items: { type: string }
        duration_ms: { type: integer }
      required: [worker_id, file_key, result]
```

---

### Convenciones generales
- **Tipos y normalización**: por defecto, minúsculas y texto normalizado (sin tildes) para conteos.
- **Timeouts**: define en Maestro un timeout por worker y número de reintentos.
- **Parcialidad**: si faltan respuestas, el Maestro puede devolver `warnings` y `missing_workers`.
- **CORS/Auth**: si se expone a Internet, habilitar CORS y, si aplica, un esquema de API key simple.

---

> **Siguiente paso sugerido**: crear `openapi-master.yaml` y `openapi-worker.yaml` como archivos en el repo y enlazarlos desde el README; o integrar los esquemas con FastAPI para publicar `/openapi.json` y `/docs` automáticamente.

