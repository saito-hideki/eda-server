#  Copyright 2024 Red Hat, Inc.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.

import logging

from django.shortcuts import get_object_or_404
from django_filters import rest_framework as defaultfilters
from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
)
from rest_framework import mixins, status, viewsets
from rest_framework.filters import BaseFilterBackend
from rest_framework.response import Response

from aap_eda.api import exceptions, filters, serializers
from aap_eda.api.serializers.eda_credential import get_references
from aap_eda.core import models
from aap_eda.core.enums import ResourceType
from aap_eda.core.utils.credentials import inputs_to_store

from .mixins import (
    CreateModelMixin,
    PartialUpdateOnlyModelMixin,
    ResponseSerializerMixin,
)

logger = logging.getLogger(__name__)


class KindFilterBackend(BaseFilterBackend):
    def filter_queryset(self, request, queryset, _view):
        kinds = request.GET.getlist("credential_type__kind")
        if bool(kinds):
            return queryset.filter(credential_type__kind__in=kinds)
        return queryset


class EdaCredentialViewSet(
    ResponseSerializerMixin,
    CreateModelMixin,
    PartialUpdateOnlyModelMixin,
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    queryset = models.EdaCredential.objects.all()
    serializer_class = serializers.EdaCredentialSerializer
    filter_backends = (
        KindFilterBackend,
        defaultfilters.DjangoFilterBackend,
    )
    filterset_class = filters.EdaCredentialFilter
    ordering_fields = ["name"]

    rbac_resource_type = ResourceType.EDA_CREDENTIAL
    rbac_action = None

    @extend_schema(
        description="Get EDA credential by id",
        parameters=[
            OpenApiParameter(
                "refs",
                required=False,
                enum=["true", "false"],
                description=(
                    "Query resources that have reference to the credential"
                    " by its id"
                ),
            ),
        ],
        responses={
            status.HTTP_200_OK: OpenApiResponse(
                serializers.EdaCredentialSerializer,
                description="Return an EDA credential by id.",
            ),
        },
    )
    def retrieve(self, request, pk):
        eda_credential = get_object_or_404(models.EdaCredential, id=pk)
        eda_credential_serializers = serializers.EdaCredentialSerializer(
            eda_credential
        )

        refs = request.query_params.get("refs", "false").lower() == "true"
        eda_credential_serializers.references = (
            get_references(eda_credential) if refs else None
        )

        return Response(eda_credential_serializers.data)

    @extend_schema(
        description="Create a new EDA credential.",
        request=serializers.EdaCredentialCreateSerializer,
        responses={
            status.HTTP_201_CREATED: OpenApiResponse(
                serializers.EdaCredentialSerializer,
                description="Return the new EDA credential.",
            ),
        },
    )
    def create(self, request):
        serializer = serializers.EdaCredentialCreateSerializer(
            data=request.data
        )

        serializer.is_valid(raise_exception=True)
        serializer.validated_data["inputs"] = inputs_to_store(
            serializer.validated_data["inputs"]
        )
        eda_credential = serializer.create(serializer.validated_data)

        return Response(
            serializers.EdaCredentialSerializer(eda_credential).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        description="List all EDA credentials",
        parameters=[
            OpenApiParameter(
                "credential_type__kind",
                type=str,
                description="Kind of CredentialType",
            ),
        ],
        responses={
            status.HTTP_200_OK: OpenApiResponse(
                serializers.EdaCredentialSerializer(many=True),
                description="Return a list of EDA credentials.",
            ),
        },
    )
    def list(self, request):
        credentials = models.EdaCredential.objects.exclude(
            managed=True,
        )
        credentials = self.filter_queryset(credentials)

        serializer = serializers.EdaCredentialSerializer(
            credentials, many=True
        )
        result = self.paginate_queryset(serializer.data)

        return self.get_paginated_response(result)

    @extend_schema(
        description="Partial update of an EDA credential",
        request=serializers.EdaCredentialCreateSerializer,
        responses={
            status.HTTP_200_OK: OpenApiResponse(
                serializers.EdaCredentialSerializer,
                description=(
                    "Update successful. Return an updated EDA credential."
                ),
            )
        },
    )
    def partial_update(self, request, pk):
        eda_credential = self.get_object()
        serializer = serializers.EdaCredentialCreateSerializer(
            eda_credential, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)

        if serializer.validated_data.get("inputs"):
            serializer.validated_data["inputs"] = inputs_to_store(
                serializer.validated_data["inputs"],
                eda_credential.inputs,
            )

        for key, value in serializer.validated_data.items():
            setattr(eda_credential, key, value)

        eda_credential.save()

        return Response(
            serializers.EdaCredentialSerializer(eda_credential).data
        )

    @extend_schema(
        description="Delete an eda credential by id",
        responses={
            status.HTTP_204_NO_CONTENT: OpenApiResponse(
                None, description="Delete successful."
            )
        },
        parameters=[
            OpenApiParameter(
                name="force",
                description="Force deletion if there are dependent objects",
                required=False,
                type=bool,
            )
        ],
    )
    def destroy(self, request, *args, **kwargs):
        force = request.query_params.get("force", "false").lower() in [
            "true",
            "1",
            "yes",
        ]
        eda_credential = self.get_object()
        if eda_credential.managed:
            error = "Managed EDA credential cannot be deleted"
            return Response(
                {"errors": error}, status=status.HTTP_400_BAD_REQUEST
            )

        references = get_references(eda_credential)

        if bool(references) and not force:
            raise exceptions.Conflict(
                f"Credential {eda_credential.name} is being referenced by "
                "other resources and cannot be deleted. If you want to force "
                "delete, please add /?force=true query param."
            )
        self.perform_destroy(eda_credential)
        return Response(status=status.HTTP_204_NO_CONTENT)
