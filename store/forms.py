from django import forms
from django.contrib.auth.models import User
from decimal import Decimal
from .models import (
    Product, Category, ProductImage, ProductVariation,
    ProductVariationImage, ProductTechnicalSpec, ProductAttribute,
    DilutionBaseProduct,
    SiteSettings,
    PaymentMethod,
    FinanceRecord,
    Quotation,
    DrinzzContractConfig,
)
from accounts.forms import CustomUserCreationForm


PHONE_INDICATIVO = '+57'


class ClientCreateForm(CustomUserCreationForm):
    """Formulario mínimo para crear cliente: usuario, correo, nombre, teléfono, tipo, dirección."""
    phone = forms.CharField(
        max_length=25,
        required=True,
        label='Teléfono',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '300 123 4567',
            'inputmode': 'tel',
        }),
    )

    def clean_phone(self):
        value = (self.cleaned_data.get('phone') or '').strip()
        if not value:
            return value
        # Siempre guardar con indicativo delante
        if not value.startswith('+'):
            value = f'{PHONE_INDICATIVO} {value}'
        return value
    client_type = forms.ChoiceField(
        choices=[
            ('natural', 'Persona natural'),
            ('empresa', 'Empresa'),
        ],
        required=True,
        label='Tipo de cliente',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    departamento = forms.CharField(
        required=True,
        label='Departamento',
        widget=forms.Select(
            choices=[('', '-- Seleccione departamento --')],
            attrs={'class': 'form-select', 'id': 'client_departamento'}
        ),
    )
    city = forms.CharField(
        required=True,
        label='Ciudad',
        widget=forms.Select(
            choices=[('', '-- Primero seleccione departamento --')],
            attrs={'class': 'form-select', 'id': 'client_city'}
        ),
    )
    address = forms.CharField(
        required=True,
        label='Dirección exacta',
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Calle, número, barrio, adicional',
        }),
    )

    class Meta(CustomUserCreationForm.Meta):
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Usuario'
        self.fields['email'].label = 'Correo'
        self.fields['first_name'].label = 'Nombre'
        self.fields['last_name'].label = 'Apellido'
        for field in self.fields.values():
            if 'class' not in field.widget.attrs:
                field.widget.attrs.setdefault('class', 'form-control')

    def save(self, commit=True):
        user = super().save(commit=commit)
        if commit and hasattr(user, 'profile'):
            user.profile.phone = self.cleaned_data.get('phone', '')
            user.profile.client_type = self.cleaned_data.get('client_type', 'natural')
            user.profile.departamento = self.cleaned_data.get('departamento', '')
            user.profile.city = self.cleaned_data.get('city', '')
            user.profile.address = self.cleaned_data.get('address', '')
            user.profile.save()
        return user


