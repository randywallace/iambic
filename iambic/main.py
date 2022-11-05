import asyncio
import pathlib
import warnings

import click

from iambic.config.models import Config
from iambic.core import noq_json as json
from iambic.core.context import ctx
from iambic.core.git import clone_git_repos
from iambic.core.logger import log
from iambic.core.models import TemplateChangeDetails
from iambic.core.utils import gather_templates
from iambic.request_handler.apply import apply_changes, flag_expired_resources
from iambic.request_handler.detect import detect_changes
from iambic.request_handler.generate import generate_templates
from iambic.request_handler.git_apply import apply_git_changes
from iambic.request_handler.git_plan import plan_git_changes

warnings.filterwarnings("ignore", category=FutureWarning, module="botocore.client")


def output_proposed_changes(template_changes: list[TemplateChangeDetails]):
    if template_changes:
        file_name = "proposed_changes.json"
        log.info(f"A detailed summary of descriptions was saved to {file_name}")

        with open(file_name, "w") as f:
            f.write(
                json.dumps(
                    [template_change.dict() for template_change in template_changes],
                    indent=2,
                )
            )


@click.group()
def cli():
    ...


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
@click.option(
    "--template",
    "-t",
    "templates",
    required=False,
    multiple=True,
    type=click.Path(exists=True),
    help="The template file path(s) to apply. Example: ./aws/roles/engineering.yaml",
)
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def plan(config_path: str, templates: list[str], repo_dir: str):
    run_plan(config_path, templates, repo_dir)


def run_plan(config_path: str, templates: list[str], repo_dir: str):
    if not templates:
        templates = asyncio.run(gather_templates(repo_dir or str(pathlib.Path.cwd())))

    asyncio.run(flag_expired_resources(templates))

    config = Config.load(config_path)
    config.set_account_defaults()
    ctx.eval_only = True
    output_proposed_changes(asyncio.run(apply_changes(config, templates, ctx)))


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
def detect(config_path: str):
    run_detect(config_path)


def run_detect(config_path: str):
    config = Config.load(config_path)
    config.set_account_defaults()
    asyncio.run(detect_changes(config))


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
@click.option(
    "--repo_base_path",
    "-d",
    "repo_base_path",
    required=True,
    type=click.Path(exists=True),
    help="The repo base directory that should contain the templates. Example: ~/iambic/templates",
)
def clone_repos(config_path: str, repo_base_path: str):
    run_clone_repos(config_path, repo_base_path)


def run_clone_repos(config_path: str, repo_base_path: str):
    config = Config.load(config_path)
    config.set_account_defaults()
    asyncio.run(clone_git_repos(config, repo_base_path))


@cli.command()
@click.option(
    "--force",
    "-f",
    is_flag=True,
    show_default=True,
    help="Apply changes without asking for permission?",
)
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
@click.option(
    "--template",
    "-t",
    "templates",
    required=False,
    multiple=True,
    type=click.Path(exists=True),
    help="The template file path(s) to apply. Example: ./aws/roles/engineering.yaml",
)
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def apply(force: bool, config_path: str, templates: list[str], repo_dir: str):
    run_apply(force, config_path, templates, repo_dir)


def run_apply(force: bool, config_path: str, templates: list[str], repo_dir: str):
    if not templates:
        templates = asyncio.run(gather_templates(repo_dir or str(pathlib.Path.cwd())))

    config = Config.load(config_path)
    config.set_account_defaults()
    ctx.eval_only = not force
    template_changes = asyncio.run(apply_changes(config, templates, ctx))
    output_proposed_changes(template_changes)

    if ctx.eval_only and template_changes and click.confirm("Proceed?"):
        ctx.eval_only = False
        asyncio.run(apply_changes(config, templates, ctx))
    asyncio.run(detect_changes(config))


@cli.command(name="git-apply")
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def git_apply(config_path: str, repo_dir: str):
    run_git_apply(config_path, repo_dir)


def run_git_apply(config_path: str, repo_dir: str):
    template_changes = asyncio.run(
        apply_git_changes(config_path, repo_dir or str(pathlib.Path.cwd()))
    )
    output_proposed_changes(template_changes)


@cli.command()
@click.option(
    "--config",
    "-c",
    "config_path",
    type=click.Path(exists=True),
    help="The config.yaml file path to apply. Example: ./prod/config.yaml",
)
@click.option(
    "--template",
    "-t",
    "templates",
    required=False,
    multiple=True,
    type=click.Path(exists=True),
    help="The template file path(s) to apply. Example: ./aws/roles/engineering.yaml",
)
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def git_plan(config_path: str, templates: list[str], repo_dir: str):
    run_git_plan(config_path, templates, repo_dir)


def run_git_plan(config_path: str, templates: list[str], repo_dir: str):
    template_changes = asyncio.run(
        plan_git_changes(config_path, repo_dir or str(pathlib.Path.cwd()))
    )
    output_proposed_changes(template_changes)


@cli.command(name="import")
@click.option(
    "--config",
    "-c",
    "config_paths",
    multiple=True,
    type=click.Path(exists=True),
    help="The config.yaml file paths. Example: ./prod/config.yaml",
)
@click.option(
    "--repo-dir",
    "-d",
    "repo_dir",
    required=False,
    type=click.Path(exists=True),
    help="The repo directory containing the templates. Example: ~/noq-templates",
)
def import_(config_paths: list[str], repo_dir: str):
    run_import(config_paths, repo_dir or str(pathlib.Path.cwd()))


def run_import(config_paths: list[str], repo_dir: str):
    configs = []
    for config_path in config_paths:
        config = Config.load(config_path)
        config.set_account_defaults()
        configs.append(config)
    asyncio.run(generate_templates(configs, repo_dir or str(pathlib.Path.cwd())))


if __name__ == "__main__":
    cli()
