from pathlib import Path

from thesis_rest_tester.loaders.openapi_loader import OpenAPILoader


def test_openapi_loader_extracts_operations(tmp_path: Path) -> None:
    spec = tmp_path / "openapi.yaml"
    spec.write_text(
        """
openapi: 3.0.3
security:
  - bearerAuth: []
paths:
  /proposals/{proposalId}:
    parameters:
      - in: path
        name: proposalId
        required: true
        schema: {type: integer}
    post:
      operationId: updateProposal
      summary: Update a proposal
      tags: [proposals]
      requestBody:
        content:
          application/json:
            schema:
              type: object
              properties:
                title: {type: string}
      responses:
        "200": {description: Updated}
        "400": {description: Invalid input}
""",
        encoding="utf-8",
    )

    loaded = OpenAPILoader().load(spec)

    assert loaded.raw_document["openapi"] == "3.0.3"
    assert len(loaded.operations) == 1
    operation = loaded.operations[0]
    assert operation.method == "POST"
    assert operation.path == "/proposals/{proposalId}"
    assert operation.operation_id == "updateProposal"
    assert operation.parameters[0]["name"] == "proposalId"
    assert operation.request_body_schema == {
        "type": "object",
        "properties": {"title": {"type": "string"}},
    }
    assert operation.response_codes == ["200", "400"]
    assert operation.tags == ["proposals"]
    assert operation.auth_required is True

