import json


class JsonValidationError(ValueError):
    pass


def reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise JsonValidationError(f"duplicate key: {key}")
        result[key] = value
    return result


def reject_constant(value):
    raise JsonValidationError(f"non-standard JSON number: {value}")


def parse_object(source):
    value = json.loads(
        source,
        object_pairs_hook=reject_duplicate_keys,
        parse_constant=reject_constant,
    )
    if not isinstance(value, dict):
        raise JsonValidationError("top-level JSON value must be an object")
    return value


async def main(ctx, input):
    state = dict(input["inputs"]["state"])
    iteration = input["inputs"]["iteration"]
    raw_json = input["inputs"]["raw_json"]
    try:
        result = parse_object(raw_json)
        # Replace this line with deterministic field and business validation.
        if not result:
            raise JsonValidationError("result object must not be empty")
    except (JsonValidationError, json.JSONDecodeError, TypeError, ValueError) as exc:
        state.update(
            status="failed" if iteration >= 3 else "retry",
            raw_json=raw_json,
            validation_error=str(exc)[:300],
            retry_instruction=(
                "Regenerate the complete JSON object and correct this error: "
                + str(exc)[:300]
            ),
        )
        return {
            "outputs": {
                "state": state,
                "decision": "done" if iteration >= 3 else "continue",
            },
            "route": None,
        }
    state.update(status="success", result=result)
    state.pop("validation_error", None)
    state.pop("retry_instruction", None)
    return {
        "outputs": {"state": state, "decision": "done"},
        "route": None,
    }
