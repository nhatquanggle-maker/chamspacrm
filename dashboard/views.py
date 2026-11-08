from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required


@login_required
def admin_dashboard(request):
    """Bảng điều khiển Quản trị viên Cham Spa (Figma 772:2)"""
    tab = request.GET.get('tab')
    if tab == 'customers':
        return redirect('accounts:admin_customer_list')
    if tab == 'staff':
        return redirect('accounts:admin_staff_list')
    return render(request, 'layouts/admin_layout.html')


@login_required
def staff_dashboard(request):
    """Bảng điều khiển Kỹ thuật viên / Ca trực Cham Spa (Figma 760:751)"""
    return render(request, 'layouts/staff_layout.html')
