import re

from django.shortcuts import render
from django.http import HttpResponse
from django.core.urlresolvers import reverse
from django.forms import CharField, HiddenInput
from django.template import TemplateDoesNotExist

from utils import generate_form, get_content_type, get_format, parse_http_accept_header
from serializers import serializers
from inflector import pluralize

class Views(object):
    model = None
    template_path = ''
    supported_formats = ['html']
    form = None

    def index(self, request):
        """Render a list of objects."""
        objects = self.model.objects.all()

        return self._render(
            request = request,
            template = 'index',
            context = {
                pluralize(self.model.__name__).lower(): objects,
            },
            status = 200
        )

    def show(self, request, id):
        """Render a single object."""
        try:
            object = self.model.objects.get(id=id)
        except self.model.DoesNotExist:
            return render(
                request = request,
                template_name = '404.html',
                status = 404
            )

        return self._render(
            request = request,
            template = 'show',
            context = {
                self.model.__name__.lower(): object
            },
            status = 200
        )

    def new(self, request):
        """Render a form to create a new object."""
        form = (self.form or generate_form(self.model))()

        return self._render(
            request = request,
            template = 'new',
            context = {
                'form': form
            },
            status = 200
        )

    def create(self, request):
        """Create a new object."""    
        form = (self.form or generate_form(self.model))(request.POST)

        if form.is_valid():
            object = form.save()

            response = HttpResponse(status=303)
            response['Location'] = reverse(
                viewname = '%s_%s' % (self.model._meta.app_label, self.model.__name__.lower()),
                args = [object.id]
            )
            return response
        else:
            return self._render(
                request = request,
                template = 'new',
                context = {
                    'form': form
                },
                status = 400
            )

    def edit(self, request, id):
        """Render a form to edit an object."""
        try:
            object = self.model.objects.get(id=id)
        except self.model.DoesNotExist:
            return render(
                request = request,
                template_name = '404.html',
                status = 404
            )

        form = (self.form or generate_form(self.model))(instance=object)

        # Add "_method" field to override request method to PUT
        form.fields['_method'] = CharField(required=True, initial='PUT', widget=HiddenInput)

        return self._render(
            request = request,
            template = 'edit',
            context = {
                self.model.__name__.lower(): object,
                'form': form
            },
            status = 200
        )

    def update(self, request, id):
        """Edit an object."""
        try:
            object = self.model.objects.get(id=id)
        except self.model.DoesNotExist:
            return render(
                request = request,
                template_name = '404.html',
                status = 404
            )

        form = (self.form or generate_form(self.model))(request.PUT, instance=object)

        if form.is_valid():
            object = form.save()

            return self.show(request, id)
        else:
            return self._render(
                request = request,
                template = 'edit',
                context = {
                    'form': form
                },
                status = 400
            )

    def destroy(self, request, id):
        """Delete an object."""
        try:
            object = self.model.objects.get(id=id)
            object.delete()
        except self.model.DoesNotExist:
            return render(
                request = request,
                template_name = '404.html',
                status = 404
            )

        return self._render(
            request = request,
            template = 'destroy',
            status = 200
        )

    def _get_format(self, request):
        """Determine the desired response format."""

        # Determine format from extension...
        if '.' in request.path:
            format = request.path.split('.')[-1]
            if format in self.supported_formats:
                return format

        # ... or if no extension is given, fall back to the HTTP Accept header...
        elif 'HTTP_ACCEPT' in request.META:

            # Derive a list of supported content types from the list of supported formats.
            supported_content_types = []
            for supported_format in self.supported_formats:
                supported_content_types.append(get_content_type(supported_format))

            # Find the highest-ranking content type.
            for accepted_content_type in parse_http_accept_header(request.META['HTTP_ACCEPT']):
                if accepted_content_type in supported_content_types:
                    return get_format(accepted_content_type)

    def _render(self, request, template, status, context={}):
        """Render a response."""

        format = self._get_format(request)

        if not format:
            return HttpResponse(status=406)

        # Render template...
        try:
            return render(
                request = request,
                template_name = '%s%s.%s' % (self.template_path, template, format),
                dictionary = context,
                status = status,
                content_type = get_content_type(format)
            )
        # ... or if no template exists, look for an appropriate serializer.
        except TemplateDoesNotExist:

            if format in serializers:
                return HttpResponse(
                    content = serializers[format](context).serialize(),
                    content_type = get_content_type(format),
                    status = status
                )
            else:
                raise