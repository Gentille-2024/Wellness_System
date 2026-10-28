from django.shortcuts import render


def forbidden(request, exception=None):
    message = str(exception) if exception and str(exception) else "You don't have permission to open this page."
    return render(request, "403.html", {"message": message}, status=403)
