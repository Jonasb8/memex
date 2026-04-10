"""Unit tests for structural detection and extractor interfaces."""
import pytest
from memex.structural import (
    categorize_file,
    is_structural_change,
    build_changed_files_section,
)
from memex.extractor import is_low_signal, build_prompt


# ---------------------------------------------------------------------------
# categorize_file
# ---------------------------------------------------------------------------

class TestCategorizeFile:
    def test_alembic_migration(self):
        assert categorize_file("alembic/versions/001_add_users.py") == "migration"

    def test_generic_migrations_dir(self):
        assert categorize_file("migrations/0001_initial.py") == "migration"

    def test_nested_migrations_dir(self):
        assert categorize_file("app/migrations/0002_add_column.py") == "migration"

    def test_rails_migration_naming(self):
        assert categorize_file("db/migrate/20240101120000_create_users.rb") == "migration"

    def test_terraform_file(self):
        assert categorize_file("infra/main.tf") == "infra"

    def test_terraform_in_root(self):
        assert categorize_file("main.tf") == "infra"

    def test_k8s_yaml(self):
        assert categorize_file("k8s/deployment.yaml") == "infra"

    def test_kubernetes_dir(self):
        assert categorize_file("kubernetes/service.yml") == "infra"

    def test_helm_values(self):
        assert categorize_file("helm/values.yaml") == "infra"

    def test_charts_dir(self):
        assert categorize_file("charts/myapp/templates/ingress.yaml") == "infra"

    def test_openapi_yaml(self):
        assert categorize_file("openapi.yaml") == "schema"

    def test_openapi_json(self):
        assert categorize_file("api/openapi.json") == "schema"

    def test_swagger_yaml(self):
        assert categorize_file("swagger.yaml") == "schema"

    def test_schema_json(self):
        assert categorize_file("schema.json") == "schema"

    def test_graphql_schema(self):
        assert categorize_file("schema.graphql") == "schema"

    def test_graphql_file(self):
        assert categorize_file("api/queries.graphql") == "schema"

    def test_proto_file(self):
        assert categorize_file("api/service.proto") == "schema"

    def test_dockerfile(self):
        assert categorize_file("Dockerfile") == "deployment"

    def test_dockerfile_variant(self):
        assert categorize_file("Dockerfile.prod") == "deployment"

    def test_docker_compose(self):
        assert categorize_file("docker-compose.yml") == "deployment"

    def test_docker_compose_prod(self):
        assert categorize_file("docker-compose.prod.yml") == "deployment"

    def test_regular_python_file(self):
        assert categorize_file("src/app/models.py") is None

    def test_test_file(self):
        assert categorize_file("tests/test_auth.py") is None

    def test_readme(self):
        assert categorize_file("README.md") is None

    def test_plain_yaml_in_root_not_infra(self):
        # Raw .yaml without an infra directory prefix must NOT match
        assert categorize_file("config.yaml") is None

    def test_plain_yml_in_root_not_infra(self):
        assert categorize_file("renovate.yml") is None

    def test_case_insensitive_migration(self):
        assert categorize_file("Migrations/001_init.py") == "migration"

    def test_case_insensitive_terraform(self):
        assert categorize_file("Terraform/main.tf") == "infra"


# ---------------------------------------------------------------------------
# is_structural_change
# ---------------------------------------------------------------------------

class TestIsStructuralChange:
    def test_empty_list_is_false(self):
        assert not is_structural_change([])

    def test_migration_file_is_structural(self):
        assert is_structural_change(["migrations/001_add_sessions.py", "app/models.py"])

    def test_terraform_is_structural(self):
        assert is_structural_change(["terraform/main.tf", "README.md"])

    def test_schema_only_is_structural(self):
        assert is_structural_change(["openapi.yaml"])

    def test_deployment_file_is_structural(self):
        assert is_structural_change(["Dockerfile", "src/app.py"])

    def test_regular_files_not_structural(self):
        assert not is_structural_change(["src/auth.py", "tests/test_auth.py", "README.md"])

    def test_plain_yaml_not_structural(self):
        assert not is_structural_change(["config.yaml", "src/app.py"])

    def test_mixed_structural_and_regular(self):
        # One structural file is enough
        assert is_structural_change(["src/app.py", "migrations/001.py", "tests/test_app.py"])


