from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from .models import UserProfile

class UserRegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)
    phone_number = forms.CharField(max_length=20, required=False)
    mobile_money_provider = forms.ChoiceField(
        choices=[('', 'Select Provider'), ('mtn', 'MTN Mobile Money'), ('airtel', 'Airtel Money')],
        required=False
    )
    
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs.update({'class': 'form-control'})

class UserLoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Username'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Password'}))

class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['phone_number', 'address', 'city', 'country', 'bio', 'profile_picture', 'mobile_money_number', 'mobile_money_provider', 'hide_phone_number']
        widgets = {
            'bio': forms.Textarea(attrs={'rows': 4, 'class': 'form-control', 'placeholder': 'Tell us about yourself...'}),
            'address': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'hide_phone_number': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'hide_phone_number': 'Hide phone number from my public profile',
        }
        help_texts = {
            'hide_phone_number': 'When enabled, your phone number will only be visible to you.',
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            if field != 'profile_picture' and field != 'hide_phone_number':
                self.fields[field].widget.attrs.update({'class': 'form-control'})

class SellerApplicationForm(forms.ModelForm):
    business_name = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your business name'})
    )
    business_type = forms.ChoiceField(
        choices=UserProfile._meta.get_field('business_type').choices,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    national_id_number = forms.CharField(
        max_length=50,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your National ID number'})
    )
    national_id_front = forms.ImageField(
        required=True,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'})
    )
    national_id_back = forms.ImageField(
        required=True,
        widget=forms.FileInput(attrs={'class': 'form-control', 'accept': 'image/*'})
    )
    phone_number = forms.CharField(
        max_length=20,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+256 XXX XXX XXX'})
    )
    bank_account_name = forms.CharField(
        max_length=200,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Account holder name'})
    )
    bank_account_number = forms.CharField(
        max_length=100,
        required=True,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Your bank account number'})
    )
    bank_name = forms.ChoiceField(
        choices=UserProfile._meta.get_field('bank_name').choices,
        required=True,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    years_of_experience = forms.IntegerField(
        min_value=0,
        required=True,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'Years of selling experience', 'min': 0})
    )
    business_description = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Tell us about your business, what you sell, your target market, etc.'})
    )
    product_categories = forms.CharField(
        required=True,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'What categories of products will you sell? (e.g., Electronics, Fashion, Home & Garden)'})
    )
    
    class Meta:
        model = UserProfile
        fields = [
            'business_name',
            'business_type',
            'business_registration_number',
            'national_id_number',
            'national_id_front',
            'national_id_back',
            'phone_number',
            'bank_account_name',
            'bank_account_number',
            'bank_name',
            'years_of_experience',
            'business_description',
            'product_categories',
        ]
        
        widgets = {
            'business_registration_number': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Registration number (if applicable)'
            }),
        }
        
        labels = {
            'business_name': 'Business Name',
            'business_type': 'Business Type',
            'business_registration_number': 'Business Registration Number',
            'national_id_number': 'National ID Number',
            'national_id_front': 'National ID (Front Photo)',
            'national_id_back': 'National ID (Back Photo)',
            'phone_number': 'Phone Number',
            'bank_account_name': 'Bank Account Name',
            'bank_account_number': 'Bank Account Number',
            'bank_name': 'Bank',
            'years_of_experience': 'Years of Experience',
            'business_description': 'Business Description',
            'product_categories': 'Product Categories',
        }
        
        help_texts = {
            'national_id_front': 'Upload a clear photo of the front of your National ID card',
            'national_id_back': 'Upload a clear photo of the back of your National ID card',
        }
