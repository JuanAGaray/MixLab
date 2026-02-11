from django import forms
from django.contrib.auth.models import User
from .models import (
    Product, Category, ProductImage, ProductVariation,
    ProductVariationImage, ProductTechnicalSpec, ProductAttribute
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
    
    class Meta:
        model = Product
        fields = [
            'name', 'slug', 'description', 'category', 'product_type',
            'purchase_cost', 'price', 'promotional_price',
            'stock', 'available', 'image', 'keywords'
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'slug': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Se genera automáticamente del nombre'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'product_type': forms.Select(attrs={'class': 'form-select'}),
            'purchase_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'promotional_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Opcional'}),
            'stock': forms.NumberInput(attrs={'class': 'form-control'}),
            'available': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'image': forms.FileInput(attrs={'class': 'form-control'}),
            'keywords': forms.TextInput(attrs={'class': 'form-control'}),
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
        }


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
