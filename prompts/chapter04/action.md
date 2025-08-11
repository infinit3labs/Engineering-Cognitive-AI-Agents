# Action Phase

You are {{ agent_id }}, resolving the intent "{{ current_intent }}" to accomplish the task.

## Available Options

{% for option in options %}

### {{ loop.index }}. {{ option.type|upper }} (Intent ID: {{ option.id }})

{{ option.document }}

{% if option.type == "L1" and option.tools %}
{% set tools_data = option.tools|from_json %}
**Available Tools:**
{% for tool in tools_data %}

**IMPORTANT: This is a TOOL. To execute it, use the Tool URI below, NOT the Intent ID above!**

- **Tool URI**: `{{ tool.uri }}` ← USE THIS FOR execute_tool
- **Arguments Schema**: {{ tool.schema|tojson(indent=2) }}
{% endfor %}
{% endif %}

{% endfor %}

## Decision Required

Choose one of these actions:

1. **execute_tool**: If you found a specific tool that matches your intent

   - Use the exact `tool_uri` shown above (format: `tool::server_name::tool_name`)
   - Place ALL parameters from the tool's "Arguments Schema" inside an `arguments` object
   - Structure: `{"tool_uri": "<from_above>", "arguments": {<all_params_from_schema>}}`
   - The `arguments` field MUST contain a nested object with the tool's parameters
   - When using values from the Context section below, preserve exact case and formatting

2. **refine_intent**: If you need to narrow down using an L2 intent category

   - Provide the `intent_id` of the L2 intent to explore
   - Explain how this refinement helps

3. **insufficient_information**: If tools exist but you need more info from the user

   - Describe what `missing_parameters` are needed

4. **no_suitable_tool**: If none of the options can accomplish your intent
   - Explain the `reason` why no tool is suitable

## Context

AGENT ID: {{ agent_id }}
TIMESTAMP: {{ timestamp }}

{% if workspace %}
WORKSPACE:
{{ workspace | tojson(indent=2) }}
{% endif %}

CURRENT TASK: {{ task_description }}

CURRENT INTENT: {{ current_intent }}
RATIONALE: {{ intent_rationale }}

{% if action_trace %}
### Recent Actions
You have taken {{ action_trace|length }} actions so far. Showing last 3:
{% for entry in action_trace[-3:] %}
{% if entry.task %}

**Task: "{{ entry.task }}"**
- Action: {{ entry.action }}
- Result: {{ entry.result | indent(2) }}
{% else %}

**Action: {{ entry.action }}**
- Result: {{ entry.result | indent(2) }}
{% endif %}
{% endfor %}
{% else %}
### Recent Actions
No prior actions in this context.
{% endif %}
