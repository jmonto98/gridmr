# GridMR

> **Resumen breve:** Proyecto en Python con soporte para Docker. Contiene scripts y archivos de configuración para ejecutar y desplegar la aplicación localmente.

---

## Tabla de contenidos

- [Descripción](#descripción)
- [Características](#características)
- [Requisitos](#requisitos)
- [Instalación (local)](#instalación-local)
- [Instalación (Docker)](#instalación-docker)
- [Configuración](#configuración)
- [Uso](#uso)
- [Estructura del proyecto](#estructura-del-proyecto)

---

## Descripción

`gridmr` es un proyecto escrito principalmente en Python que incluye:

- Scripts ejecutables (por ejemplo `split_pile.py`).
- Dependencias listadas en `requirements.txt`.
- Orquestación con Docker mediante `docker-compose.yml`.
- Un ejemplo de archivo de variables de entorno `.env.example`.

> **Nota:** Esta README es un template detallado pensado para ser completo y claro; adapta las secciones de `Uso` y `Argumentos` al comportamiento real de los scripts.

## Características

- Código en Python apto para entornos virtuales.
- Contenedor Docker para facilitar despliegue y pruebas.
- Archivo de ejemplo para variables de entorno.

## Requisitos

- Python 3.8+ (recomendado).  
- pip (o pipx) para instalar dependencias.  
- Docker y docker-compose (opcional, sólo si vas a usar la configuración Docker).

## Instalación (local)

```bash
# Clonar el repo
git clone https://github.com/jmonto98/gridmr.git
cd gridmr

# Crear un entorno virtual (recomendado)
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Instalar dependencias
pip install -r requirements.txt
```

## Instalación (Docker)

Si prefieres usar Docker (recomendado para reproducibilidad):

```bash
# Construir e iniciar servicios
docker-compose up --build

# Para ejecutar en segundo plano
docker-compose up -d --build

# Ver logs
docker-compose logs -f
```

## Configuración

Copia el archivo de ejemplo de variables de entorno y edítalo con tus valores:

```bash
cp .env.example .env
# Edita .env con tus credenciales / rutas / opciones
```

Incluye en `.env` las variables necesarias (puedes añadir aquí un listado de variables clave si lo deseas):

```
# EJEMPLO (rellenar con los nombres reales que use el proyecto)
# DATABASE_URL=postgres://user:pass@host:port/dbname
# API_KEY=tu_api_key
# OTRAVAR=valor
```

## Uso

### Ejecutar el script principal

El proyecto contiene el script `split_pile.py`. La forma de invocarlo dependerá de los argumentos que defina el propio script. Un ejemplo genérico:

```bash
# Ejemplo (ajusta según los argumentos reales del script)
python split_pile.py --input data/entrada.csv --output data/salida/ --n-piles 4
```

> **Importante:** Revisa el encabezado del script (`--help`) para conocer las opciones reales si el script usa `argparse` o similar:

```bash
python split_file.py --help
```

### Usar con Docker

Si preferiste levantar con `docker-compose`, revisa el `docker-compose.yml` para ver el nombre del servicio que ejecuta el script o la app. Para ejecutar un comando puntual dentro del contenedor:

```bash
# Obtener ID/name del contenedor (o usar el service_name del compose)
docker-compose run --rm <service_name> python split_pile.py --help
```

## Estructura del proyecto

Describiré los archivos detectados automáticamente en el repo. Completa/desarrolla estas entradas con más detalle si lo deseas:

```
├─ .env.example       # Ejemplo de variables de entorno
├─ docker-compose.yml # Definición de servicios Docker
├─ requirements.txt   # Dependencias Python
├─ split_pile.py      # Script principal (documentar su propósito y opciones)
├─ .gitignore
```

