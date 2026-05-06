import json
from dataclasses import dataclass
from helix.ai.schemas import TaskType
from helix.ai.prompts import STANDARD_HELIX_SYSTEM_RULES, TASK_TEMPLATES

@dataclass
class Prompt:
    system: str
    xml_payload: str

class UnifiedPromptBuilder:
    def __init__(self):
        self._system_rules = self.load_system_rules()
        self._json_context = None
    
    def load_system_rules(self) -> str:
        return STANDARD_HELIX_SYSTEM_RULES
        
    def load_task_instructions(self, task_type: TaskType) -> str:
        if task_type not in TASK_TEMPLATES:
            raise ValueError(f"No prompt template found for task type: {task_type}")
        return TASK_TEMPLATES[task_type]
        
    def inject_context(self, json_payload: dict) -> None:
        self._json_context = json_payload
        
    def build_xml_payload(self, task_type: TaskType) -> Prompt:
        if self._json_context is None:
            raise ValueError("Context JSON must be injected before building payload.")
            
        task_instructions = self.load_task_instructions(task_type)
        json_str = json.dumps(self._json_context, indent=2)
        
        xml_payload = f"""<system_constraints>
{self._system_rules}
</system_constraints>

<backend_data>
{json_str}
</backend_data>

<task_instructions>
{task_instructions}
</task_instructions>
"""
        return Prompt(system=self._system_rules, xml_payload=xml_payload)
