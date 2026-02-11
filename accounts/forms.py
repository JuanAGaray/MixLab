from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import UserProfile, ShippingAddress

# DPA Colombia: 32 departamentos + Bogotá D.C. (orden alfabético para listas)
DEPARTAMENTOS_COLOMBIA = [
    ('', '-- Seleccione departamento --'),
    ('Amazonas', 'Amazonas'),
    ('Antioquia', 'Antioquia'),
    ('Arauca', 'Arauca'),
    ('Atlántico', 'Atlántico'),
    ('Bogotá D.C.', 'Bogotá D.C.'),
    ('Bolívar', 'Bolívar'),
    ('Boyacá', 'Boyacá'),
    ('Caldas', 'Caldas'),
    ('Caquetá', 'Caquetá'),
    ('Casanare', 'Casanare'),
    ('Cauca', 'Cauca'),
    ('Cesar', 'Cesar'),
    ('Chocó', 'Chocó'),
    ('Córdoba', 'Córdoba'),
    ('Cundinamarca', 'Cundinamarca'),
    ('Guainía', 'Guainía'),
    ('Guaviare', 'Guaviare'),
    ('Huila', 'Huila'),
    ('La Guajira', 'La Guajira'),
    ('Magdalena', 'Magdalena'),
    ('Meta', 'Meta'),
    ('Nariño', 'Nariño'),
    ('Norte de Santander', 'Norte de Santander'),
    ('Putumayo', 'Putumayo'),
    ('Quindío', 'Quindío'),
    ('Risaralda', 'Risaralda'),
    ('San Andrés y Providencia', 'San Andrés y Providencia'),
    ('Santander', 'Santander'),
    ('Sucre', 'Sucre'),
    ('Tolima', 'Tolima'),
    ('Valle del Cauca', 'Valle del Cauca'),
    ('Vaupés', 'Vaupés'),
    ('Vichada', 'Vichada'),
]


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, label='Correo electrónico')
    first_name = forms.CharField(max_length=30, required=False, label='Nombre')
    last_name = forms.CharField(max_length=30, required=False, label='Apellido')

    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'password1', 'password2')

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        if commit:
            user.save()
        return user


class ShippingAddressForm(forms.ModelForm):
    """Form to add a new shipping address (DPA Colombia: departamento, ciudad, dirección exacta, referencia, Google Maps)"""
    departamento = forms.ChoiceField(
        choices=DEPARTAMENTOS_COLOMBIA,
        required=True,
        label='Departamento',
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'id_departamento_address'}),
    )
    city = forms.CharField(
        required=True,
        label='Ciudad',
        widget=forms.Select(choices=[('', '-- Primero seleccione departamento --')], attrs={'class': 'form-control', 'id': 'id_city_address'}),
    )

    class Meta:
        model = ShippingAddress
        fields = [
            'departamento',
            'city',
            'address',
            'punto_referencia',
            'google_maps_ubicacion',
            'phone',
        ]
        widgets = {
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Dirección exacta: calle, carrera, número, barrio',
            }),
            'punto_referencia': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: Frente al parque, diagonal a la panadería',
            }),
            'google_maps_ubicacion': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'Pega el enlace de compartir de Google Maps (se abrirá en la app o en maps.google.com)',
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Teléfono de contacto',
            }),
        }
        labels = {
            'address': 'Dirección exacta',
            'punto_referencia': 'Punto de referencia',
            'google_maps_ubicacion': 'Ubicación en Google Maps',
            'phone': 'Teléfono',
        }
        help_texts = {
            'punto_referencia': 'Opcional. Ej: frente al parque, diagonal a la panadería.',
            'google_maps_ubicacion': 'Opcional. El enlace se abrirá en la aplicación Google Maps o en maps.google.com.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Si hay instancia con ciudad, el widget Select se rellenará por JS según departamento
        if self.instance and self.instance.pk and self.instance.city:
            self.fields['city'].widget.choices = [('', '-- Seleccione ciudad --'), (self.instance.city, self.instance.city)]


class UserProfileForm(forms.ModelForm):
    """Simplified profile form - only phone and default shipping address"""
    new_phone = forms.CharField(
        max_length=20,
        required=False,
        label='Nuevo Teléfono',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Agregar nuevo teléfono'})
    )

    class Meta:
        model = UserProfile
        fields = ['default_shipping_address']
        widgets = {
            'default_shipping_address': forms.Select(attrs={'class': 'form-control'}),
        }
        labels = {
            'default_shipping_address': 'Dirección de Envío Predeterminada',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            # Only show shipping addresses for this user
            self.fields['default_shipping_address'].queryset = ShippingAddress.objects.filter(user=user)
            self.fields['default_shipping_address'].empty_label = 'Selecciona una dirección'
