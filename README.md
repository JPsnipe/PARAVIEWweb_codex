# ParaView Blast Furnace Monitor

Aplicación web interactiva para monitorear y visualizar datos de un horno industrial (blast furnace) usando VTK, ParaView y Trame.

## Características

- Visualización 3D de datos de temperatura del horno
- Gráficos interactivos con Plotly
- Interfaz web responsive con Vuetify 3
- Sondeo de temperatura en puntos específicos
- Control de isosuperficies y opacidad
- Sistema de clipping para análisis seccional

## Tecnologías

- **Trame**: Framework para aplicaciones científicas web
- **VTK**: Visualización 3D de datos científicos
- **Plotly**: Gráficos interactivos
- **Pandas**: Procesamiento de datos
- **Vuetify 3**: UI components

## Instalación

```bash
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

## Uso

```bash
python app.py
```

La aplicación estará disponible en `http://localhost:8080`

## Estructura del Proyecto

- `app.py`: Aplicación principal Trame con UI
- `pipeline.py`: Pipeline de procesamiento VTK/ParaView
- `requirements.txt`: Dependencias del proyecto
- `loading.tpl`: Template de carga
- `index-asset.js`: Assets JavaScript

## Desarrollo con Branches

Para proteger el código estable y facilitar el desarrollo:

```bash
# Trabajar en una nueva característica
git checkout -b feature/nombre-caracteristica

# Hacer cambios y commits
git add .
git commit -m "Descripción del cambio"

# Subir branch al remoto
git push -u origin feature/nombre-caracteristica

# Cuando esté listo, fusionar a main
git checkout main
git merge feature/nombre-caracteristica
git push
```

## Livecoding desde Móvil/Tablet

Este repositorio está optimizado para trabajar con:
- GitHub Codespaces
- GitHub.dev (presiona `.` en el repo)
- Agentes web de Codex
- Gemini Code Assist

## Licencia

MIT