class ClientEditForm(forms.Form):
    """Formulario para editar cliente (sin contraseña)."""
    email = forms.EmailField(required=True, label='Correo', widget=forms.EmailInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(max_length=30, required=False, label='Nombre', widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=30, required=False, label='Apellido', widget=forms.TextInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(
        max_length=25,
        required=True,
        label='Teléfono',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '300 123 4567', 'inputmode': 'tel'}),
    )
    client_type = forms.ChoiceField(
        choices=[('natural', 'Persona natural'), ('empresa', 'Empresa')],
        required=True,
        label='Tipo de cliente',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    departamento = forms.CharField(
        required=True,
        label='Departamento',
        widget=forms.Select(
            choices=[('', '-- Seleccione departamento --')],
            attrs={'class': 'form-select', 'id': 'client_departamento'}
        ),
    )
    city = forms.CharField(
        required=True,
        label='Ciudad',
        widget=forms.Select(
            choices=[('', '-- Primero seleccione departamento --')],
            attrs={'class': 'form-select', 'id': 'client_city'}
        ),
    )
    address = forms.CharField(
        required=True,
        label='Dirección exacta',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Calle, número, barrio, ciudad'}),
    )

    def clean_phone(self):
        value = (self.cleaned_data.get('phone') or '').strip()
        if value and not value.startswith('+'):
            value = f'{PHONE_INDICATIVO} {value}'
        return value


class GuestCheckoutForm(forms.Form):
    """Datos de contacto para checkout como invitado (no crea usuario)."""
    full_name = forms.CharField(
        max_length=200,
        required=True,
        label='Nombre completo',
        widget=forms.TextInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'Nombre y apellidos / Razón social'}),
    )
    email = forms.EmailField(
        required=True,
        label='Correo electrónico',
        widget=forms.EmailInput(attrs={'class': 'form-control form-control-sm', 'placeholder': 'correo@ejemplo.com'}),
    )
    client_type = forms.ChoiceField(
        choices=[('natural', 'Persona natural'), ('empresa', 'Empresa')],
        required=True,
        label='Tipo de cliente',
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )
    departamento = forms.CharField(
        required=True,
        label='Departamento',
        widget=forms.Select(
            choices=[('', '-- Seleccione departamento --')],
            attrs={'class': 'form-select form-select-sm', 'id': 'guest_departamento'}
        ),
    )
    city = forms.CharField(
        required=True,
        label='Ciudad',
        widget=forms.Select(
            choices=[('', '-- Primero seleccione departamento --')],
            attrs={'class': 'form-select form-select-sm', 'id': 'guest_city'}
        ),
    )
    address = forms.CharField(
        required=True,
        label='Dirección exacta',
        widget=forms.Textarea(attrs={
            'class': 'form-control form-control-sm',
            'rows': 2,
            'placeholder': 'Calle, número, barrio, adicional',
        }),
    )
    # Coordenadas seleccionadas en el mapa (opcionales)
    map_lat = forms.CharField(required=False, widget=forms.HiddenInput())
    map_lng = forms.CharField(required=False, widget=forms.HiddenInput())
    punto_referencia = forms.CharField(
        max_length=255,
        required=False,
        label='Punto de referencia',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Ej: Frente al parque, diagonal a la panadería (opcional)',
        }),
    )
    phone = forms.CharField(
        max_length=25,
        required=True,
        label='Teléfono (WhatsApp)',
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Ej: 300 123 4567 (con WhatsApp habilitado)',
            'inputmode': 'tel',
        }),
    )

    def clean_phone(self):
        value = (self.cleaned_data.get('phone') or '').strip()
        if value and not value.startswith('+'):
            value = f'{PHONE_INDICATIVO} {value}'
        return value


