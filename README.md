# Frozz - E-Commerce + Sistema de Alquileres

Aplicación web Django completa para una marca de granizadoras con funcionalidades de e-commerce y sistema de alquileres.

## 🚀 Características Principales

### E-Commerce
- ✅ Catálogo de productos con categorías
- ✅ Carrito de compras
- ✅ Proceso de checkout
- ✅ Gestión de pedidos y estados
- ✅ Historial de pedidos del usuario

### Sistema de Alquileres
- ✅ Alquiler de máquinas granizadoras
- ✅ Precios por día, semana y mes
- ✅ Calendario de disponibilidad
- ✅ Gestión de reservas

### Autenticación y Usuarios
- ✅ Registro y login de usuarios
- ✅ Perfiles de usuario
- ✅ Roles: Cliente y Administrador

### Panel de Administración
- ✅ Gestión completa de productos, categorías, pedidos y alquileres
- ✅ Dashboard con métricas básicas

### API REST
- ✅ Endpoints para productos, categorías, pedidos y carrito
- ✅ Autenticación por sesión y token

## 📋 Requisitos Previos

- Python 3.10+
- PostgreSQL 12+
- pip (gestor de paquetes de Python)

## 🛠️ Instalación

### 1. Clonar el repositorio

```bash
cd Frozz
```

### 2. Crear y activar entorno virtual

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/Mac:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar base de datos PostgreSQL

Crear una base de datos PostgreSQL:

```sql
CREATE DATABASE frozz_db;
CREATE USER frozz_user WITH PASSWORD 'tu_password';
ALTER ROLE frozz_user SET client_encoding TO 'utf8';
ALTER ROLE frozz_user SET default_transaction_isolation TO 'read committed';
ALTER ROLE frozz_user SET timezone TO 'UTC';
GRANT ALL PRIVILEGES ON DATABASE frozz_db TO frozz_user;
```

### 5. Configurar variables de entorno

Crear un archivo `.env` en la raíz del proyecto:

```env
SECRET_KEY=tu-secret-key-super-segura-aqui
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=frozz_db
DB_USER=frozz_user
DB_PASSWORD=tu_password
DB_HOST=localhost
DB_PORT=5432
```

### 6. Ejecutar migraciones

```bash
python manage.py makemigrations
python manage.py migrate
```

### 7. Crear superusuario

```bash
python manage.py createsuperuser
```

### 8. Recopilar archivos estáticos

```bash
python manage.py collectstatic --noinput
```

### 9. Ejecutar servidor de desarrollo

```bash
python manage.py runserver
```

La aplicación estará disponible en `http://127.0.0.1:8000/`

## 📁 Estructura del Proyecto

```
Frozz/
├── accounts/          # App de autenticación y perfiles
├── store/             # App de e-commerce
├── rentals/           # App de alquileres
├── frozz/             # Configuración del proyecto
├── templates/         # Plantillas HTML
├── static/            # Archivos estáticos (CSS, JS, imágenes)
├── media/             # Archivos de medios (imágenes subidas)
├── manage.py
├── requirements.txt
└── README.md
```

## 🎨 Diseño

- **Framework CSS:** Bootstrap 5
- **Paleta de colores:** Azul y blanco (tema hielo/granizado)
- **Responsive:** Optimizado para móvil, tablet y desktop
- **Iconos:** Bootstrap Icons

## 🔑 Funcionalidades por Rol

### Cliente
- Ver catálogo de productos
- Agregar productos al carrito
- Realizar pedidos
- Reservar alquileres
- Ver historial de pedidos y alquileres
- Gestionar perfil

### Administrador
- Acceso al panel de administración Django
- Gestionar productos y categorías
- Gestionar pedidos y estados
- Gestionar alquileres
- Ver métricas y estadísticas

## 📡 API REST

Los endpoints de la API están disponibles en `/api/`:

- `GET /api/categories/` - Listar categorías
- `GET /api/products/` - Listar productos (con filtros: ?category=slug&type=sale&search=query)
- `GET /api/orders/` - Listar pedidos del usuario autenticado
- `GET /api/cart/my_cart/` - Obtener carrito del usuario
- `POST /api/cart/add_item/` - Agregar item al carrito

## 🗄️ Modelos Principales

- **Category:** Categorías de productos
- **Product:** Productos (venta, alquiler, insumos, desechables)
- **Order:** Pedidos de compra
- **OrderItem:** Items de pedido
- **Cart:** Carrito de compras
- **CartItem:** Items del carrito
- **Rental:** Alquileres de máquinas
- **RentalAvailability:** Disponibilidad de alquileres
- **UserProfile:** Perfil extendido del usuario

## 🔐 Seguridad

- Autenticación segura con Django
- Validación de formularios
- Protección CSRF
- Variables de entorno para configuración sensible
- Validación de stock antes de checkout

## 🚧 Próximas Mejoras (Opcional)

- [ ] Integración de pagos (Stripe/MercadoPago)
- [ ] Notificaciones por email
- [ ] Integración con WhatsApp
- [ ] Soporte multiidioma (ES/EN)
- [ ] Dashboard con gráficos y métricas avanzadas
- [ ] Sistema de reseñas y calificaciones
- [ ] Cupones y descuentos

## 📝 Notas

- Las imágenes de productos se almacenan en `media/products/`
- Las imágenes de categorías se almacenan en `media/categories/`
- Los avatares de usuario se almacenan en `media/avatars/`

## 👨‍💻 Desarrollo

Para desarrollo local, asegúrate de tener:
- PostgreSQL corriendo
- Variables de entorno configuradas
- Migraciones aplicadas
- Superusuario creado

## 📄 Licencia

Este proyecto es privado y propiedad de Frozz.

---

Desarrollado con ❄️ usando Django 5.0

