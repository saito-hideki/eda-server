#  Copyright 2023 Red Hat, Inc.
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
import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

from aap_eda.core import models
from aap_eda.services.project import (
    ProjectImportService as _ProjectImportService,
)
from aap_eda.services.project.git import GitRepository

DATA_DIR = Path(__file__).parent / "data"


class ProjectImportService(_ProjectImportService):
    def _temporary_directory(self) -> tempfile.TemporaryDirectory:
        tmp_mock = mock.Mock()
        tmp_mock.name = DATA_DIR / "project-01"
        tmp_mock.__enter__ = mock.Mock(return_value=tmp_mock.name)
        tmp_mock.__exit__ = mock.Mock(return_value=None)
        return tmp_mock


@pytest.mark.django_db
def test_project_import():
    repo_mock = mock.Mock(name="GitRepository()")
    repo_mock.rev_parse.return_value = (
        "adc83b19e793491b1c6ea0fd8b46cd9f32e592fc"
    )

    git_mock = mock.Mock(name="GitRepository", spec=GitRepository)
    git_mock.clone.return_value = repo_mock

    service = ProjectImportService(git_cls=git_mock)
    project = service.run(
        name="test-project-01", url="https://git.example.com/repo.git"
    )

    git_mock.clone.assert_called_once_with(
        "https://git.example.com/repo.git", DATA_DIR / "project-01", depth=1
    )

    assert project is not None
    assert project.id is not None
    assert project.name == "test-project-01"
    assert project.url == "https://git.example.com/repo.git"
    assert project.git_hash == "adc83b19e793491b1c6ea0fd8b46cd9f32e592fc"

    rulebooks = list(project.rulebook_set.order_by("name"))
    assert len(rulebooks) == 2

    with open(DATA_DIR / "project-01-import.json") as fp:
        expected_rulebooks = json.load(fp)

    for rulebook, expected in zip(rulebooks, expected_rulebooks):
        assert_rulebook_is_valid(rulebook, expected)


def assert_rulebook_is_valid(rulebook: models.Rulebook, expected: dict):
    assert rulebook.name == expected["name"]

    rulesets = list(rulebook.ruleset_set.order_by("id"))
    assert len(rulesets) == len(expected["rulesets"])

    for ruleset, expected_rulesets in zip(rulesets, expected["rulesets"]):
        assert_ruleset_is_valid(ruleset, expected_rulesets)


def assert_ruleset_is_valid(ruleset: models.Ruleset, expected: dict):
    assert ruleset.name == expected["name"]

    rules = list(ruleset.rule_set.order_by("id"))
    assert len(rules) == len(expected["rules"])

    for rule, expected_rules in zip(rules, expected["rules"]):
        assert_rule_is_valid(rule, expected_rules)


def assert_rule_is_valid(rule: models.Rule, expected: dict):
    assert rule.name == expected["name"]
    assert rule.action == expected["action"]