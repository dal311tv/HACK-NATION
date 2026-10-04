# Navegador IA

Aplicación web tipo chat, escrita en PHP y organizada con MVC. La interfaz llama al controlador PHP; el modelo `OpenAIChatModel` se conecta a la Responses API de OpenAI. La clave API se mantiene en el servidor.

## Estructura MVC

- `app/Models/OpenAIChatModel.php`: solicita respuestas a OpenAI.
- `app/Controllers/ChatController.php`: valida la petición, coordina el modelo y sirve la vista.
- `app/Views/chat.php`: interfaz del chat.
- `index.php`: entrada principal y render de la vista.
- `api/chat.php`: ruta JSON que delega en el controlador.

## Ejecutar en Windows

PHP 8.5.11 para Windows x64 está incluido en `runtime/php`, con cURL y OpenSSL habilitados. Desde la carpeta del proyecto, arranca el servidor con:

```powershell
.\runtime\php\php.exe -S localhost:8000
```

Abre `http://localhost:8000`. Para iniciar el servidor y pegar la clave API de forma oculta en PowerShell:

```powershell
.\start.ps1
```

De forma opcional, selecciona un modelo disponible para tu cuenta con `$env:OPENAI_MODEL = "modelo-disponible"` antes de arrancar.

En el servidor de publicación, configura `OPENAI_API_KEY` en el entorno de PHP. No agregues la clave al HTML, JavaScript ni al repositorio.
