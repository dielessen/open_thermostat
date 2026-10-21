"""Keep rejected native form input visible; no persistence or validation bypass."""
import probatio as vol

def retained_input_schema(flow,schema,user_input):
    if user_input is None:
        return schema
    values=dict(user_input)
    # Missing optional selector means an explicit clear, not reinsertion of its
    # older suggestion. This only changes display hints; validators stay intact.
    for marker in schema.schema:
        if isinstance(marker,vol.Optional) and marker.schema not in values:
            values[marker.schema]=None
    return flow.add_suggested_values_to_schema(schema,values)
