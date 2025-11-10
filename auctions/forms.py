from django import forms
from .models import Item, Category, Bid, Review, ShippingLocation
from decimal import Decimal

class SellItemForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=Category.objects.all(),
        required=False,
        empty_label="Select Category (Optional)",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    duration_minutes = forms.IntegerField(
        min_value=10,
        help_text="How long the auction should run (minutes)",
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': ''})
    )
    
    seller_city = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'seller-city'}),
        help_text="Select your city for shipping calculation"
    )
    
    seller_area = forms.ChoiceField(
        required=False,
        widget=forms.Select(attrs={'class': 'form-control', 'id': 'seller-area'}),
        help_text="Select your area"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        cities = ShippingLocation.objects.values_list('city', flat=True).distinct().order_by('city')
        self.fields['seller_city'].choices = [('', 'Select City')] + [(city, city) for city in cities]
        
        if self.data.get('seller_city'):
            areas = ShippingLocation.objects.filter(
                city=self.data.get('seller_city')
            ).values_list('area', flat=True).order_by('area')
            self.fields['seller_area'].choices = [('', 'Select Area')] + [(area, area) for area in areas]
        elif self.instance and self.instance.pk and self.instance.seller_city:
            areas = ShippingLocation.objects.filter(
                city=self.instance.seller_city
            ).values_list('area', flat=True).order_by('area')
            self.fields['seller_area'].choices = [('', 'Select Area')] + [(area, area) for area in areas]
        else:
            self.fields['seller_area'].choices = [('', 'Select City First')]
    
    def clean_starting_price(self):
        price = self.cleaned_data.get('starting_price')
        if price is not None and price <= 0:
            raise forms.ValidationError('Starting price must be greater than zero.')
        return price
    
    def clean_min_increment(self):
        increment = self.cleaned_data.get('min_increment')
        if increment is not None and increment <= 0:
            raise forms.ValidationError('Minimum increment must be greater than zero.')
        return increment
    
    def clean_buy_now_price(self):
        buy_now = self.cleaned_data.get('buy_now_price')
        starting_price = self.cleaned_data.get('starting_price')
        
        if buy_now is not None:
            if buy_now <= 0:
                raise forms.ValidationError('Buy Now price must be greater than zero.')
            if starting_price and buy_now < starting_price:
                raise forms.ValidationError('Buy Now price must be higher than starting price.')
        
        return buy_now
    
    class Meta:
        model = Item
        fields = ['title', 'description', 'starting_price', 'min_increment', 'buy_now_price', 'category', 'main_image',
                  'seller_city', 'seller_area', 'free_shipping', 'pickup_available', 'shipping_cost_base']
        widgets = {
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '',
                'id': 'item-title'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 8,
                'placeholder': 'Describe your item in detail...',
                'id': 'item-description'
            }),
            'starting_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '',
                'id': 'item-price'
            }),
            'min_increment': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '',
                'id': 'item-increment'
            }),
            'buy_now_price': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '2000000 (Optional - Leave blank to disable)',
                'id': 'buy-now-price'
            }),
            'main_image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'id': 'item-image'
            }),
            'free_shipping': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'free-shipping'
            }),
            'pickup_available': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'id': 'pickup-available'
            }),
            'shipping_cost_base': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': '15000',
                'id': 'shipping-cost',
                'min': '0'
            }),
        }
        labels = {
            'title': 'Title:',
            'description': 'Description:',
            'starting_price': 'Starting price:',
            'min_increment': 'Min increment:',
            'buy_now_price': 'Buy Now price (Optional):',
            'main_image': 'Photos:',
            'seller_city': 'Your City:',
            'seller_area': 'Your Area:',
            'free_shipping': 'Offer Free Shipping',
            'pickup_available': 'Allow Pickup from Store',
            'shipping_cost_base': 'Base Shipping Cost (UGX):',
        }
        help_texts = {
            'buy_now_price': 'Allow buyers to purchase immediately at this price. Hidden after first valid bid.',
        }

class PlaceBidForm(forms.ModelForm):
    class Meta:
        model = Bid
        fields = ['amount']
        widgets = {
            'amount': forms.NumberInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Enter your bid amount',
                'step': '1000',
                'min': '0',
            }),
        }
        labels = {
            'amount': 'Your Bid (UGX)',
        }
    
    def __init__(self, *args, item=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.item = item
        if item:
            min_bid = item.current_price + item.min_increment
            self.fields['amount'].widget.attrs['min'] = str(min_bid)
            self.fields['amount'].widget.attrs['placeholder'] = f'Minimum: UGX {min_bid:,.0f}'
    
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if not self.item:
            raise forms.ValidationError('Item not found.')
        
        if amount <= self.item.current_price:
            raise forms.ValidationError(
                f'Your bid must be higher than the current price of UGX {self.item.current_price:,.0f}'
            )
        
        min_bid = self.item.current_price + self.item.min_increment
        if amount < min_bid:
            raise forms.ValidationError(
                f'Your bid must be at least UGX {min_bid:,.0f} (current price + minimum increment)'
            )
        
        return amount

class ReviewForm(forms.ModelForm):
    rating = forms.ChoiceField(
        choices=[(i, f'{i} Star{"s" if i > 1 else ""}') for i in range(1, 6)],
        widget=forms.RadioSelect(attrs={'class': 'rating-radio'}),
        label='Your Rating'
    )
    
    class Meta:
        model = Review
        fields = ['rating', 'comment', 'review_image']
        widgets = {
            'comment': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Share your experience with this seller...',
            }),
            'review_image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
            }),
        }
        labels = {
            'comment': 'Your Review',
            'review_image': 'Add a Photo (Optional)',
        }
    
    def clean_comment(self):
        comment = self.cleaned_data.get('comment')
        if len(comment) < 10:
            raise forms.ValidationError('Please write at least 10 characters.')
        return comment