# ---------------------------------------------------------------------------
# is_low_signal — with changed_files
# ---------------------------------------------------------------------------

class TestIsLowSignalWithFiles:
    def test_backward_compatible_no_changed_files(self):
        # Existing callers pass no changed_files — must still work
        assert is_low_signal("chore: update readme", "")

    def test_structural_files_override_title_filter(self):
        # "chore: add sessions table" + empty body → normally low-signal by title
        # but the migration file should rescue it
        assert not is_low_signal(
            "chore: add sessions table",
            "",
            changed_files=["migrations/001_add_sessions.py"],
        )

    def test_dep_bump_always_low_signal_even_with_structural_files(self):
        # Always-low pattern wins — alembic migration doesn't rescue a dep-bump title
        assert is_low_signal(
            "bump alembic from 1.0 to 2.0",
            "",
            changed_files=["alembic/versions/migration.py"],
        )

    def test_structural_files_with_good_body_already_not_low_signal(self):
        # Long body already passes — structural override is redundant but harmless
        assert not is_low_signal(
            "chore: schema migration",
            "A" * 100,
            changed_files=None,
        )

    def test_no_structural_files_low_signal_title_applies(self):
        # Without structural files, the existing heuristic filters still work
        assert is_low_signal("chore: tidy up imports", "", changed_files=["src/utils.py"])

    def test_infra_files_override_low_signal(self):
        assert not is_low_signal(
            "fix: update terraform config",
            "",
            changed_files=["terraform/main.tf"],
        )

    def test_dockerfile_overrides_low_signal(self):
        assert not is_low_signal(
            "ci: update dockerfile",
            "",
            changed_files=["Dockerfile"],
        )


# ---------------------------------------------------------------------------
# build_changed_files_section
# ---------------------------------------------------------------------------

class TestBuildChangedFilesSection:
    def test_none_returns_no_file_list(self):
        section = build_changed_files_section(None)
        assert "No file list available" in section

    def test_empty_list_returns_no_file_list(self):
        section = build_changed_files_section([])
        assert "No file list available" in section

    def test_migration_files_listed(self):
        section = build_changed_files_section(["migrations/001_add_sessions.py"])
        assert "migrations/001_add_sessions.py" in section
        assert "Database migrations" in section

    def test_infra_files_listed(self):
        section = build_changed_files_section(["terraform/main.tf"])
        assert "terraform/main.tf" in section
        assert "Infrastructure / IaC" in section

    def test_schema_files_listed(self):
        section = build_changed_files_section(["openapi.yaml"])
        assert "openapi.yaml" in section
        assert "API / Schema definitions" in section

    def test_non_structural_summarized_not_listed(self):
        files = [f"src/module_{i}.py" for i in range(5)]
        section = build_changed_files_section(files)
        # Individual paths should NOT appear
        for f in files:
            assert f not in section
        assert "5" in section  # count is shown

    def test_mixed_structural_and_regular(self):
        files = ["migrations/001.py", "src/app.py", "src/models.py"]
        section = build_changed_files_section(files)
        assert "migrations/001.py" in section
        assert "Database migrations" in section
        assert "2" in section  # 2 other files summarized


# ---------------------------------------------------------------------------
# build_prompt — changed_files integration
# ---------------------------------------------------------------------------

class TestBuildPromptWithFiles:
    def test_no_changed_files_shows_unavailable(self):
        prompt = build_prompt("Fix bug", "body", [])
        assert "No file list available" in prompt

    def test_migration_files_appear_in_prompt(self):
        prompt = build_prompt(
            "Add sessions table", "", [],
            changed_files=["migrations/001_add_sessions.py"],
        )
        assert "migrations/001_add_sessions.py" in prompt
        assert "Database migrations" in prompt

    def test_structural_instruction_in_prompt(self):
        prompt = build_prompt("Add sessions table", "", [],
                              changed_files=["migrations/001_add_sessions.py"])
        assert "migrations, infrastructure" in prompt

    def test_backward_compatible_no_changed_files_param(self):
        # Old call signature: build_prompt(title, body, comments)
        prompt = build_prompt("Fix bug", "body", ["a review comment"])
        assert "a review comment" in prompt
        assert "No file list available" in prompt
