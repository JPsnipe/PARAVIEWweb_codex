# Acceso Remoto a la Aplicación

## Túnel ngrok Activo

**URL Pública**: https://nonreviewable-jacki-fledgier.ngrok-free.dev

### Acceso desde Móvil/Tablet

1. Abre el navegador en tu dispositivo móvil o tablet
2. Visita: https://nonreviewable-jacki-fledgier.ngrok-free.dev
3. Si aparece una página de advertencia de ngrok, haz clic en "Visit Site"
4. La aplicación Blast Furnace Monitor se cargará

### Panel de Administración ngrok

Puedes monitorear las conexiones en tiempo real:
- **Dashboard local**: http://localhost:4040
- Aquí verás todas las peticiones HTTP/HTTPS que llegan al túnel

### Comandos Útiles

```bash
# Ver estado del túnel
curl http://localhost:4040/api/tunnels | python -m json.tool

# Detener ngrok
# Encuentra el proceso: ps aux | grep ngrok
# Mata el proceso: kill <PID>

# Reiniciar el túnel
ngrok http 9012
```

### Información Técnica

- **Puerto local**: 9012
- **Protocolo**: HTTPS
- **Túnel activo**: Sí (corriendo en segundo plano)
- **Tipo de cuenta**: Free (con página intermedia)

### Notas de Seguridad

- La URL de ngrok es temporal y cambiará si reinicias el túnel
- Con la cuenta gratuita, los visitantes verán una página de advertencia antes de acceder
- Considera autenticar tu cuenta ngrok o usar una cuenta de pago para URLs permanentes
- No compartas la URL públicamente si contiene datos sensibles

### Cuenta ngrok de Pago (Opcional)

Si quieres:
- URLs personalizadas (ej: `paraview.ngrok.io`)
- Sin página de advertencia
- Túneles persistentes
- Múltiples túneles simultáneos

Visita: https://ngrok.com/pricing

### Alternativas para Acceso Permanente

1. **GitHub Codespaces**: Entorno completo en la nube
2. **Railway.app**: Deploy gratuito con URL permanente
3. **Render.com**: Free tier para aplicaciones web
4. **Heroku**: Free tier (con limitaciones)
5. **VPS**: DigitalOcean, Linode, AWS EC2, etc.
