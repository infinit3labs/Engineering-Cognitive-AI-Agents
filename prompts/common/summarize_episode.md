# Episode Summarization

You are summarizing a sequence of actions from Winston's episodic memory. Your goal is to create a concise narrative that captures what happened, preserving key technical details and identifying any surprising outcomes or lessons learned.

## Task Description

{{ task_description }}

{% if previous_summary %}

## Previous Summary

{{ previous_summary }}
{% endif %}

## Actions to Summarize

{% for action in actions %}
{{ loop.index }}. **{{ action.action }}**

- Reasoning: {{ action.reasoning }}
- Result: {{ action.result }}
  {% endfor %}

## Instructions

Create a summary that:

1. Tells a coherent story of what Winston did{% if previous_summary %}, building on the previous summary{% endif %}
2. Preserves important technical details (commands, errors, solutions)
3. Identifies "surprise" moments where outcomes differed from expectations
4. Extracts reusable lessons from the experience

{% if is_checkpoint %}
Note: This is a checkpoint compression, not a final summary. More actions will follow.
{% endif %}

Return a JSON object with this structure:

```json
{
  "summary": "Narrative summary of the actions...",
  "lessons": ["Lesson or surprise discovery 1", "Lesson 2", ...],
  "key_results": ["Important outcome 1", "Important outcome 2", ...]
}
```