class ProductForm(forms.ModelForm):
    """Form for creating and editing products"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo venta y alquiler (tipos legacy se muestran si el producto ya los tiene)
        choices = [('sale', 'Venta'), ('rental', 'Alquiler')]
        current = getattr(self.instance, 'product_type', None)
        if current and current not in ('sale', 'rental'):
            choices.append((current, self.instance.get_product_type_display()))
        self.fields['product_type'].choices = choices

    class Meta:
        model = Product
        fields = [
            'name', 'slug', 'description', 'category', 'product_type',
            'purchase_cost', 'price', 'promotional_price',
            'stock', 'available', 'image', 'keywords', 'accent_color',
            'unit_price_enabled', 'unit_quantity', 'unit_measure',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Se genera automáticamente del nombre'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'product_type': forms.Select(attrs={'class': 'form-select', 'id': 'id_product_type'}),
            'purchase_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'promotional_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Opcional'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'keywords': forms.TextInput(attrs={'class': 'form-control'}),
            'accent_color': forms.TextInput(attrs={
                'class': 'form-control form-control-color',
                'type': 'color',
                'title': 'Elige un color de diseño',
            }),
            'unit_price_enabled': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'id_unit_price_enabled',
            }),
            'unit_quantity': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0.001',
                'placeholder': 'Ej: 5',
            }),
            'unit_measure': forms.Select(attrs={'class': 'form-select'}),
        }
        labels = {
            'name': 'Nombre del Producto',
            'slug': 'URL (Slug)',
            'description': 'Descripción',
            'category': 'Categoría',
            'product_type': 'Tipo de Producto',
            'purchase_cost': 'Costo de Compra',
            'price': 'Precio de Venta',
            'promotional_price': 'Precio Promocional',
            'stock': 'Stock',
            'available': 'Disponible',
            'image': 'Imagen Principal',
            'keywords': 'Palabras Clave',
            'accent_color': 'Color de diseño',
            'unit_price_enabled': 'Precio unitario',
            'unit_quantity': 'Unidades totales',
            'unit_measure': 'Medida',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['price'].required = False
        self.fields['promotional_price'].required = False
        self.fields['purchase_cost'].required = False
        self.fields['accent_color'].required = False
        self.fields['slug'].required = False
        self.fields['unit_quantity'].required = False
        self.fields['unit_measure'].required = False
        self.fields['unit_price_enabled'].required = False
        # El input type=color no acepta vacío; usar un default visual
        if not (self.instance and self.instance.pk and self.instance.accent_color):
            self.fields['accent_color'].initial = '#0F6FFF'

    def clean_slug(self):
        from django.utils.text import slugify
        slug = (self.cleaned_data.get('slug') or '').strip()
        name = (self.data.get('name') or '').strip()
        if not slug and name:
            slug = slugify(name) or 'producto'
        if not slug:
            return ''
        qs = Product.objects.filter(slug=slug)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            base = slug
            counter = 2
            while True:
                candidate = f'{base}-{counter}'
                conflict = Product.objects.filter(slug=candidate)
                if self.instance and self.instance.pk:
                    conflict = conflict.exclude(pk=self.instance.pk)
                if not conflict.exists():
                    slug = candidate
                    break
                counter += 1
        return slug

    def clean_accent_color(self):
        import re
        clear = self.data.get('accent_color_clear') == 'on'
        if clear:
            return ''
        value = (self.cleaned_data.get('accent_color') or self.data.get('accent_color') or '').strip()
        if not value:
            return ''
        if not re.fullmatch(r'#[0-9A-Fa-f]{6}', value):
            raise forms.ValidationError('Usa un color hex válido, por ejemplo #0F6FFF.')
        return value.upper()

    def clean_purchase_cost(self):
        value = self.cleaned_data.get('purchase_cost')
        if value in (None, ''):
            return Decimal('0.00')
        return value

    def clean_price(self):
        value = self.cleaned_data.get('price')
        if value in (None, ''):
            return None
        return value

    def clean_promotional_price(self):
        value = self.cleaned_data.get('promotional_price')
        if value in (None, ''):
            return None
        return value

    def clean_unit_quantity(self):
        value = self.cleaned_data.get('unit_quantity')
        if value in (None, ''):
            return None
        return value

    def clean(self):
        cleaned_data = super().clean()
        product_type = cleaned_data.get('product_type')
        if product_type == 'rental':
            cleaned_data['purchase_cost'] = Decimal('0.00')
            cleaned_data['promotional_price'] = None
            if not cleaned_data.get('price'):
                cleaned_data['price'] = Decimal('0.01')
        elif not cleaned_data.get('price'):
            self.add_error('price', 'El precio de venta es obligatorio para este tipo de producto.')

        enabled = cleaned_data.get('unit_price_enabled')
        unit_quantity = cleaned_data.get('unit_quantity')
        unit_measure = cleaned_data.get('unit_measure') or 'l'
        if enabled:
            if not unit_quantity or unit_quantity <= 0:
                self.add_error('unit_quantity', 'Ingresa las unidades totales o desactiva Precio unitario.')
            cleaned_data['unit_measure'] = unit_measure
        else:
            cleaned_data['unit_quantity'] = None
            cleaned_data['unit_measure'] = unit_measure or 'l'
        return cleaned_data


class ProductImageForm(forms.ModelForm):
    """Form for product images"""
    
    class Meta:
        model = ProductImage
        fields = ['image', 'alt_text']
        widgets = {
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'alt_text': forms.TextInput(attrs={'class': 'form-control'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'image': 'Imagen',
            'alt_text': 'Texto Alternativo',
            'is_primary': 'Imagen Principal',
        }


class ProductVariationForm(forms.ModelForm):
    """Form for product variations"""
    
    class Meta:
        model = ProductVariation
        fields = ['variation_type', 'name', 'value', 'price_modifier', 'stock', 'available', 'sku', 'image']
        widgets = {
            'variation_type': forms.Select(attrs={'class': 'form-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'value': forms.TextInput(attrs={'class': 'form-control'}),
            'price_modifier': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sku': forms.TextInput(attrs={'class': 'form-control'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'variation_type': 'Tipo de Variación',
            'name': 'Nombre',
            'value': 'Valor',
            'price_modifier': 'Modificador de Precio',
            'stock': 'Stock',
            'available': 'Disponible',
            'sku': 'SKU',
            'image': 'Imagen',
        }


class ProductVariationImageForm(forms.ModelForm):
    """Form for product variation images"""
    
    class Meta:
        model = ProductVariationImage
        fields = ['image', 'alt_text', 'is_primary']
        widgets = {
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'alt_text': forms.TextInput(attrs={'class': 'form-control'}),
            'is_primary': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'image': 'Imagen',
            'alt_text': 'Texto Alternativo',
            'is_primary': 'Imagen Principal',
        }


class ProductTechnicalSpecForm(forms.ModelForm):
    """Form for technical specifications"""
    
    class Meta:
        model = ProductTechnicalSpec
        fields = ['name', 'description', 'order']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'order': forms.NumberInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'name': 'Nombre',
            'description': 'Descripción',
            'order': 'Orden',
        }


class ProductAttributeForm(forms.ModelForm):
    """Form for product attributes"""
    
    class Meta:
        model = ProductAttribute
        fields = ['key', 'value', 'order']
        widgets = {
            'key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Garantía, Tamaño, Peso, etc.'}),
            'value': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: 12 meses, Grande, 500g, etc.'}),
            'order': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
        labels = {
            'key': 'Atributo',
            'value': 'Valor',
            'order': 'Orden',
        }


class CategoryForm(forms.ModelForm):
    """Form for categories"""
    
    class Meta:
        model = Category
        fields = ['name', 'description', 'image']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'name': 'Nombre',
            'description': 'Descripción',
            'image': 'Imagen',
        }


class QuotationForm(forms.Form):
    """Form for quotation request"""
    existing_client = forms.ModelChoiceField(
        queryset=User.objects.filter(is_staff=False).order_by('first_name', 'last_name', 'username'),
        required=False,
        label='Cliente existente',
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    unregistered_client = forms.BooleanField(
        required=False,
        label='Cliente no registrado',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    client_kind = forms.ChoiceField(
        choices=[
            ('natural', 'Persona natural'),
            ('empresa', 'Empresa'),
        ],
        required=False,
        label='Tipo de cliente',
        widget=forms.RadioSelect()
    )
    client_name = forms.CharField(
        max_length=200,
        label='Nombre del Cliente',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    client_email = forms.EmailField(
        label='Email del Cliente',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control'})
    )
    client_phone = forms.CharField(
        max_length=20,
        label='Teléfono',
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    client_departamento = forms.CharField(
        max_length=100,
        label='Departamento',
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'quotation_departamento'})
    )
    client_city = forms.CharField(
        max_length=100,
        label='Ciudad',
        required=False,
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'quotation_city'})
    )
    notes = forms.CharField(
        label='Notas adicionales',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Información adicional sobre la cotización...'})
    )


class DilutionBaseProductForm(forms.ModelForm):
    """Formulario admin para productos base de la calculadora de agua."""

    class Meta:
        model = DilutionBaseProduct
        fields = ('name', 'slug', 'description', 'water_ml_per_base_ml', 'is_active', 'sort_order')
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Concentrado de granizado'}),
            'slug': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'base-granizado (opcional, se genera solo)',
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Instrucciones opcionales para el usuario',
            }),
            'water_ml_per_base_ml': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.001',
                'min': '0',
                'placeholder': 'Ej: 4',
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': '0'}),
        }
        labels = {
            'name': 'Nombre del producto base',
            'slug': 'Enlace para compartir (# en la URL)',
            'description': 'Descripción / instrucciones',
            'water_ml_per_base_ml': 'ML de agua por 1 ML de base',
            'is_active': 'Visible en la calculadora',
            'sort_order': 'Orden de aparición',
        }
        help_texts = {
            'slug': 'Opcional. Si lo dejas vacío se crea desde el nombre. Ej: base-granizado',
            'water_ml_per_base_ml': 'Proporción 1:4 → escribe 4. Por cada 1 ml de producto base se agregan 4 ml de agua.',
        }


class SiteSettingsForm(forms.ModelForm):
    """Formulario para editar contacto, redes y banner del sitio."""

    class Meta:
        model = SiteSettings
        fields = (
            'contact_email',
            'contact_phone',
            'whatsapp_number',
            'wa_n8n_enabled',
            'wa_n8n_webhook_url',
            'wa_n8n_phone',
            'address_city',
            'address_country',
            'company_legal_name',
            'company_nit',
            'company_matricula',
            'company_address',
            'company_department',
            'company_rep_name',
            'jurisdiction_city',
            'instagram_url',
            'tiktok_url',
            'facebook_url',
        )
        widgets = {
            'contact_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'contact_phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '3128104046'}),
            'whatsapp_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '573128104046'}),
            'wa_n8n_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'wa_n8n_webhook_url': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://n8n.kodeuniverse.com/webhook/...',
            }),
            'wa_n8n_phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '573001112233 o Group ID',
            }),
            'address_city': forms.TextInput(attrs={'class': 'form-control'}),
            'address_country': forms.TextInput(attrs={'class': 'form-control'}),
            'company_legal_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'MIXLAB SAS'}),
            'company_nit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '902031074-1'}),
            'company_matricula': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '10006865'}),
            'company_address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Barrio Ciudad Bicentenario, Conjunto Residencial Parques de Bolívar 2',
            }),
            'company_department': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bolívar'}),
            'company_rep_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del representante'}),
            'jurisdiction_city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cartagena'}),
            'instagram_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://instagram.com/...'}),
            'tiktok_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://tiktok.com/@...'}),
            'facebook_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://facebook.com/...'}),
        }
        labels = {
            'contact_email': 'Correo de contacto',
            'contact_phone': 'Teléfono (como se muestra en el sitio)',
            'whatsapp_number': 'Número de WhatsApp (botón del sitio)',
            'wa_n8n_enabled': 'Activar notificaciones WhatsApp (n8n)',
            'wa_n8n_webhook_url': 'Webhook n8n',
            'wa_n8n_phone': 'Teléfono o Group ID destino',
            'address_city': 'Ciudad',
            'address_country': 'País',
            'company_legal_name': 'Razón social (arrendador)',
            'company_nit': 'NIT del arrendador',
            'company_matricula': 'Matrícula mercantil',
            'company_address': 'Dirección del arrendador',
            'company_department': 'Departamento',
            'company_rep_name': 'Representante legal',
            'jurisdiction_city': 'Ciudad de jurisdicción',
            'instagram_url': 'Instagram',
            'tiktok_url': 'TikTok',
            'facebook_url': 'Facebook (opcional)',
        }
        help_texts = {
            'whatsapp_number': 'Solo dígitos con código de país, sin + ni espacios. Ej: 573045379501',
            'wa_n8n_phone': 'Este valor se envía como body.phone al webhook n8n.',
            'wa_n8n_webhook_url': 'Usa la URL de producción (/webhook/...), no /webhook-test/.',
        }


class PaymentMethodForm(forms.ModelForm):
    """Formulario para un método de pago (banco / cuenta)."""

    class Meta:
        model = PaymentMethod
        fields = (
            'account_type',
            'bank_name',
            'bank_logo',
            'holder_name',
            'document_type',
            'document_number',
            'account_number',
            'breb_key',
            'is_active',
            'sort_order',
        )
        widgets = {
            'account_type': forms.Select(attrs={'class': 'form-select'}),
            'bank_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Bancolombia S.A.'}),
            'bank_logo': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'holder_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre del titular'}),
            'document_type': forms.Select(attrs={'class': 'form-select'}),
            'document_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1143397396'}),
            'account_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '912-097121-60'}),
            'breb_key': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Opcional'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'sort_order': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }
        labels = {
            'account_type': 'Tipo de cuenta',
            'bank_name': 'Banco / entidad',
            'bank_logo': 'Logo del banco',
            'holder_name': 'A nombre de',
            'document_type': 'Tipo documento',
            'document_number': 'NIT o C.C.',
            'account_number': 'Número de cuenta',
            'breb_key': 'Llave BREB',
            'is_active': 'Activo',
            'sort_order': 'Orden',
        }


class FinanceRecordForm(forms.ModelForm):
    """Formulario para registrar gastos y pagos."""

    class Meta:
        model = FinanceRecord
        fields = (
            'record_type',
            'amount',
            'description',
            'category',
            'recorded_at',
            'related_quotation',
            'receipt',
            'notes',
        )
        widgets = {
            'record_type': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej: Compra de insumos / Abono cliente'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'recorded_at': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'related_quotation': forms.Select(attrs={'class': 'form-select'}),
            'receipt': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }
        labels = {
            'record_type': 'Tipo',
            'amount': 'Monto (COP)',
            'description': 'Descripción',
            'category': 'Categoría',
            'recorded_at': 'Fecha',
            'related_quotation': 'Cotización relacionada (opcional)',
            'receipt': 'Comprobante / foto',
            'notes': 'Notas',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Quotation.objects.order_by('-id')
        self.fields['related_quotation'].queryset = qs
        self.fields['related_quotation'].required = False
        self.fields['related_quotation'].empty_label = '— Sin cotización —'


STAFF_ROLE_CHOICES = [
    ('vendedor', 'Vendedor'),
    ('admin', 'Administrador'),
]


class StaffUserCreateForm(CustomUserCreationForm):
    """Crear usuario del equipo: Vendedor o Administrador."""
    role = forms.ChoiceField(
        choices=STAFF_ROLE_CHOICES,
        required=True,
        label='Rol',
        widget=forms.Select(attrs={'class': 'form-select'}),
        help_text='Vendedor: acceso al panel Manager. Administrador: acceso total (superusuario).',
    )
    phone = forms.CharField(
        max_length=25,
        required=False,
        label='Teléfono',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '300 123 4567',
            'inputmode': 'tel',
        }),
    )
    avatar = forms.ImageField(
        required=False,
        label='Foto de perfil',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
    )

    class Meta(CustomUserCreationForm.Meta):
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        self.allow_admin_role = kwargs.pop('allow_admin_role', False)
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Usuario'
        self.fields['email'].label = 'Correo'
        self.fields['email'].required = True
        self.fields['first_name'].label = 'Nombre'
        self.fields['first_name'].required = True
        self.fields['last_name'].label = 'Apellido'
        if not self.allow_admin_role:
            self.fields['role'].choices = [('vendedor', 'Vendedor')]
        for name, field in self.fields.items():
            if name in ('role',):
                continue
            field.widget.attrs.setdefault('class', 'form-control')

    def clean_role(self):
        role = self.cleaned_data.get('role') or 'vendedor'
        if role == 'admin' and not self.allow_admin_role:
            raise forms.ValidationError('Solo un administrador puede crear otros administradores.')
        return role

    def clean_phone(self):
        value = (self.cleaned_data.get('phone') or '').strip()
        if value and not value.startswith('+'):
            value = f'{PHONE_INDICATIVO} {value}'
        return value

    def save(self, commit=True):
        user = super().save(commit=False)
        role = self.cleaned_data.get('role') or 'vendedor'
        user.is_staff = True
        user.is_superuser = (role == 'admin')
        user.is_active = True
        if commit:
            user.save()
            profile = getattr(user, 'profile', None)
            if profile is None:
                from accounts.models import UserProfile
                profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.phone = self.cleaned_data.get('phone', '') or ''
            avatar = self.cleaned_data.get('avatar')
            if avatar:
                profile.avatar = avatar
            profile.save()
        return user


class StaffUserEditForm(forms.Form):
    """Editar usuario del equipo, rol, foto y estado."""
    email = forms.EmailField(required=True, label='Correo', widget=forms.EmailInput(attrs={'class': 'form-control'}))
    first_name = forms.CharField(max_length=30, required=True, label='Nombre', widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=30, required=False, label='Apellido', widget=forms.TextInput(attrs={'class': 'form-control'}))
    phone = forms.CharField(
        max_length=25,
        required=False,
        label='Teléfono',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '300 123 4567', 'inputmode': 'tel'}),
    )
    role = forms.ChoiceField(
        choices=STAFF_ROLE_CHOICES,
        required=True,
        label='Rol',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    is_active = forms.BooleanField(
        required=False,
        label='Cuenta activa',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    avatar = forms.ImageField(
        required=False,
        label='Foto de perfil',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/*'}),
    )
    clear_avatar = forms.BooleanField(
        required=False,
        label='Quitar foto actual',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    new_password = forms.CharField(
        required=False,
        label='Nueva contraseña (opcional)',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'autocomplete': 'new-password'}),
        help_text='Déjalo vacío para no cambiar la contraseña.',
    )

    def __init__(self, *args, **kwargs):
        self.allow_admin_role = kwargs.pop('allow_admin_role', False)
        super().__init__(*args, **kwargs)
        if not self.allow_admin_role:
            self.fields['role'].choices = [('vendedor', 'Vendedor')]

    def clean_phone(self):
        value = (self.cleaned_data.get('phone') or '').strip()
        if value and not value.startswith('+'):
            value = f'{PHONE_INDICATIVO} {value}'
        return value

    def clean_role(self):
        role = self.cleaned_data.get('role') or 'vendedor'
        if role == 'admin' and not self.allow_admin_role:
            raise forms.ValidationError('Solo un administrador puede asignar rol Admin.')
        return role


class CompanyNameForm(forms.Form):
    """Edición rápida del nombre de la empresa."""
    company_legal_name = forms.CharField(
        max_length=200,
        required=True,
        label='Nombre de la empresa (razón social)',
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'MIXLAB SAS',
        }),
    )


class DrinzzContractConfigForm(forms.ModelForm):
    """Edición del contrato marco Drinzz (admin)."""

    class Meta:
        model = DrinzzContractConfig
        fields = (
            'operator_brand',
            'operator_legal_name',
            'operator_nit',
            'operator_address',
            'operator_city',
            'operator_rep_name',
            'associate_pct_month1',
            'operator_pct_month1',
            'associate_pct',
            'operator_pct',
            'billing_threshold',
            'maintain_bonus_pct',
            'expenses_assumed',
            'provides_operators',
            'estimated_income_min',
            'estimated_income_max',
            'contract_duration_months',
            'renewal_auto',
            'termination_notice_days',
            'settlement_days',
            'jurisdiction_city',
            'object_clause',
            'associate_obligations',
            'operator_obligations',
            'transparency_clause',
            'additional_clauses',
            'disclaimer_income',
            'version_label',
            'is_published',
        )
        widgets = {
            'operator_brand': forms.TextInput(attrs={'class': 'form-control'}),
            'operator_legal_name': forms.TextInput(attrs={'class': 'form-control'}),
            'operator_nit': forms.TextInput(attrs={'class': 'form-control'}),
            'operator_address': forms.TextInput(attrs={'class': 'form-control'}),
            'operator_city': forms.TextInput(attrs={'class': 'form-control'}),
            'operator_rep_name': forms.TextInput(attrs={'class': 'form-control'}),
            'associate_pct_month1': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'operator_pct_month1': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'associate_pct': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'operator_pct': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'billing_threshold': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'maintain_bonus_pct': forms.NumberInput(attrs={'class': 'form-control', 'min': 0, 'max': 100}),
            'expenses_assumed': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'provides_operators': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'estimated_income_min': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'estimated_income_max': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'contract_duration_months': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'renewal_auto': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'termination_notice_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'settlement_days': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'jurisdiction_city': forms.TextInput(attrs={'class': 'form-control'}),
            'object_clause': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'associate_obligations': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
            'operator_obligations': forms.Textarea(attrs={'class': 'form-control', 'rows': 6}),
            'transparency_clause': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'additional_clauses': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'disclaimer_income': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'version_label': forms.TextInput(attrs={'class': 'form-control'}),
            'is_published': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        a = cleaned.get('associate_pct')
        o = cleaned.get('operator_pct')
        if a is not None and o is not None and (a + o) != 100:
            self.add_error('operator_pct', 'La suma del reparto por meta debe ser 100%.')
        a1 = cleaned.get('associate_pct_month1')
        o1 = cleaned.get('operator_pct_month1')
        if a1 is not None and o1 is not None and (a1 + o1) != 100:
            self.add_error('operator_pct_month1', 'La suma del reparto del primer mes debe ser 100%.')
        return cleaned
