from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

import yaml


class PromptManager:
    """Manage prompts loaded from external files."""
    
    def __init__(self, prompts_dir: str | Path = None):
        """Initialize prompt manager.
        Args:
            prompts_dir: Directory containing prompt files. 
                        Defaults to 'prompts' in package directory.
        """
        if prompts_dir is None:
            # Default to prompts directory in package
            prompts_dir = Path(__file__).parent / "prompts"
        
        self.prompts_dir = Path(prompts_dir)
        self._prompts_cache: Dict[str, Dict[str, Any]] = {}
        
    def _load_prompt_file(self, task_type: str) -> Dict[str, Any]:
        """Load prompt configuration from file.
        Args:
            task_type: Type of task (e.g., 'code_generation', 'review', 'planning')
        Returns:
            Dictionary containing prompt templates and metadata
        """
        if task_type in self._prompts_cache:
            return self._prompts_cache[task_type]
        
        # Try YAML first, then JSON
        yaml_path = self.prompts_dir / f"{task_type}.yaml"
        json_path = self.prompts_dir / f"{task_type}.json"
        
        if yaml_path.exists():
            with open(yaml_path, 'r') as f:
                config = yaml.safe_load(f)
        elif json_path.exists():
            with open(json_path, 'r') as f:
                config = json.load(f)
        else:
            raise FileNotFoundError(
                f"No prompt file found for task '{task_type}' in {self.prompts_dir}"
            )
        
        self._prompts_cache[task_type] = config
        return config
    
    def get_prompt(self, task_type: str, variant: str = "default", **kwargs: Any) -> str:
        """Get a formatted prompt for a specific task.
        Args:
            task_type: Type of task (matches filename without extension)
            variant: Variant of the prompt (e.g., 'default', 'detailed', 'concise')
            **kwargs: Variables to format into the prompt template
        Returns:
            Formatted prompt string
        """
        config = self._load_prompt_file(task_type)
        
        # Get the variant template
        variants = config.get('variants', {})
        if variant not in variants:
            available = ', '.join(variants.keys())
            raise ValueError(
                f"Variant '{variant}' not found for task '{task_type}'. "
                f"Available variants: {available}"
            )
        
        template = variants[variant].get('template', '')
        
        # Format with provided kwargs
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise ValueError(
                f"Missing required variable {e} for prompt '{task_type}.{variant}'"
            )
    
    def get_metadata(self, task_type: str) -> Dict[str, Any]:
        """Get metadata about a prompt.
        Args:
            task_type: Type of task
        Returns:
            Dictionary with metadata like description, author, version, etc.
        """
        config = self._load_prompt_file(task_type)
        return config.get('metadata', {})
    
    def list_available_tasks(self) -> list[str]:
        """List all available task types.
        Returns:
            List of task type names
        """
        tasks = []
        for file_path in self.prompts_dir.glob("*.yaml"):
            tasks.append(file_path.stem)
        for file_path in self.prompts_dir.glob("*.json"):
            if file_path.stem not in tasks:
                tasks.append(file_path.stem)
        return sorted(tasks)
    
    def list_variants(self, task_type: str) -> list[str]:
        """List all available variants for a task.
        Args:
            task_type: Type of task
        Returns:
            List of variant names
        """
        config = self._load_prompt_file(task_type)
        return list(config.get('variants', {}).keys())
