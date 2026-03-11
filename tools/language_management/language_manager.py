import json

# Function to load supported languages from policy_config.json
def load_supported_languages(config_path="config/policy_config.json"):
    """
    Load supported languages from policy configuration.
    Args:
        config_path (str): Path to policy configuration file.

    Returns:
        list[dict]: Supported languages with code and label.
    """
    with open(config_path, "r", encoding="utf-8") as f:
        policy_config = json.load(f)
    return policy_config.get("language_policy", {}).get("supported_languages", [])
