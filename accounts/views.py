from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.shortcuts import redirect, render

from .forms import UserCreateForm


def signupaccount(request):
    if request.method == 'GET':
        return render(request, 'signupaccount.html', {'form': UserCreateForm})

    if request.POST['password1'] != request.POST['password2']:
        return render(request, 'signupaccount.html', {'form': UserCreateForm, 'error': 'Passwords do not match'})
    try:
        user = User.objects.create_user(request.POST['username'], password=request.POST['password1'])
        user.save()
        login(request, user)
        return redirect('home')
    except IntegrityError:
        return render(request, 'signupaccount.html', {
            'form': UserCreateForm,
            'error': 'Username already taken. Choose new username.',
        })


def loginaccount(request):
    if request.method == 'GET':
        return render(request, 'loginaccount.html', {'form': AuthenticationForm})

    user = authenticate(request, username=request.POST['username'], password=request.POST['password'])
    if user is None:
        return render(request, 'loginaccount.html', {
            'form': AuthenticationForm(),
            'error': 'username and password do not match',
        })
    login(request, user)
    return redirect(request.GET.get('next') or 'home')


@login_required
def logoutaccount(request):
    logout(request)
    return redirect('home')
