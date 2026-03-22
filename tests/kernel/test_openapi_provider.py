"""Tests for terrarium.kernel.openapi_provider -- OpenAPI spec parsing."""

import pytest
from terrarium.kernel.openapi_provider import OpenAPIProvider


SIMPLE_OPENAPI_YAML = """\
openapi: "3.0.3"
info:
  title: Pet Store
  version: "1.0.0"
paths:
  /pets:
    get:
      operationId: list_pets
      summary: List all pets
      parameters:
        - name: limit
          in: query
          schema:
            type: integer
      responses:
        "200":
          description: A list of pets
          content:
            application/json:
              schema:
                type: array
                items:
                  type: object
                  properties:
                    id:
                      type: string
                    name:
                      type: string
    post:
      operationId: create_pet
      summary: Create a pet
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                name:
                  type: string
                species:
                  type: string
      responses:
        "201":
          description: Pet created
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
  /pets/{petId}:
    get:
      operationId: get_pet
      summary: Get a pet by ID
      parameters:
        - name: petId
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: A single pet
          content:
            application/json:
              schema:
                type: object
                properties:
                  id:
                    type: string
                  name:
                    type: string
"""


async def test_parse_simple_spec(tmp_path):
    """Parsing a simple OpenAPI YAML spec extracts operations."""
    spec_file = tmp_path / "petstore.yaml"
    spec_file.write_text(SIMPLE_OPENAPI_YAML)

    provider = OpenAPIProvider(spec_dir=str(tmp_path))
    result = await provider.fetch("petstore")

    assert result is not None
    assert result["source"] == "openapi"
    assert result["service"] == "petstore"
    assert result["title"] == "Pet Store"
    ops = result["operations"]
    assert len(ops) == 3
    op_names = {op["name"] for op in ops}
    assert op_names == {"list_pets", "create_pet", "get_pet"}


async def test_parse_parameters(tmp_path):
    """Parameters (query, path, body) are extracted from operations."""
    spec_file = tmp_path / "petstore.yaml"
    spec_file.write_text(SIMPLE_OPENAPI_YAML)

    provider = OpenAPIProvider(spec_dir=str(tmp_path))
    result = await provider.fetch("petstore")
    ops_by_name = {op["name"]: op for op in result["operations"]}

    # list_pets has a query param 'limit'
    list_op = ops_by_name["list_pets"]
    assert "limit" in list_op["parameters"]

    # get_pet has a path param 'petId'
    get_op = ops_by_name["get_pet"]
    assert "petId" in get_op["parameters"]

    # create_pet has body properties
    create_op = ops_by_name["create_pet"]
    assert "name" in create_op["parameters"]
    assert "species" in create_op["parameters"]


async def test_parse_response(tmp_path):
    """200/201 response schemas are extracted from operations."""
    spec_file = tmp_path / "petstore.yaml"
    spec_file.write_text(SIMPLE_OPENAPI_YAML)

    provider = OpenAPIProvider(spec_dir=str(tmp_path))
    result = await provider.fetch("petstore")
    ops_by_name = {op["name"]: op for op in result["operations"]}

    # list_pets 200 response
    list_op = ops_by_name["list_pets"]
    assert list_op["response_schema"]["type"] == "array"

    # create_pet 201 response
    create_op = ops_by_name["create_pet"]
    assert create_op["response_schema"]["type"] == "object"

    # get_pet 200 response
    get_op = ops_by_name["get_pet"]
    assert get_op["response_schema"]["type"] == "object"


async def test_supports_local(tmp_path):
    """supports() returns True when a YAML spec file exists in spec_dir."""
    spec_file = tmp_path / "stripe.yaml"
    spec_file.write_text("openapi: '3.0.0'\ninfo:\n  title: Stripe\n  version: '1.0'\npaths: {}\n")

    provider = OpenAPIProvider(spec_dir=str(tmp_path))
    assert await provider.supports("stripe") is True
    assert await provider.supports("nonexistent") is False


async def test_missing_returns_none(tmp_path):
    """Unknown service with no spec file returns None."""
    provider = OpenAPIProvider(spec_dir=str(tmp_path))
    result = await provider.fetch("nonexistent_service")
    assert result is None
