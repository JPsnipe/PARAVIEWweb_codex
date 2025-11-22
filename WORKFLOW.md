# Workflow de Desarrollo - PARAVIEWweb_codex

## Estructura de Branches

- **main**: Código estable y en producción. NUNCA trabajes directamente aquí.
- **develop**: Branch de desarrollo principal. Integra todas las features.
- **feature/xxx**: Branches para nuevas características.
- **fix/xxx**: Branches para correcciones de bugs.

## Workflow Recomendado

### 1. Comenzar una nueva característica

```bash
# Asegúrate de estar en develop y actualizado
git checkout develop
git pull origin develop

# Crea una nueva rama de característica
git checkout -b feature/nombre-descriptivo
```

### 2. Trabajar en tu feature

```bash
# Hacer cambios en el código...

# Ver qué archivos cambiaron
git status

# Agregar archivos modificados
git add .

# O agregar archivos específicos
git add archivo1.py archivo2.py

# Hacer commit con mensaje descriptivo
git commit -m "Descripción clara del cambio"

# Subir a GitHub
git push -u origin feature/nombre-descriptivo
```

### 3. Integrar cambios a develop

```bash
# Cambiar a develop
git checkout develop

# Actualizar develop
git pull origin develop

# Fusionar tu feature
git merge feature/nombre-descriptivo

# Subir a GitHub
git push origin develop

# Opcional: Borrar la rama feature ya integrada
git branch -d feature/nombre-descriptivo
git push origin --delete feature/nombre-descriptivo
```

### 4. Liberar a producción (main)

```bash
# Solo cuando develop esté estable y probado
git checkout main
git pull origin main
git merge develop
git push origin main

# Crear un tag de versión (opcional)
git tag -a v1.0.0 -m "Versión 1.0.0: Descripción"
git push origin v1.0.0
```

## Comandos Útiles Rápidos

```bash
# Ver el estado actual
git status

# Ver diferencias antes de commit
git diff

# Ver historial de commits
git log --oneline --graph --all

# Ver todas las ramas
git branch -a

# Cambiar de rama
git checkout nombre-rama

# Deshacer cambios NO commiteados
git restore archivo.py

# Ver ramas remotas
git remote -v
```

## Para Livecoding desde Móvil/Tablet

### GitHub.dev (Editor Web)
1. En el repositorio https://github.com/JPsnipe/PARAVIEWweb_codex
2. Presiona la tecla `.` (punto)
3. Se abrirá VS Code en el navegador
4. Puedes editar, commit y push desde ahí

### GitHub Mobile App
1. Descarga GitHub Mobile (iOS/Android)
2. Accede a tu repo
3. Puedes ver código, hacer commits simples y gestionar issues

### Codespaces (Entorno completo)
1. En tu repo, click en "Code" > "Codespaces" > "Create codespace"
2. Tendrás un entorno de desarrollo completo en la nube
3. Puedes ejecutar la app con `python app.py`

## Protección de main

Para evitar commits accidentales en main:

1. Ve a GitHub.com > Tu repo > Settings > Branches
2. Click en "Add rule"
3. Branch name pattern: `main`
4. Marca: "Require a pull request before merging"
5. Save changes

Ahora solo podrás integrar a main mediante Pull Requests.

## Tips de Seguridad

- Nunca commitees archivos `.env` o con credenciales
- Revisa el `.gitignore` antes de cada commit
- Usa `.gitignore` para excluir datos grandes de VTK si los generas
- Haz commits pequeños y frecuentes
- Escribe mensajes de commit descriptivos

## Estrategia de Versiones

```
main (v1.0.0) ──────────────────────────────────────────
                ↑                              ↑
develop ────────┴──────────────────────────────┴────────
                ↑         ↑          ↑
feature/A ──────┘         │          │
feature/B ────────────────┘          │
fix/bug-1 ───────────────────────────┘
```

## En caso de emergencia (deshacer cosas)

```bash
# Deshacer el último commit (mantiene cambios)
git reset --soft HEAD~1

# Deshacer cambios no commiteados
git restore .

# Ver qué cambió en un commit específico
git show <commit-hash>

# Volver a un commit anterior (CUIDADO)
git reset --hard <commit-hash>
```
