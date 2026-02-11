from rest_framework import serializers
from .models import Category, Product, ProductImage, Order, OrderItem, Cart, CartItem


class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = ['id', 'image', 'alt_text']


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'slug', 'description', 'image']


class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    
    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 'category', 
            'product_type', 'price', 'stock', 'available', 
            'image', 'images', 'created_at'
        ]


class OrderItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    subtotal = serializers.ReadOnlyField()
    
    class Meta:
        model = OrderItem
        fields = ['id', 'product', 'quantity', 'price', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    user = serializers.StringRelatedField(read_only=True)
    
    class Meta:
        model = Order
        fields = [
            'id', 'user', 'status', 'total', 'shipping_address',
            'shipping_city', 'shipping_phone', 'shipping_notes',
            'created_at', 'updated_at', 'paid_at', 'delivered_at', 'items'
        ]
        read_only_fields = ['total', 'created_at', 'updated_at']


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    subtotal = serializers.ReadOnlyField()
    
    class Meta:
        model = CartItem
        fields = ['id', 'product', 'quantity', 'subtotal', 'created_at']


class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True)
    total = serializers.ReadOnlyField()
    item_count = serializers.ReadOnlyField()
    
    class Meta:
        model = Cart
        fields = ['id', 'items', 'total', 'item_count', 'created_at', 'updated_at']

