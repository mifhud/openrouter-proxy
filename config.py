#!/usr/bin/env python3
"""
Configuration module for Anthropic API Proxy.
Loads settings from a YAML file and initializes logging.
"""

import logging
import sys
from typing import Dict, Any

import yaml

from constants import CONFIG_FILE


def load_config() -> Dict[str, Any]:
    """Load configuration from YAML file."""
    try:
        with open(CONFIG_FILE, encoding="utf-8") as file:
            return yaml.safe_load(file)
    except FileNotFoundError:
        print(f"Configuration file {CONFIG_FILE} not found. "
              "Please create it based on config.yml.example.")
        sys.exit(1)
    except yaml.YAMLError as e:
        print(f"Error parsing configuration file: {e}")
        sys.exit(1)


def setup_logging(config_: Dict[str, Any]) -> logging.Logger:
    """Configure logging based on configuration."""
    log_level_str = config_.get("server", {}).get("log_level", "INFO")
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    logger_ = logging.getLogger("anthropic-proxy")
    logger_.info("Logging level set to %s", log_level_str)

    return logger_


def normalize_and_validate_config(config_data: Dict[str, Any]):
    """
    Normalizes the configuration by adding defaults for missing keys
    and validates the structure and types, logging warnings/errors.
    Modifies the config_data dictionary in place.
    """
    # --- Anthropic Section ---
    if not isinstance(config_data.get("anthropic"), dict):
        logger.warning("'anthropic' section missing or invalid in config.yml. Using defaults.")
        config_data["anthropic"] = {}
    anthropic_config = config_data["anthropic"]

    default_base_url = "https://api.kilo.ai/v1"
    if not isinstance(anthropic_config.get("base_url"), str):
        logger.warning(
            "'anthropic.base_url' missing or invalid in config.yml. Using default: %s",
            default_base_url
        )
        anthropic_config["base_url"] = default_base_url
    # Remove trailing slash if present
    anthropic_config["base_url"] = anthropic_config["base_url"].rstrip("/")

    default_public_endpoints = ["/v1/models"]
    if "public_endpoints" in anthropic_config and anthropic_config["public_endpoints"] is None:
        anthropic_config["public_endpoints"] = []
    if not isinstance(anthropic_config.get("public_endpoints"), list):
        logger.warning(
            "'anthropic.public_endpoints' missing or invalid in config.yml. "
            "Using default: %s",
            default_public_endpoints
        )
        anthropic_config["public_endpoints"] = default_public_endpoints
    else:
        validated_endpoints = []
        for i, endpoint in enumerate(anthropic_config["public_endpoints"]):
            if not isinstance(endpoint, str):
                logger.warning("Item %d in 'anthropic.public_endpoints' is not a string. Skipping.", i)
                continue
            if not endpoint:
                logger.warning("Item %d in 'anthropic.public_endpoints' is empty. Skipping.", i)
                continue
            # Ensure leading slash
            if not endpoint.startswith("/"):
                validated_endpoints.append("/" + endpoint)
            else:
                validated_endpoints.append(endpoint)
        anthropic_config["public_endpoints"] = validated_endpoints

    if not isinstance(anthropic_config.get("keys"), list):
        logger.warning("'anthropic.keys' missing or invalid in config.yml. Using empty list.")
        anthropic_config["keys"] = []
    if not anthropic_config["keys"]:
        logger.warning(
            "'anthropic.keys' list is empty in config.yml. "
            "Proxy will not work for authenticated endpoints."
        )

    def_key_selection_strategy = "round-robin"
    if (not isinstance(key_selection_strategy := anthropic_config.get("key_selection_strategy"), str) or
            key_selection_strategy not in ["round-robin", "first", "random"]):
        logger.warning(
            "'anthropic.key_selection_strategy' is unknown: '%s', set '%s'",
            str(key_selection_strategy), def_key_selection_strategy
        )
        anthropic_config["key_selection_strategy"] = def_key_selection_strategy

    if not isinstance(anthropic_config.get("key_selection_opts"), list):
        logger.warning("'anthropic.key_selection_opts' missing or invalid in config.yml. Using empty list.")
        anthropic_config["key_selection_opts"] = []

    default_rate_limit_cooldown = 14400
    if not isinstance(anthropic_config.get("rate_limit_cooldown"), (int, float)):
        logger.warning(
            "'anthropic.rate_limit_cooldown' missing or invalid in config.yml. "
            "Using default: %s",
            default_rate_limit_cooldown
        )
        anthropic_config["rate_limit_cooldown"] = default_rate_limit_cooldown

    # --- Request Proxy Section ---
    if not isinstance(config_data.get("requestProxy"), dict):
        logger.warning("'requestProxy' section missing or invalid in config.yml. Using defaults.")
        config_data["requestProxy"] = {}
    proxy_config = config_data["requestProxy"]

    default_proxy_enabled = False
    if not isinstance(proxy_config.get("enabled"), bool):
        logger.warning(
            "'requestProxy.enabled' missing or invalid in config.yml. Using default: %s",
            default_proxy_enabled
        )
        proxy_config["enabled"] = default_proxy_enabled

    default_proxy_url = ""
    if not isinstance(proxy_config.get("url"), str):
        logger.warning(
            "'requestProxy.url' missing or invalid in config.yml. Using default: '%s'",
            default_proxy_url
        )
        proxy_config["url"] = default_proxy_url


# Load configuration
config = load_config()

# Initialize logging
logger = setup_logging(config)

# Normalize and validate configuration (modifies config in place)
normalize_and_validate_config(config)
