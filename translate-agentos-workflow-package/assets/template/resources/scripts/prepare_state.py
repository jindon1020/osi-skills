async def main(ctx, input):
    request_text = input["inputs"]["request_text"]
    return {
        "outputs": {
            "state": {
                "request_text": request_text,
                "status": "pending",
            }
        },
        "route": None,
    }
