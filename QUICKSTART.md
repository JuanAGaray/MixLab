# 🚀 Guía de Inicio Rápido - Frozz

## Pasos para Ejecutar el Proyecto

### 1. Activar el Entorno Virtual

**Windows:**
```bash
venv\Scripts\activate
```

**Linux/Mac:**
```bash
source venv/bin/activate
```

### 2. Instalar Dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar Base de Datos

Asegúrate de tener PostgreSQL instalado y ejecutando. Luego crea la base de datos:

```sql
CREATE DATABASE frozz_db;
```

### 4. Crear Archivo .env

Crea un archivo `.env` en la raíz del proyecto con:

```env
SECRET_KEY=django-insecure-cambiar-en-produccion
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=frozz_db
DB_USER=postgres
DB_PASSWORD=tu_password_postgres
DB_HOST=localhost
DB_PORT=5432
```

### 5. Ejecutar Migraciones

```bash
python manage.py makemigrations
python manage.py migrate
```

### 6. Crear Superusuario

```bash
python manage.py createsuperuser
```

Sigue las instrucciones para crear un usuario administrador.

### 7. Cargar Datos de Ejemplo (Opcional)

Puedes crear productos y categorías desde el panel de administración en:
`http://127.0.0.1:8000/admin/`

### 8. Ejecutar el Servidor

```bash
python manage.py runserver
```

### 9. Acceder a la Aplicación

- **Frontend:** http://127.0.0.1:8000/
- **Admin Panel:** http://127.0.0.1:8000/admin/
- **API:** http://127.0.0.1:8000/api/

## 📝 Notas Importantes

- Las imágenes se guardan en la carpeta `media/` (se crea automáticamente)
- Los archivos estáticos se recopilan en `staticfiles/` con `python manage.py collectstatic`
- El perfil de usuario se crea automáticamente cuando un usuario se registra

## 🔑 Usuarios de Prueba

Después de crear el superusuario, puedes:
1. Iniciar sesión en el admin panel
2. Crear categorías y productos
3. Crear usuarios normales desde el admin o desde el registro público

## 🎯 Próximos Pasos

1. Crear categorías desde el admin
2. Agregar productos (venta, alquiler, insumos, desechables)
3. Probar el flujo de compra completo
4. Probar el sistema de alquileres

