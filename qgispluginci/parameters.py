#! python3  # noqa E265

"""
    Parameters management.
"""

# ############################################################################
# ########## Libraries #############
# ##################################

# standard library
import configparser
import datetime
import logging
import os
import re
import sys
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

import toml
import yaml

# 3rd party
from slugify import slugify

from qgispluginci.exceptions import ConfigurationNotFound

# ############################################################################
# ########## Globals #############
# ################################


DASH_WARNING = "Dash in the plugin name is causing issues with QGIS plugin manager"

logger = logging.getLogger(__name__)


# ############################################################################
# ########## Classes #############
# ################################


class Parameters:
    """
    Attributes
    ----------
    plugin_path: str
        The directory of the source code in the repository.
        Defaults to: `slugify(plugin_name)`

    github_organization_slug: str
        The organization slug on SCM host (e.g. Github) and translation platform (e.g. Transifex).
        Not required when running on Travis since deduced from `$TRAVIS_REPO_SLUG`environment variable.

    project_slug: str
        The project slug on SCM host (e.g. Github) and translation platform (e.g. Transifex).
        Not required when running on Travis since deduced from `$TRAVIS_REPO_SLUG`environment variable.

    transifex_coordinator: str
        The username of the coordinator in Transifex.
        Required to create new languages.

    transifex_organization: str
        The organization name in Transifex
        Defaults to: the GitHub organization slug

    transifex_project: str
        The project on Transifex, which can be different from the one on GitHub.
        Defaults to: the project_slug

    transifex_resource: str
        The resource name in transifex
        Defaults to: the project_slug

    translation_source_language:
        The source language for translations.
        Defaults to: 'en'

    translation_languages:
        List of languages.

    changelog_include:
        If the changelog must be added when releasing a version AND if there is a CHANGELOG.md file
        Defaults to True

    changelog_path:
        Path to the CHANGELOG.md relative to the configuration file. Defaults to CHANGELOG.md

    changelog_number_of_entries:
        Number of changelog entries to add in the metdata.txt
        Defaults to 3

    create_date: datetime.date
        The date of creation of the plugin.
        The would be used in the custom repository XML.
        Format: YYYY-MM-DD

    lrelease_path: str
        The path of lrelease executable

    pylupdate5_path: str
        The path of pylupdate executable


    """

    @classmethod
    def make_from(
        cls, *, args: Optional[Any] = None, config_file: Optional[str] = None
    ) -> "Parameters":
        """
        Instantiate from a config file or by exploring the filesystem
        Accepts an argparse Namespace for backward compatibility.
        """
        configuration_not_found = ConfigurationNotFound(
            ".qgis-plugin-ci or setup.cfg or pyproject.toml with a 'qgis-plugin-ci' section have not been found."
        )

        def explore_config() -> Dict[str, Any]:
            if os.path.isfile(".qgis-plugin-ci"):
                # We read the .qgis-plugin-ci file
                with open(".qgis-plugin-ci", encoding="utf8") as f:
                    arg_dict = yaml.safe_load(f)
            elif os.path.isfile("pyproject.toml"):
                # We read the pyproject.toml file
                with open("pyproject.toml", encoding="utf8") as f:
                    arg_dict = toml.load(f)
            else:
                config = configparser.ConfigParser()
                config.read("setup.cfg")
                if "qgis-plugin-ci" in config.sections():
                    # We read the setup.cfg file
                    arg_dict = dict(config.items("qgis-plugin-ci"))
                else:
                    # We don't have either a .qgis-plugin-ci or a setup.cfg
                    if args and args.command == "changelog":
                        # but for the "changelog" sub command, the config file is not required, we can continue
                        arg_dict = dict()
                    else:
                        raise configuration_not_found
            return arg_dict

        def load_config(path_to_file: str) -> Dict[str, Any]:
            if "setup.cfg" in path_to_file:
                config = configparser.ConfigParser()
                config.read(path_to_file)
                return dict(config.items("qgis-plugin-ci"))

            with open(path_to_file) as f:
                if ".qgis-plugin-ci" in path_to_file:
                    return yaml.safe_load(f)
                _, suffix = path_to_file.rsplit(".", 1)
                if suffix == "toml":
                    contents = toml.load(f)
                    return contents["qgis-plugin-ci"]

            raise configuration_not_found

        if config_file:
            config_dict = load_config(config_file)
        else:
            config_dict = explore_config()
        return cls(config_dict)

    def __init__(self, definition: Dict[str, Any]):
        self.plugin_path = definition.get("plugin_path")

        get_metadata = self.collect_metadata()
        self.plugin_name = get_metadata("name")
        self.plugin_slug = slugify(self.plugin_name)
        self.project_slug = definition.get(
            "project_slug",
            os.environ.get("TRAVIS_REPO_SLUG", f".../{self.plugin_slug}").split("/")[1],
        )
        self.github_organization_slug = definition.get(
            "github_organization_slug",
            os.environ.get("TRAVIS_REPO_SLUG", "").split("/")[0],
        )
        self.transifex_coordinator = definition.get("transifex_coordinator", "")
        self.transifex_organization = definition.get(
            "transifex_organization", self.github_organization_slug
        )
        self.translation_source_language = definition.get(
            "translation_source_language", "en"
        )
        self.translation_languages = definition.get("translation_languages", {})
        self.transifex_project = definition.get("transifex_project", self.project_slug)
        self.transifex_resource = definition.get(
            "transifex_resource", self.project_slug
        )
        self.create_date = datetime.datetime.strptime(
            str(definition.get("create_date", datetime.date.today())), "%Y-%m-%d"
        )
        self.lrelease_path = definition.get("lrelease_path", "lrelease")
        self.pylupdate5_path = definition.get("pylupdate5_path", "pylupdate5")
        changelog_include = definition.get("changelog_include", True)
        if isinstance(changelog_include, str):
            self.changelog_include = changelog_include.lower() in [
                "true",
                "1",
                "t",
                "y",
            ]
        else:
            self.changelog_include = changelog_include
        self.changelog_number_of_entries = definition.get(
            "changelog_number_of_entries", 3
        )
        self.changelog_path = definition.get("changelog_path", "CHANGELOG.md")

        # read from metadata
        if not self.plugin_path:
            # This tool can be used outside of a QGIS plugin to read a changelog file
            return

        self.author = get_metadata("author", "")
        self.description = get_metadata("description")
        self.qgis_minimum_version = get_metadata("qgisMinimumVersion")
        self.icon = get_metadata("icon", "")
        self.tags = get_metadata("tags", "")
        self.experimental = get_metadata("experimental", False)
        self.deprecated = get_metadata("deprecated", False)
        self.issue_tracker = get_metadata("tracker")
        self.homepage = get_metadata("homepage", "")
        if self.homepage == "":
            logger.warning(
                "Homepage is not given in the metadata. "
                "It is a mandatory information to publish "
                "the plugin on the QGIS official repository."
            )
        self.repository_url = get_metadata("repository")

    @staticmethod
    def archive_name(
        plugin_name, release_version: str, experimental: bool = False
    ) -> str:
        """
        Returns the archive file name
        """
        # zipname: use dot before version number
        # and not dash since it's causing issues #22
        if "-" in plugin_name:
            logger.warning(DASH_WARNING)

        experimental = "-experimental" if experimental else ""
        return f"{plugin_name}{experimental}.{release_version}.zip"

    def collect_metadata(self) -> Callable[[str, Optional[Any]], Any]:
        """
        Returns a closure capturing a Dict of metadata, allowing to retrieve one
        value after the other while also iterating over the file once.
        """
        metadata_file = f"{self.plugin_path}/metadata.txt"
        metadata = {}
        with open(metadata_file) as fh:
            for line in fh:
                split = line.strip().split("=", 1)
                if len(split) == 2:
                    metadata[split[0]] = split[1]

        def get_metadata(key: str, default_value: Optional[Any] = None) -> Any:
            if not self.plugin_path:
                return ""

            value = metadata.get(key, None)
            if value:
                return value
            elif default_value is not None:
                return default_value
            else:
                logger.error(f"Mandatory key is missing in metadata: {key}")
                sys.exit(1)

        return get_metadata

    def __iter__(self) -> Iterator[Tuple[str, Any]]:
        """Allows to represent attributes as dict, list, etc."""
        for k in vars(self):
            yield k, self.__getattribute__(k)

    def __str__(self) -> str:
        """Allows to represent instances as a string."""
        return str(dict(self))


# ############################################################################
# ####### Stand-alone run ########
# ################################
if __name__ == "__main__":
    pass
