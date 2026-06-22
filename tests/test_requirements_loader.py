from thesis_rest_tester.loaders.requirements_loader import RequirementsLoader


def test_source_requirements_preserve_xlsx_identity_and_structure() -> None:
    rows = [
        {
            "Issue-id": "PT27",
            "Type": "User Story",
            "Business Value": 945,
            "Description": (
                "As a citizen\nI want to confirm my registration\n"
                "So that my account becomes valid."
            ),
            "Comments (check also system textual description)": "Code is valid for 30 minutes.",
        }
    ]

    requirements = RequirementsLoader._source_requirements(rows)

    assert len(requirements) == 1
    assert requirements[0].id == "PT27"
    assert requirements[0].role == "citizen"
    assert requirements[0].business_value == 945
    assert requirements[0].constraints == ["Code is valid for 30 minutes."]
    assert requirements[0].expected_behaviors == ["my account becomes valid"]
